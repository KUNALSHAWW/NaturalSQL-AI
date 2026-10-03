.PHONY: install test lint demo-db bench-guard bench bench-injection bench-throughput app serve clean

PY ?= python
PROVIDER ?= ollama
MODEL ?= gemma4:e4b

install:
	$(PY) -m pip install -r requirements-dev.txt && $(PY) -m pip install -e .

test:
	$(PY) -m pytest

lint:
	ruff check .

demo-db:                    ## deterministic retail database used by the demo and the benchmark
	$(PY) -m naturalsql make-demo-db --out demo_retail.db

bench-guard:                ## no model needed: attack corpus + legitimate queries + read-only executor
	$(PY) -m naturalsql bench guard

bench:                      ## execution-accuracy ablation, prompt injection, throughput (needs a model)
	$(PY) -m naturalsql bench all --provider $(PROVIDER) --model $(MODEL)

bench-injection:
	$(PY) -m naturalsql bench injection --provider $(PROVIDER) --model $(MODEL)

bench-throughput:           ## tokens per second and time to first token for the provider
	$(PY) -m naturalsql bench throughput --provider $(PROVIDER) --model $(MODEL)

app:
	streamlit run app.py

serve:
	$(PY) -m naturalsql serve

clean:
	rm -rf .pytest_cache .ruff_cache build *.egg-info naturalsql_audit.jsonl naturalsql_memory.db
