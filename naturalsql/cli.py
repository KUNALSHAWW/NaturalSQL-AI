"""Command line: ``python -m naturalsql <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _settings(args):
    from .config import Settings

    s = Settings.from_env()
    if args.db:
        s.db_url = args.db if "://" in args.db else f"sqlite:///{args.db}"
    if args.provider:
        s.provider = args.provider
        s.base_url, s.model = "", ""
        s.__post_init__()
    if args.model:
        s.model = args.model
    return s


def _ask(args) -> None:
    from .api import build_engine

    s = _settings(args)
    if args.n:
        s.n_candidates = args.n
    engine = build_engine(s)
    a = engine.ask(args.question)
    print(f"status     : {a.status}")
    if a.message:
        print(f"message    : {a.message}")
    if a.sql:
        print(f"sql        : {a.sql}")
        print(f"confidence : {a.confidence:.2f} ({a.agreement})")
        for line in a.explanation:
            print(f"  - {line}")
        print(" | ".join(a.columns))
        for r in a.rows[: args.rows]:
            print(" | ".join(str(v) for v in r))
        if len(a.rows) > args.rows:
            print(f"... {len(a.rows) - args.rows} more rows")


def _demo_db(args) -> None:
    from .bench import retail_db

    p = retail_db.build(args.out)
    print(f"wrote {p}")


def _bench(args) -> None:
    from .bench import evaluate as ev
    from .bench import retail_db
    from .llm import make_client

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "bench_retail.db"
    retail_db.build(db)

    def save(name: str, data: dict) -> None:
        (out / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
        print(f"wrote {out / (name + '.json')}")

    if args.suite in ("guard", "all"):
        g = ev.evaluate_guard(db)
        g["read_only_executor"] = ev.evaluate_readonly_executor(db)
        save("guard", g)
        print(f"guard: blocked {g['blocked']}/{g['attack_payloads']} attacks, "
              f"{g['legitimate_blocked']}/{g['legitimate_queries']} legitimate queries wrongly blocked")
    if args.suite in ("accuracy", "injection", "throughput", "all"):
        llm = make_client(_settings(args))
        if args.suite in ("accuracy", "all"):
            save("accuracy", ev.run_accuracy(llm, db, n_candidates=args.candidates, limit=args.limit))
        if args.suite in ("injection", "all"):
            save("injection", ev.run_injection(llm, db))
        if args.suite in ("throughput", "all"):
            save("throughput_" + llm.name.replace(":", "_").replace("/", "_"), ev.run_throughput(llm))


def _serve(args) -> None:
    import uvicorn

    uvicorn.run("naturalsql.api:app", host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="naturalsql")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", help="SQLite file path or SQLAlchemy URL")
        p.add_argument("--provider", choices=["groq", "openai", "ollama"])
        p.add_argument("--model")

    p = sub.add_parser("ask", help="ask one question")
    p.add_argument("question")
    p.add_argument("-n", type=int, help="number of candidate queries")
    p.add_argument("--rows", type=int, default=20)
    common(p)
    p.set_defaults(fn=_ask)

    p = sub.add_parser("make-demo-db", help="create the deterministic retail demo database")
    p.add_argument("--out", default="demo_retail.db")
    p.set_defaults(fn=_demo_db)

    p = sub.add_parser("bench", help="run benchmark suites")
    p.add_argument("suite", choices=["guard", "accuracy", "injection", "throughput", "all"])
    p.add_argument("--out", default="benchmarks/results")
    p.add_argument("--candidates", type=int, default=3)
    p.add_argument("--limit", type=int)
    common(p)
    p.set_defaults(fn=_bench)

    p = sub.add_parser("serve", help="start the REST API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=_serve)

    args = ap.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    main()
