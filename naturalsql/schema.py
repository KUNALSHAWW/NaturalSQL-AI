"""Schema introspection and *schema linking*.

Putting an entire schema in the prompt works for toy databases and fails for real ones:
the model is distracted by irrelevant tables and the prompt blows the context budget.
Schema linking selects the part of the schema a question needs and adds *value hints*:
when the question mentions "France" the model is told that ``customers.country`` contains
that exact value, which removes the most common source of empty results (wrong literal).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_STOP = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is", "are", "was", "were", "be", "by", "with",
    "what", "which", "who", "whom", "how", "many", "much", "show", "list", "give", "me", "all", "each", "per", "that",
    "have", "has", "had", "do", "does", "did", "from", "at", "as", "it", "its", "their", "than", "then", "there", "this",
    "get", "find", "tell", "number", "total", "average", "count", "top", "most", "least", "highest", "lowest", "any",
}

_SYNONYMS = {
    "revenue": ["total", "amount", "price", "sales", "income"],
    "sales": ["total", "amount", "revenue", "price"],
    "spend": ["total", "amount", "price"],
    "cost": ["price", "amount"],
    "client": ["customer"], "buyer": ["customer"], "user": ["customer", "user"],
    "item": ["product"], "goods": ["product"],
    "staff": ["employee"], "worker": ["employee"], "pay": ["salary"], "wage": ["salary"],
    "date": ["created", "at", "time"], "when": ["created", "at", "date"],
    "country": ["country", "nation"], "nation": ["country"],
}


def tokens(text_: str) -> list[str]:
    """Lower-case word tokens, splitting snake_case and camelCase, with crude stemming."""
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", text_ or "")
    out = []
    for w in re.findall(r"[A-Za-z0-9]+", t.lower()):
        if w in _STOP or len(w) < 2:
            continue
        for suf in ("ies", "es", "s", "ing", "ed"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.append(w)
    return out


@dataclass
class Column:
    name: str
    type: str
    primary_key: bool = False
    nullable: bool = True
    samples: list[str] = field(default_factory=list)
    distinct_values: list[str] | None = None   # set when the column is a small enumeration


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    name: str
    columns: list[Column]
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    row_count: int | None = None

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name.lower() == name.lower()), None)


@dataclass
class SchemaInfo:
    dialect: str
    tables: dict[str, Table]
    # column -> {lower_value: original_value}, for value linking
    value_index: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)

    @property
    def table_names(self) -> set[str]:
        return {t.lower() for t in self.tables}

    def columns_by_table(self) -> dict[str, set[str]]:
        return {t.name.lower(): {c.name.lower() for c in t.columns} for t in self.tables.values()}

    # ------------------------------------------------------------------ #
    @classmethod
    def from_engine(
        cls,
        engine: Engine,
        sample_values: int = 4,
        enum_threshold: int = 25,
        value_index_limit: int = 5000,
        skip_tables: set[str] | None = None,
    ) -> SchemaInfo:
        insp = inspect(engine)
        dialect = engine.dialect.name
        dialect = {"postgresql": "postgres"}.get(dialect, dialect)
        skip = {t.lower() for t in (skip_tables or set())}
        tables: dict[str, Table] = {}
        value_index: dict[tuple[str, str], dict[str, str]] = {}
        with engine.connect() as conn:
            for tname in insp.get_table_names():
                if tname.lower() in skip or tname.lower().startswith(("sqlite_", "pg_")):
                    continue
                pk = set(insp.get_pk_constraint(tname).get("constrained_columns") or [])
                cols = []
                for c in insp.get_columns(tname):
                    cols.append(Column(c["name"], str(c["type"]), c["name"] in pk, bool(c.get("nullable", True))))
                fks = [
                    ForeignKey(list(fk["constrained_columns"]), fk["referred_table"], list(fk["referred_columns"]))
                    for fk in insp.get_foreign_keys(tname)
                ]
                tbl = Table(tname, cols, fks)
                try:
                    tbl.row_count = conn.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar()
                except Exception:  # pragma: no cover - view or permissions
                    tbl.row_count = None
                for col in cols:
                    is_text = any(k in col.type.upper() for k in ("CHAR", "TEXT", "STRING", "CLOB", "VARCHAR"))
                    try:
                        rows = conn.execute(
                            text(f'SELECT DISTINCT "{col.name}" FROM "{tname}" WHERE "{col.name}" IS NOT NULL LIMIT {value_index_limit + 1}')
                        ).fetchall()
                    except Exception:  # pragma: no cover
                        continue
                    vals = [str(r[0]) for r in rows]
                    col.samples = vals[:sample_values]
                    if is_text and len(vals) <= enum_threshold:
                        col.distinct_values = sorted(vals)
                    if is_text and 0 < len(vals) <= value_index_limit:
                        value_index[(tname, col.name)] = {v.lower(): v for v in vals if len(v) >= 3}
                tables[tname] = tbl
        return cls(dialect, tables, value_index)

    # ------------------------------------------------------------------ #
    def render(self, names: list[str] | None = None, with_samples: bool = True) -> str:
        """Render selected tables as annotated ``CREATE TABLE`` statements."""
        lines = []
        for tname in names or list(self.tables):
            t = self.tables[tname]
            parts = []
            for c in t.columns:
                note = ""
                if with_samples:
                    if c.distinct_values:
                        note = "  -- values: " + ", ".join(c.distinct_values[:12])
                    elif c.samples:
                        note = "  -- e.g. " + ", ".join(repr(s[:24]) for s in c.samples[:3])
                parts.append(f"  {c.name} {c.type}{' PRIMARY KEY' if c.primary_key else ''}{note}")
            for fk in t.foreign_keys:
                parts.append(f"  FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table}({', '.join(fk.ref_columns)})")
            rc = f"  -- about {t.row_count} rows" if t.row_count is not None else ""
            lines.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(parts) + f"\n);{rc}")
        return "\n\n".join(lines)


@dataclass
class LinkedSchema:
    tables: list[str]
    ddl: str
    value_hints: list[str]
    scores: dict[str, float]


class SchemaLinker:
    """Select the relevant tables and value hints for a question."""

    def __init__(self, schema: SchemaInfo, max_tables: int = 6, small_schema: int = 8):
        self.schema = schema
        self.max_tables = max_tables
        self.small_schema = small_schema
        self._docs: dict[str, Counter] = {}
        for tname, t in schema.tables.items():
            doc: Counter = Counter()
            for tok in tokens(tname):
                doc[tok] += 3
            for c in t.columns:
                for tok in tokens(c.name):
                    doc[tok] += 2
                for s in (c.distinct_values or c.samples[:3]):
                    for tok in tokens(s):
                        doc[tok] += 1
            self._docs[tname] = doc
        n = max(len(self._docs), 1)
        df: Counter = Counter()
        for d in self._docs.values():
            df.update(set(d))
        self._idf = {tok: math.log(1 + n / (1 + c)) for tok, c in df.items()}

    def value_hints(self, question: str) -> list[tuple[str, str, str]]:
        """Find literal values from the database mentioned in the question."""
        q = " " + re.sub(r"[^\w\s'-]", " ", question.lower()) + " "
        hits = []
        for (tname, cname), idx in self.schema.value_index.items():
            for low, orig in idx.items():
                if low in _STOP:
                    continue
                if f" {low} " in q or f" {low}s " in q:
                    hits.append((tname, cname, orig))
        # prefer longer, more specific matches
        hits.sort(key=lambda h: -len(h[2]))
        return hits[:8]

    def link(self, question: str) -> LinkedSchema:
        names = list(self.schema.tables)
        q_tokens = set(tokens(question))
        for t in list(q_tokens):
            q_tokens.update(tokens(" ".join(_SYNONYMS.get(t, []))))
        hints = self.value_hints(question)

        scores: dict[str, float] = {}
        for tname, doc in self._docs.items():
            s = sum(self._idf.get(tok, 0.0) * min(doc[tok], 3) for tok in q_tokens if tok in doc)
            scores[tname] = s
        for tname, _, _ in hints:
            scores[tname] = scores.get(tname, 0.0) + 4.0

        if len(names) <= self.small_schema:
            chosen = names
        else:
            ranked = sorted(names, key=lambda n: -scores[n])
            chosen = [n for n in ranked if scores[n] > 0][: self.max_tables] or ranked[: self.max_tables]
            # one-hop foreign-key expansion so joins are possible
            extra: list[str] = []
            for n in chosen:
                for fk in self.schema.tables[n].foreign_keys:
                    if fk.ref_table in self.schema.tables and fk.ref_table not in chosen + extra:
                        extra.append(fk.ref_table)
                for other, ot in self.schema.tables.items():
                    if other not in chosen + extra and any(f.ref_table == n for f in ot.foreign_keys) and scores[other] > 0:
                        extra.append(other)
            chosen = (chosen + extra)[: self.max_tables + 3]

        hint_lines = [
            f"The question mentions '{orig}', which is a value in column {t}.{c}."
            for t, c, orig in hints
            if t in chosen
        ]
        return LinkedSchema(chosen, self.schema.render(chosen), hint_lines, scores)
