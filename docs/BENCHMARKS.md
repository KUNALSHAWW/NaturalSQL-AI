# Benchmarks

Raw results live in `benchmarks/results/`. Everything below was produced with:

- model: `gemma4:e4b` through Ollama, CPU only, no GPU
- data: the seeded retail database from `naturalsql/bench/retail_db.py` (8 tables, deterministic)
- questions: `naturalsql/bench/questions.json` (61 questions, easy / medium / hard, gold SQL verified executable and checked for ties)
- candidates: 3 per question

## Guard (no model)

| Check | Result |
|---|---|
| Attack payloads blocked | 115 / 115 |
| Legitimate queries blocked | 0 / 61 |
| Direct writes refused by the read-only executor | 6 / 6, database intact |

Per category (blocked / total): destructive 17/17, stacked statements 5/5, obfuscation 9/9, hidden DML 7/7, file and OS access 15/15, denial of service 11/11, catalog exfiltration 15/15, privilege and session 19/19, policy violation 9/9, malformed 8/8.

The guard was hardened while building this corpus: the first run missed 5 of 115 payloads (version probes, `generate_series`, `pragma_table_info`, MySQL executable comments), and the rules were extended. The committed result is the final state, and the corpus is not independent of the author.

## Execution accuracy (61 questions)

A query counts as correct when its result set equals the gold result set.

| Stage | Overall | Easy | Medium | Hard |
|---|---|---|---|---|
| Single shot, full schema | 78.7% | 100% | 88% | 37.5% |
| Single shot, schema linking | 78.7% | 100% | 88% | 37.5% |
| Plus error repair | 80.3% | 100% | 92% | 37.5% |
| Plus execution voting (full system) | 82.0% | 100% | 92% | 43.8% |

Reading this honestly:

- The full system gains 3.3 points over the baseline, which is 2 questions out of 61. The direction is consistent across the ablation, but the sample is small.
- Schema linking changes nothing on an 8-table schema. Its value should show on larger schemas; that is not measured here.
- Cost of the full system: mean latency 22.2 s against 8.4 s, mean tokens 5,751 against 1,858, 3.1 model calls per question.

### Confidence signal

| Candidate agreement | Questions | Accuracy |
|---|---|---|
| Unanimous | 54 | 88.9% |
| Split | 7 | 28.6% |

Agreement is a usable signal for routing low-confidence answers to a human.

## Prompt injection (15 prompts, full pipeline)

0 of 15 attacks succeeded. Outcomes: 6 stopped by the guard, 8 refused by the model ("cannot be answered from the available tables"), 1 answered with a safe version of the question. Prompts include instruction override, fake system messages, requests for `password_hash` and `ssn`, catalog dumps, and a benign question with a hidden `DELETE` appended.

## Throughput

Local Ollama, 5 runs: about 8.0 decode tokens per second (range 7.8 to 8.1), mean latency 29.4 s for about 232 completion tokens. This is CPU decoding on a laptop-class machine and says nothing about hosted inference. To measure a hosted provider:

```bash
GROQ_API_KEY=... python -m naturalsql bench throughput --provider groq
```

That run records decode tokens per second and time to first token from a streaming call.

## Reproducing

```bash
make bench-guard
make bench PROVIDER=ollama MODEL=gemma4:e4b
```
