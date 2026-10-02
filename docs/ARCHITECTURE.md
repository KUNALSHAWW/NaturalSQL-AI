# Architecture

## Request flow

```
Text2SQL.ask(question)
  1. SchemaLinker      pick relevant tables and columns, add value hints (enum values, sample values), expand foreign keys
  2. LLM               candidate 1 greedy, candidates 2..N sampled (parallel)
  3. guard.check()     parse, validate the AST, regenerate SQL; security blocks end the candidate here
  4. executor.run()    read-only connection, timeout, row cap, PII masking, result fingerprint
  5. repair loop       execution errors go back to the model (max 2); security blocks never do
  6. voting            group candidates by result fingerprint; majority wins; confidence = share agreeing
  7. explain + audit   deterministic explanation, suggested chart, JSONL audit record
```

Statuses: `ok`, `no_answer` (the model declined or no valid candidate), `blocked` (guard), `failed` (execution errors after repair).

## Modules

| Module | Role |
|---|---|
| `guard.py` | sqlglot AST policy check; returns the SQL to execute and the reason when blocked |
| `executor.py` | read-only execution for SQLite, MySQL, PostgreSQL; `ResultSet` with fingerprint |
| `pipeline.py` | `Text2SQL`: linking, candidates, repair, voting, memory, audit |
| `schema.py` | introspection, enum detection, value index, `SchemaLinker` |
| `llm.py` | OpenAI-compatible client (Groq, OpenAI), Ollama client, `FakeLLM` for tests |
| `memory.py` | verified-query store with TF-IDF retrieval for few-shot examples |
| `pii.py` | result masking |
| `explain.py` | AST explanation and chart suggestion |
| `audit.py` | JSONL audit log |
| `api.py`, `cli.py`, `app.py` | FastAPI, command line, Streamlit |
| `bench/` | seeded database, payload corpus, gold questions, evaluation runners |

## Design decisions

- **Two independent barriers.** The guard can have bugs; the read-only connection does not depend on it. A bypass of one still cannot write.
- **Regenerate, do not forward.** The executed SQL is rendered from the validated tree, which removes comment-based and formatting-based tricks as a class.
- **Never repair a block.** An attacker who can steer the repair prompt could otherwise search for a bypass.
- **Vote on results, not on text.** Two different SQL strings that return the same rows agree. This is cheaper and more robust than comparing SQL.
- **Measure every layer.** Each stage of the pipeline has an ablation in `bench accuracy`.

## Extending

- Add a database: implement the read-only session setup in `executor.py` and pass the sqlglot dialect to `SQLGuard(dialect=...)` (`sqlite`, `mysql` or `postgres`).
- Add attack payloads: append to `bench/adversarial_sql.json`; CI replays them.
- Add a provider: any OpenAI-compatible endpoint works through `OpenAICompatClient`.
