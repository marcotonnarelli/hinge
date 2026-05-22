# hinge — Heterogeneous Information Network tool

`hinge` ingests GitHub activity datasets (JSONL today; CSV/Parquet planned), persists
them as a typed multi-relational graph in DuckDB, and exposes **projections** —
dbt SQL models that derive task-specific sub-graphs and export them to formats
consumed by Gephi, NetworkX, igraph, etc.

This is a research artefact accompanying an ICSME 2026 submission. Architecture
and contributor rules are documented in [AGENTS.md](AGENTS.md). Read that file
before changing code.

---

## Quick start

```bash
# 1. Install (uv is the only supported package manager)
uv sync --all-extras

# 2. Ingest a dataset
uv run hinge ingest path/to/events.jsonl --reader numfocus
# → ingested 48 elements → 29 nodes, 19 edges (0 violations)
# → Dataset ID: 78fc87c370944dc2b4a4e2d4bdd97ce1

# 3. Use the printed Dataset ID to run a projection and export
uv run hinge export \
  --dataset 78fc87c370944dc2b4a4e2d4bdd97ce1 \
  --projection dev-interaction \
  --format gml \
  -o out/graph.gml

# 4. Inspect all ingested datasets
uv run hinge list datasets
```

Or via Docker:

```bash
docker compose build
docker compose run --rm hinge ingest /data/events.jsonl --reader numfocus
docker compose run --rm hinge export \
  --dataset <id> --projection dev-interaction --format gml -o /output/graph.gml
```

The DuckDB store lives at `$HINGE_STORE_PATH` (default `./network.duckdb`
locally, `/store/network.duckdb` inside the container). Multiple datasets
can coexist in the same file — each ingest run gets a unique Dataset ID.

---

## Adding a new projection

A projection is a dbt SQL model that derives a task-specific sub-graph from
the typed HIN stored in DuckDB. Adding one requires exactly four files/edits
and no changes to the kernel.

### Step 1 — Write the SQL model

Create `hinge/stages/projection/models/<name>.sql`. The model must read from
two dbt sources and produce a fixed set of columns:

```sql
-- Inputs (always these two sources, never the raw tables)
{{ source('hin', 'active_nodes') }}   -- columns: type, id, ts, attrs
{{ source('hin', 'active_edges') }}   -- columns: type, src_id, dst_id, ts, attrs

-- Output (every projection must produce exactly these columns)
SELECT
    src_id     TEXT,   -- stable node id, e.g. 'user:alice'
    src_type   TEXT,   -- node label, e.g. 'user'
    dst_id     TEXT,
    dst_type   TEXT,
    edge_type  TEXT,   -- open label, e.g. 'collaborates_with'
    attrs      JSON    -- any payload, use to_json({...})
```

`active_nodes` and `active_edges` are views created by the store immediately
before the projection runs — they are already filtered to the requested
`dataset_id`, so the SQL never needs to reference `dataset_id` at all.

**Nodes-only projections:** the pipeline derives output nodes from the union
of `src_id` and `dst_id` in the result table. A projection that emits no
edges will therefore produce no nodes either. The workaround is to use
**self-loop edges** (`src_id = dst_id`): they make the nodes visible to the
exporter, carry metadata in `attrs`, and can be filtered out in downstream
tools with `G.remove_edges_from(nx.selfloop_edges(G))`.

See [dev_interaction.sql](hinge/stages/projection/models/dev_interaction.sql)
for a full working example with a documented input/output contract, and
[top_authors_by_closures.sql](hinge/stages/projection/models/top_authors_by_closures.sql)
for the self-loop pattern.

### Step 2 — Create the spec module

Create `hinge/stages/projection/specs/<name>.py` and expose a `SPEC` constant:

```python
from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="my-projection",          # CLI key: --projection my-projection
    description="...",
    model_name="my_projection",    # must match the .sql file stem
    output_node_types=["user"],
    output_edge_types=["my_edge_label"],
)
```

This is a plain value object — no class, no inheritance. The registry loads
the module and returns the `SPEC` attribute directly.

### Step 3 — Register the entry-point

Add one line to `pyproject.toml`:

```toml
[project.entry-points."hinge.projection_specs"]
my-projection = "hinge.stages.projection.specs.my_projection:SPEC"
```

Third-party packages can register projections the same way — no fork required.

### Step 4 — Re-install so the entry-point is picked up

```bash
uv sync --all-extras
uv run hinge list projections    # → my-projection should appear
```

Entry-points are baked into `.dist-info/entry_points.txt` at install time.
Without this step the registry will not find the new spec.

### Run it

```bash
uv run hinge export \
  --dataset <id> \
  --projection my-projection \
  --format gml \
  -o output/result.gml
```

---

## Logging

Logs go to **stderr** by default. Use env vars to control verbosity and persistence:

| Variable | Purpose | Default |
|---|---|---|
| `HINGE_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `HINGE_LOG_FILE` | Also write logs to this file at full `DEBUG` detail | _(none)_ |

```bash
# See all pipeline milestones (default)
uv run hinge ingest events.jsonl

# See every batch, dbt SQL, store open/close
HINGE_LOG_LEVEL=DEBUG uv run hinge ingest events.jsonl

# Persist a full debug log to disk (useful for long ingest runs)
HINGE_LOG_FILE=hinge.log uv run hinge ingest events.jsonl
tail -f hinge.log
```

---

## Common commands

```bash
# Ingest
uv run hinge ingest events.jsonl --reader numfocus

# Inspect stored datasets
uv run hinge list datasets
uv run hinge list projections
uv run hinge list readers
uv run hinge list exporters

# Export
uv run hinge export --dataset <id> --projection dev-interaction --format gml -o out.gml

# Dev / CI
uv run pytest                                # tests
uv run ruff check .                          # lint
uv run ruff format .                         # format
uv run mypy hinge/kernel hinge/frontends     # strict type-check
uv run lint-imports                          # enforce kernel/stages/frontends boundary
```

---

## Makefile (development)

A `Makefile` is provided for quick local iteration. It uses hardcoded defaults
(fixture file, `numfocus` reader, `dev-interaction` projection, GML format) so
you don't have to remember arguments during development — **not intended for
production use**.

```bash
make install     # uv sync --all-extras
make run         # ingest fixture + export graph in one shot
make ingest      # ingest tests/fixtures/events_10.jsonl --reader numfocus
make export      # export the latest dataset (auto-detects ID from the store)
make test        # pytest
make lint        # ruff check
make fmt         # ruff format
make typecheck   # mypy on kernel + frontends
make clean       # delete output/, dbt artefacts, caches
make reset       # clean + delete network.duckdb (full fresh start)
```

Any default can be overridden on the command line:

```bash
make run   READER=numfocus LOG_LEVEL=DEBUG
make export FORMAT=graphml OUTPUT=output/graph.graphml
```
