# Contributing

```bash
pip install -r requirements-dev.txt && pip install -e .
make lint test bench-guard
```

- Security-relevant changes need a payload in `naturalsql/bench/adversarial_sql.json` that fails before the change and passes after it.
- Legitimate queries must keep passing: `make bench-guard` reports false positives.
- Benchmark claims in the docs must come from `benchmarks/results/*.json`. Do not edit numbers by hand.
- Keep commits small and describe the behaviour change.
