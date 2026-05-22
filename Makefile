SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Configuration ─────────────────────────────────────────────────────────────
READER       ?= numfocus
PROJECTION   ?= dev-interaction
FORMAT       ?= gml
OUTPUT       ?= output/graph.gml
FIXTURE      := tests/fixtures/events_10.jsonl
STORE        := network.duckdb
LOG_LEVEL    ?= INFO

# ── Helpers ───────────────────────────────────────────────────────────────────
UV           := uv run
HINGE        := $(UV) hinge

# Extract the most recently ingested dataset ID from the store (requires DuckDB)
LATEST_ID    = $(shell $(UV) python -c \
  "import duckdb; c=duckdb.connect('$(STORE)',read_only=True); \
   r=c.execute('SELECT dataset_id FROM datasets ORDER BY ingested_at DESC LIMIT 1').fetchone(); \
   print(r[0] if r else '')" 2>/dev/null)

.PHONY: help install run ingest export test lint fmt typecheck clean reset

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  hinge — development targets"
	@echo ""
	@echo "  make install          install all dependencies (including dev)"
	@echo "  make run              ingest fixture + export graph (full smoke-test)"
	@echo "  make ingest           ingest the fixture file into the store"
	@echo "  make export           export the latest dataset (auto-detects ID)"
	@echo "  make test             run the full test suite"
	@echo "  make lint             ruff lint check"
	@echo "  make fmt              ruff format in-place"
	@echo "  make typecheck        mypy on kernel + frontends"
	@echo "  make clean            delete output files and dbt artefacts"
	@echo "  make reset            clean + delete the DuckDB store (full reset)"
	@echo ""
	@echo "  Overrides (e.g. make ingest READER=numfocus):"
	@echo "    READER=$(READER)  PROJECTION=$(PROJECTION)"
	@echo "    FORMAT=$(FORMAT)   OUTPUT=$(OUTPUT)"
	@echo "    LOG_LEVEL=$(LOG_LEVEL)"
	@echo ""

# ── Install ───────────────────────────────────────────────────────────────────
install:
	uv sync --all-extras

# ── Smoke-test pipeline ───────────────────────────────────────────────────────
run: ingest export
	@echo ""
	@echo "Done. Graph written to $(OUTPUT)"

ingest:
	HINGE_LOG_LEVEL=$(LOG_LEVEL) $(HINGE) ingest $(FIXTURE) --reader $(READER)

export:
	$(eval ID := $(LATEST_ID))
	@if [ -z "$(ID)" ]; then \
	  echo "No dataset found in $(STORE). Run 'make ingest' first."; exit 1; \
	fi
	@mkdir -p $(dir $(OUTPUT))
	HINGE_LOG_LEVEL=$(LOG_LEVEL) $(HINGE) export \
	  --dataset $(ID) \
	  --projection $(PROJECTION) \
	  --format $(FORMAT) \
	  --output $(OUTPUT)

# ── Quality ───────────────────────────────────────────────────────────────────
test:
	$(UV) pytest -ra

lint:
	$(UV) ruff check .

fmt:
	$(UV) ruff format .

typecheck:
	$(UV) mypy hinge/kernel hinge/frontends

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	rm -rf output/
	rm -rf hinge/stages/projection/target/
	rm -rf hinge/stages/projection/logs/
	rm -rf hinge/stages/projection/dbt_packages/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

reset: clean
	rm -f $(STORE) $(STORE).wal
	@echo "Store deleted. Run 'make ingest' to start fresh."
