"""AST-based SQL guard: the safety boundary between an LLM and the database.

LLM-generated SQL must be treated like untrusted user input (OWASP LLM01 prompt
injection leading to LLM05 improper output handling). Regex or keyword filters are
trivially bypassed with comments, case tricks or nested statements, so this guard
parses the query into an abstract syntax tree with ``sqlglot`` and validates the
*whole tree*:

* exactly one statement, and it is a read-only query (SELECT, possibly with CTEs
  and set operations)
* no data-changing, schema-changing or administrative node anywhere, including
  inside CTEs and subqueries
* no dangerous functions (file access, sleeps, extension loading, ...)
* only tables from the allow-list; system catalogs are blocked by default
* no columns from the deny-list, and no ``SELECT *`` over tables that contain them
* bounded complexity (joins, nesting) and a row limit

The query that is finally executed is **regenerated from the validated tree**, not the
original text, so comments (including MySQL executable comments) and unusual
formatting never reach the database.

This guard is one layer. The executor adds a second, independent one by opening the
database read-only, so a bypass of the parser still cannot write.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

_FORBIDDEN_NAMES = (
    "Insert", "Update", "Delete", "Drop", "Alter", "Create", "Command", "Merge", "TruncateTable",
    "Grant", "Revoke", "Set", "Use", "Pragma", "Attach", "Detach", "Copy", "LoadData", "Into", "Lock",
    "Transaction", "Commit", "Rollback", "Analyze", "Kill", "Execute", "Refresh", "Comment", "Cache",
    "Uncache", "Declare", "Return", "Export", "Install", "Load",
)
FORBIDDEN_NODES: tuple[type, ...] = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))

DEFAULT_FORBIDDEN_FUNCTIONS = frozenset(
    {
        # file and OS access
        "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer",
        "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file", "lo_import", "lo_export",
        "lo_get", "load_file", "copy", "xp_cmdshell", "sys_exec", "sys_eval", "dblink", "dblink_exec",
        "pg_execute_server_program", "openrowset", "opendatasource",
        # denial of service
        "sleep", "pg_sleep", "pg_sleep_for", "pg_sleep_until", "benchmark", "randomblob", "zeroblob",
        "generate_series", "waitfor", "repeat",
        # session and server administration
        "set_config", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "current_setting",
        "get_lock", "release_lock", "version", "sqlite_version", "sqlite_source_id", "database",
        "user", "system_user", "session_user", "current_user", "connection_id", "pg_backend_pid",
    }
)

FORBIDDEN_FUNCTION_PREFIXES = ("pragma_", "pg_", "lo_", "dblink", "xp_", "sp_", "sys_", "utl_", "dbms_")

SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog", "mysql", "sys", "performance_schema", "sqlite_temp_master"})
SYSTEM_TABLE_PREFIXES = ("sqlite_", "pg_", "sys.", "information_schema")


@dataclass
class GuardResult:
    ok: bool
    sql: str = ""                                  # normalised SQL, safe to execute (empty when blocked)
    reasons: list[str] = field(default_factory=list)
    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


@dataclass
class SQLGuard:
    """Validate and normalise generated SQL.

    Args:
        dialect: ``sqlite``, ``mysql`` or ``postgres``.
        allowed_tables: table names the query may read. ``None`` allows any non-system table.
        denied_columns: column names that may never appear (``table.column`` also accepted).
        max_rows: row limit enforced by injecting or capping ``LIMIT``.
        max_joins: maximum number of JOIN clauses.
        max_depth: maximum subquery nesting depth.
        forbidden_functions: lower-case function names that are blocked.
    """

    dialect: str = "sqlite"
    allowed_tables: set[str] | None = None
    denied_columns: set[str] = field(default_factory=set)
    max_rows: int = 1000
    max_joins: int = 8
    max_depth: int = 4
    forbidden_functions: frozenset[str] = DEFAULT_FORBIDDEN_FUNCTIONS
    table_columns: dict[str, set[str]] = field(default_factory=dict)  # for SELECT * checks

    def __post_init__(self) -> None:
        if self.allowed_tables is not None:
            self.allowed_tables = {t.lower() for t in self.allowed_tables}
        self.denied_columns = {c.lower() for c in self.denied_columns}
        self.table_columns = {t.lower(): {c.lower() for c in cols} for t, cols in self.table_columns.items()}

    # ------------------------------------------------------------------ #
    def check(self, sql: str) -> GuardResult:
        reasons: list[str] = []
        text = (sql or "").strip().rstrip(";").strip()
        if not text:
            return GuardResult(False, reasons=["empty query"])
        if len(text) > 20_000:
            return GuardResult(False, reasons=["query too long"])
        if "\x00" in text:
            return GuardResult(False, reasons=["null byte in query"])
        if "/*!" in text:
            return GuardResult(False, reasons=["MySQL executable comments (/*! ... */) are not allowed"])

        try:
            statements = sqlglot.parse(text, read=self.dialect)
        except SqlglotError as e:
            return GuardResult(False, reasons=[f"could not parse as {self.dialect} SQL: {str(e).splitlines()[0][:120]}"])
        statements = [s for s in statements if s is not None]
        if len(statements) != 1:
            return GuardResult(False, reasons=[f"exactly one statement is allowed, found {len(statements)}"])
        tree = statements[0]

        if not isinstance(tree, (exp.Select, exp.SetOperation, exp.Subquery)):
            return GuardResult(False, reasons=[f"only read-only SELECT queries are allowed (got {type(tree).__name__})"])

        tables: set[str] = set()
        columns: set[str] = set()
        cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        column_refs: list[tuple[str, str, str]] = []
        joins = 0

        for node in tree.walk():
            if isinstance(node, FORBIDDEN_NODES):
                reasons.append(f"forbidden operation: {type(node).__name__.upper()}")
            elif isinstance(node, exp.Table):
                self._check_table(node, cte_names, tables, reasons)
            elif isinstance(node, exp.Column):
                name = node.name.lower()
                columns.add(name)
                column_refs.append((node.table.lower(), name, node.name))
            elif isinstance(node, exp.Join):
                joins += 1
            if isinstance(node, (exp.Func, exp.Anonymous)):
                for fname in self._func_names(node):
                    if fname in self.forbidden_functions or fname.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                        reasons.append(f"forbidden function: {fname}()")
                        break

        reasons.extend(self._denied_column_checks(tree, tables, column_refs))
        if joins > self.max_joins:
            reasons.append(f"too many joins ({joins} > {self.max_joins})")
        depth = self._depth(tree)
        if depth > self.max_depth:
            reasons.append(f"queries nested too deeply ({depth} > {self.max_depth})")
        reasons.extend(self._star_checks(tree, tables))

        # de-duplicate while keeping order
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            return GuardResult(False, reasons=reasons, tables=tables, columns=columns)

        tree = self._apply_limit(tree)
        try:
            safe_sql = tree.sql(dialect=self.dialect, comments=False)
        except SqlglotError as e:  # pragma: no cover - defensive
            return GuardResult(False, reasons=[f"could not regenerate SQL: {e}"])
        return GuardResult(True, sql=safe_sql, tables=tables, columns=columns)

    # ------------------------------------------------------------------ #
    def _func_names(self, node: exp.Expression) -> set[str]:
        """Every name a function call is known by.

        sqlglot maps many functions onto internal node classes (``VERSION()`` becomes
        ``CurrentVersion``, ``generate_series`` becomes ``ExplodingGenerateSeries``), so the
        class name alone is not reliable. The name as *emitted* in the regenerated SQL is what
        the database will actually see, so it is checked as well.
        """
        names: set[str] = set()
        if isinstance(node, exp.Anonymous):
            names.add(str(node.name).lower())
        else:
            try:
                names.add(node.sql_name().lower())
            except Exception:  # pragma: no cover
                pass
        try:
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_$]*)", node.sql(dialect=self.dialect))
            if m:
                names.add(m.group(1).lower())
        except Exception:  # pragma: no cover
            pass
        return names

    def _check_table(self, node: exp.Table, cte_names: set[str], tables: set[str], reasons: list[str]) -> None:
        name = node.name.lower()
        if not name:  # table-valued function like generate_series(): checked as a function
            return
        schema = (node.db or "").lower()
        catalog = (node.catalog or "").lower()
        if name in cte_names and not schema:
            return
        if schema in SYSTEM_SCHEMAS or catalog in SYSTEM_SCHEMAS or name.startswith(SYSTEM_TABLE_PREFIXES):
            reasons.append(f"access to system catalog '{node.sql(dialect=self.dialect)}' is not allowed")
            return
        tables.add(name)
        if self.allowed_tables is not None and name not in self.allowed_tables:
            reasons.append(f"table '{node.name}' is not available")

    def _denied_column_checks(self, tree: exp.Expression, tables: set[str], refs: list[tuple[str, str, str]]) -> list[str]:
        """Match restricted columns by name, by ``table.column`` and through table aliases."""
        if not self.denied_columns:
            return []
        alias_to_table = {}
        for t in tree.find_all(exp.Table):
            if t.name:
                alias_to_table[(t.alias or t.name).lower()] = t.name.lower()
        out = []
        for qualifier, name, original in refs:
            table = alias_to_table.get(qualifier, qualifier)
            candidates = {name}
            if table:
                candidates.add(f"{table}.{name}")
            else:  # unqualified: it could belong to any referenced table that has this column
                candidates |= {f"{t}.{name}" for t in tables if name in self.table_columns.get(t, set())}
            if candidates & self.denied_columns:
                out.append(f"access to restricted column '{original}' is not allowed")
        return out

    def _star_checks(self, tree: exp.Expression, tables: set[str]) -> list[str]:
        """Block ``SELECT *`` when any referenced table has a denied column."""
        if not self.denied_columns:
            return []
        out = []
        has_star = any(isinstance(n, exp.Star) for n in tree.walk() if not isinstance(n.parent, exp.Count))
        if has_star:
            for t in tables:
                if self.table_columns.get(t, set()) & self.denied_columns:
                    out.append(f"SELECT * on '{t}' would expose restricted columns; list columns explicitly")
        return out

    def _depth(self, node: exp.Expression, level: int = 0) -> int:
        deepest = level
        for child in node.iter_expressions():
            inc = 1 if isinstance(child, (exp.Subquery, exp.Select)) and not isinstance(node, exp.Subquery) else 0
            deepest = max(deepest, self._depth(child, level + inc))
        return deepest

    def _apply_limit(self, tree: exp.Expression) -> exp.Expression:
        limit = tree.args.get("limit")
        if limit is None:
            return tree.limit(self.max_rows)
        try:
            value = int(limit.expression.name)
        except (ValueError, AttributeError, TypeError):
            return tree.limit(self.max_rows)
        return tree.limit(min(value, self.max_rows)) if value > self.max_rows else tree
