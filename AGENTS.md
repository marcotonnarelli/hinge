# AGENTS.md — HIN Tool

Instructions for AI coding agents working on this codebase. Read this file before touching any code.

---

## What this tool does

`hinge` takes a pre-collected GitHub dataset (JSONL/CSV/Parquet files) and builds a **Heterogeneous Information Network (HIN)**: a typed, multi-relational graph of users, repositories, pull requests, issues, and their interactions. From that substrate, users run **projections** (dbt SQL models) that derive task-specific sub-graphs and export them to Gephi, NetworkX, igraph, and others.

It is a research tool submitted to ICSME 2026. Correctness, reproducibility, and a clean public API matter more than performance.

---

## Architecture — read this first

The paradigm is **microkernel + pipeline**. Full rationale is in `architecture_decision.md`. The short version:

```
Frontends  →  kernel.runner  →  Pipeline: Reader → Store → Projection → Exporter
                                              ↑ each slot filled by a stage implementation
                  ↑ stage implementations registered in kernel.registry via entry-points
```

**Three rules that are never violated:**

1. `hinge.kernel` imports nothing outside the Python standard library and Pydantic. No DuckDB, no dbt, no HTTP, no filesystem I/O.
2. `hinge.stages.*` imports only from `hinge.kernel` and their own direct dependencies (duckdb, dbt-core, etc.). Stages never import other stages.
3. `hinge.frontends.*` imports from `hinge.kernel` and calls `hinge.kernel.registry` and `hinge.kernel.runner`. Frontends never import from `hinge.stages`.

If a proposed change violates any of these three rules, stop and ask. There is no exception.

---

## Package layout

**One class per file.** Every public class lives in its own module, named in `snake_case` after the class. Small value objects or `NamedTuple`s that only exist to support one class may live alongside it, but any type used by more than one class gets its own file.

```
hinge/
├── kernel/
│   ├── schema/               # Core typed-graph data carriers + vocabulary
│   │   ├── hin_schema.py         # HINSchema — vocabulary + schema_version (loaded from types.yaml; single source of truth)
│   │   ├── typed_node.py         # TypedNode (Pydantic; `type: str` — open vocabulary)
│   │   ├── typed_edge.py         # TypedEdge (Pydantic; `type: str` — open vocabulary)
│   │   └── schema_violation.py   # SchemaViolation (yielded by readers for bad records)
│   ├── projection/           # Projection value objects (no SQL, no computation)
│   │   ├── projection_spec.py    # ProjectionSpec + ProjectionParams
│   │   └── projected_graph.py    # ProjectedGraph + ProjectedGraphHandle
│   ├── protocols/            # Stage contracts (Python Protocol classes)
│   │   ├── reader_stage.py       # ReaderStage + ReaderDescriptor
│   │   ├── store_stage.py        # StoreStage + StoreFingerprint + StoreCensus + DatasetMeta
│   │   ├── dataset_view.py       # DatasetView — what Store hands to Projection
│   │   ├── projection_stage.py   # ProjectionStage + EngineFingerprint
│   │   └── exporter_stage.py     # ExporterStage + ExportReceipt
│   ├── registry.py           # Discovers all 5 entry-point groups; maps names → factories/specs
│   └── runner.py             # Transactional ingest, projection wrapper, snapshot_id computation
├── stages/
│   ├── readers/
│   │   ├── _format_utils.py     # shared JSONL/CSV/Parquet parsing helpers (internal)
│   │   └── numfocus_reader.py   # NumFocusReader → implements ReaderStage
│   ├── store/
│   │   └── duckdb_store.py      # DuckDBStore (context manager) → implements StoreStage
│   ├── projection/
│   │   ├── dbt_projection.py    # DbtProjection (engine) → implements ProjectionStage
│   │   └── specs/               # one module per ProjectionSpec — entry-point registered
│   │       └── dev_interaction.py   # exposes SPEC = ProjectionSpec(...)
│   └── exporters/
│       ├── gml_exporter.py      # GmlExporter    → implements ExporterStage
│       ├── graphml_exporter.py  # GraphMlExporter (stub)
│       ├── gexf_exporter.py     # GexfExporter (stub)
│       ├── parquet_exporter.py  # ParquetExporter (stub)
│       ├── jsonld_exporter.py   # JsonLdExporter (stub)
│       └── dot_exporter.py      # DotExporter (stub)
├── frontends/
│   ├── cli/            # Typer app; calls registry + runner
│   ├── tui/            # Textual app; calls registry + runner
│   ├── web/            # FastAPI app; calls registry + runner
│   └── lib.py          # Public library facade: hinge.ingest(), hinge.export(), hinge.project()
├── dbt/                # SQL representation layer: sources → HIN core → cookbook networks
│   ├── models/
│   │   ├── sources/    # active_* dbt source declarations
│   │   ├── hin/        # canonical HIN representation models
│   │   └── networks/   # cookbook projection models selected by ProjectionSpec
│   ├── macros/
│   ├── dbt_project.yml
│   └── profiles.yml
├── config/
│   └── types.yaml      # Single source of truth for the open label vocabulary + schema_version
└── __init__.py         # re-exports from frontends/lib.py
```

The type vocabulary is **open**: `TypedNode.type` and `TypedEdge.type` are
plain `str`. Validation against `types.yaml` happens once at ingest, in the
runner. Projections may emit any label — there is no Python enum to extend.

---

## Development dataset — NumFocus

The repository ships a real GitHub dataset under `num_focus/` used for development, manual testing, and the paper's case study. **Do not commit this directory** — it is listed in `.gitignore`.

```
num_focus/
├── NumFocus_Jan22-Dec24_GH_Actions.jsonl     # 2,716,910 records — one atomic event per line
└── NumFocus_Jan22-Dec24_GH_Activities.jsonl  # 2,278,299 records — one aggregated activity window per line
```

**Coverage:** 59 NumFocus-affiliated organisations (astropy, pandas-dev, matplotlib, scikit-learn, dask, bokeh, …), 2,925 repositories, January 2022 – December 2024.

### Which file to use and when

| File | Use for |
|---|---|
| `GH_Actions.jsonl` | Ingestion — primary source; each line is one indivisible atomic event |
| `GH_Activities.jsonl` | Future activity-window analysis only; not consumed by the current extractor |

Always ingest from `GH_Actions.jsonl` unless a task explicitly concerns activity windows.

### Record schema (`GH_Actions.jsonl`)

Each line is a flat JSON object — this is **not** standard GH Archive format:

```jsonc
{
  "action":     "OpenPullRequest",          // action type — maps directly to an EdgeType
  "event_id":   "19541248803",              // unique event id (string)
  "date":       "2022-01-01T00:14:19Z",     // ISO 8601 timestamp
  "actor":      { "id": 24376333, "login": "stefmolin" },   // → User node
  "repository": {
    "id":               1385122,
    "name":             "matplotlib/matplotlib",   // full_name; → Repo node
    "organisation":     "matplotlib",
    "organisation_id":  215947
  },
  "details": { ... }   // action-specific payload (see mapping below)
}
```

### Action → HIN type mapping

`NumFocusReader` translates each `action` string into a `TypedEdge` between a `User` node and an `Artifact` or `Repo` node. The `Repo → contains → Artifact` structural edge is derived from the `repository` field present on every record.

| `action` value | `EdgeType` | Src | Dst | Key `details` fields |
|---|---|---|---|---|
| `OpenPullRequest` | `opened` | User | Artifact (pull_request) | `details.pull_request.{id, number, title, state, created_date, …}` |
| `OpenIssue` | `opened` | User | Artifact (issue) | `details.issue.{id, number, title, state, created_date, …}` |
| `CreatePullRequestReview` | `reviewed` | User | Artifact (pull_request) | `details.pull_request`, `details.review.{id, submitted_date}` |
| `CreatePullRequestComment` | `commented_on` | User | Artifact (pull_request) | `details.pull_request`, `details.comment` |
| `CreateIssueComment` | `commented_on` | User | Artifact (issue) | `details.issue`, `details.comment` |
| `CreatePullRequestReviewComment` | `review_commented_on` | User | Artifact (pull_request) | `details.pull_request`, `details.comment` |
| `MergePullRequest` | `merged` | User | Artifact (pull_request) | `details.pull_request.{merged, closed_date}` |
| `ClosePullRequest` | `closed` | User | Artifact (pull_request) | `details.pull_request` |
| `CloseIssue` | `closed` | User | Artifact (issue) | `details.issue` |
| `ReopenPullRequest` | `reopened` | User | Artifact (pull_request) | `details.pull_request` |
| `ReopenIssue` | `reopened` | User | Artifact (issue) | `details.issue` |
| `PushCommits` | `pushed` | User | Artifact (push) | `details.push.{id, ref, commits}` |
| `CommentCommit` | `commented_commits` | User | Artifact (push) | `details.commit` |
| `ForkRepository` | `created_fork` | User | Artifact (branch) | `details.fork.{id, name}` |
| `StarRepository` | `starred` | User | Repo | `details` is empty |
| `PublishRelease` | `released` | User | Artifact (release) | `details.release.{id, tag, name}` |
| `ManageWikiPage` | `wiki_edited` | User | Artifact (wiki_page) | `details.wiki_page` |
| `AddMember` | `member_of` | User | Repo | `details.member` |
| `CreateBranch`, `DeleteBranch`, `CreateTag`, `DeleteTag`, `CreateRepository`, `MakeRepositoryPublic` | **skipped** | — | — | not modelled in current HIN substrate |

### Using the dataset during development

Work with a small slice for fast iteration — never read the full 2.7 M-record file in a hot loop:

```bash
# Create a 10 k-record dev slice once (gitignored)
head -10000 num_focus/NumFocus_Jan22-Dec24_GH_Actions.jsonl > num_focus/dev_slice.jsonl

# Ingest the dev slice — always declare --reader explicitly
uv run hinge ingest num_focus/dev_slice.jsonl --reader numfocus
# → Dataset ID: <hex id printed here>

# Ingest the full dataset (for integration tests and benchmarks)
uv run hinge ingest num_focus/NumFocus_Jan22-Dec24_GH_Actions.jsonl --reader numfocus

# Inspect what has been ingested
uv run hinge list datasets
```

Each ingest run produces a unique **Dataset ID** (UUID hex). Multiple datasets
can coexist in the same `network.duckdb` file. All downstream commands
(`export`, `project`) require `--dataset <id>` so it is always explicit which
data is being processed.

For **automated tests**, never read from `num_focus/` directly. Extract a small focused fixture into `tests/fixtures/` (10–50 records) and commit it. The fixture should cover only the action types the test exercises:

```bash
# Generate a fixture covering PR-lifecycle actions (20 records)
python3 -c "
import json, sys
targets = {'OpenPullRequest','MergePullRequest','CreatePullRequestReview','ClosePullRequest'}
count = 0
with open('num_focus/NumFocus_Jan22-Dec24_GH_Actions.jsonl') as f:
    for line in f:
        if json.loads(line)['action'] in targets:
            sys.stdout.write(line)
            count += 1
            if count >= 20: break
" > tests/fixtures/pr_events.jsonl
```

The existing placeholder `tests/fixtures/events_10.jsonl` should be replaced with records drawn from this dataset.

---

## Common tasks

### Adding support for a new dataset

A "dataset" is a file (JSONL, CSV, or Parquet) with its own schema. Adding support means creating one `Reader` class — there is no separate source or extractor to wire up.

1. Create `hinge/stages/readers/<dataset_name>_reader.py`.
2. Define a class that satisfies `ReaderStage` from `hinge.kernel.protocols`: implement `iter_elements()` (yields `TypedNode | TypedEdge | SchemaViolation`) and `describe()`. Use the helpers in `hinge/stages/readers/_format_utils.py` for JSONL/CSV/Parquet parsing.
3. Register it in `pyproject.toml` under `[project.entry-points."hinge.readers"]`.
4. Write a test in `tests/stages/readers/test_<dataset_name>_reader.py`.

`NumFocusReader` is the reference implementation. If your dataset uses the same flat schema but a different file format, subclass it and rely on the format auto-detection.

Do **not** import the class anywhere in `hinge.kernel` or `hinge.frontends`. The registry discovers it at startup.

### Adding a new built-in exporter

1. Create `hinge/stages/exporters/<format>.py`.
2. Define a class that satisfies `ExporterStage` from `hinge.kernel.protocols` — no `implements` declaration needed, just the right methods.
3. Register it in `pyproject.toml` under `[project.entry-points."hinge.exporters"]`.
4. Write a test in `tests/stages/exporters/test_<format>.py` (see testing section).

Do **not** import the class anywhere in `hinge.kernel` or `hinge.frontends`. The registry discovers it at startup.

### Adding a new built-in projection

A projection is a dbt SQL model that derives a task-specific sub-graph from
the typed HIN stored in DuckDB. The pipeline is:

```
scope_to_dataset()           DbtProjection.run()       _CursorHandle
  creates active_hin_nodes →   dbt subprocess runs   →   lazy cursor over
  and active_hin_edges views   your .sql model            the result table
  filtered to dataset_id       writes result table
```

Four steps, no kernel changes required.

**Step 1 — Write the SQL model**

Create `hinge/dbt/models/networks/<name>.sql`.

Input: read from canonical dbt HIN models — never touch `nodes`, `edges`, or
unscoped contract tables directly (they contain all datasets; upstream HIN models
are built from active views already filtered to the requested `dataset_id`).

```sql
{{ ref('hin_nodes') }}   -- canonical HIN node model
{{ ref('hin_edges') }}   -- canonical HIN edge model
```

Output: the model **must** return exactly these columns in this order:

```
src_id     TEXT    stable node id — e.g. 'user:alice'
src_type   TEXT    node label — e.g. 'user', 'repo', 'artifact'
dst_id     TEXT    stable node id
dst_type   TEXT    node label
edge_type  TEXT    open string label — projections may invent new ones
attrs      JSON    any payload, use DuckDB's to_json({...}) syntax
```

`DbtProjection` discovers the result table by the SQL file's stem (e.g.
`dev_interaction.sql` → table `dev_interaction`). dbt materialises it as a
`TABLE` by default (`dbt_project.yml` sets this globally).

**Output nodes are derived from edges.** `_CursorHandle.iter_nodes()` computes
the node set as `SELECT DISTINCT src_id, src_type UNION SELECT dst_id, dst_type`
from the result table. A projection that emits no edges therefore produces no
nodes. For **nodes-only projections**, use **self-loop edges** (`src_id = dst_id`):
the node appears in both sides of the union, the self-loop carries metadata in
`attrs`, and downstream tools can drop it with
`G.remove_edges_from(nx.selfloop_edges(G))`.

See `hinge/dbt/models/networks/dev_interaction.sql` for a full worked example.

**Step 2 — Create the spec module**

Create `hinge/stages/projection/specs/<name>.py` and expose a `SPEC` constant:

```python
from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="my-projection",          # CLI key passed to --projection
    description="...",
    model_name="my_projection",    # must match the .sql file stem exactly
    output_node_types=["user"],
    output_edge_types=["my_label"],
)
```

This is a plain value object — not a class, not a subclass of anything. The
registry loads the module at runtime and returns the `SPEC` attribute directly
without calling `()`. `get_projection_spec()` validates that it is a
`ProjectionSpec` instance and raises `TypeError` otherwise.

**Step 3 — Register the entry-point**

Add one line to `pyproject.toml` under the projection_specs group:

```toml
[project.entry-points."hinge.projection_specs"]
my-projection = "hinge.stages.projection.specs.my_projection:SPEC"
```

The key (`my-projection`) is what users pass on the CLI (`--projection my-projection`).
Third-party packages can register projections the same way — no fork required.

**Step 4 — Re-install and verify**

Entry-points are baked into `.dist-info/entry_points.txt` at install time.
Without this step the registry cannot find the new spec.

```bash
uv sync --all-extras
uv run hinge list projections    # new projection must appear here
```

**Step 5 — Write a test**

Create `tests/stages/projection/test_<name>.py`. Seed an in-memory DuckDB
store with minimal fixture data, run the real dbt model against it, and assert
the output rows:

```python
def test_my_projection(tmp_path):
    store = DuckDBStore(path=tmp_path / "test.duckdb")
    with store:
        # ... upsert fixture nodes and edges ...
        view = store.scope_to_dataset(dataset_id)
    proj = DbtProjection()
    handle = proj.run(SPEC, {}, view)
    edges = list(handle.iter_edges())
    assert len(edges) > 0
```

Never mock dbt — use a real dbt run against a small fixture. The full dbt
invocation takes under a second against an in-memory store.

### Adding a new node or edge label

1. Edit `hinge/config/types.yaml` — add the new value under `node_types` or
   `edge_types` and bump `schema_version`. That's the source of truth.
2. Update `NumFocusReader.ACTION_MAP` (or the relevant reader) to emit the
   new label where appropriate. The label is just a string — there is no
   enum to extend.
3. Add a test asserting the new label is emitted for the relevant raw event.

Schema version bumps are breaking changes. Any DuckDB store built with a
prior **storage** layout must be rejected or migrated explicitly — see
`DuckDBStore` (`_STORAGE_VERSION`), which is independent of the HIN
`schema_version` recorded in `types.yaml`.

---

## Testing

### Philosophy

- Each layer is tested in isolation. A stage test does not spin up a frontend. A kernel test does not touch disk.
- Never mock `hinge.kernel` types (`TypedNode`, `TypedEdge`, etc.) — construct them directly. They are plain Pydantic models.
- Never mock DuckDB in store tests — use an in-memory DuckDB instance (`:memory:`).
- Never mock dbt in projection tests — use a real dbt run against a pre-loaded in-memory DuckDB fixture.
- Reader tests use small committed fixture files from `tests/fixtures/`. Never read from `num_focus/` in tests.

### Test layout

```
tests/
├── kernel/
│   ├── test_schema.py      # Pydantic validation, SchemaVersion, NodeType/EdgeType membership
│   └── test_registry.py    # Entry-point discovery, lookup API
├── stages/
│   ├── readers/
│   │   └── test_numfocus_reader.py  # iter_elements() against fixture file, violation cases
│   ├── store/
│   │   └── test_duckdb.py  # upsert + query round-trip on :memory: DuckDB
│   ├── projection/
│   │   └── test_dev_interaction.py  # full dbt run on fixture store, assert edge types
│   └── exporters/
│       └── test_gml.py     # write() to BytesIO, parse output, assert node/edge counts
├── frontends/
│   └── test_lib.py         # integration: ingest fixture → project → export, assert receipt
└── fixtures/
    ├── events_10.jsonl     # 10 flat GH activity events used across tests
    └── store_seed.sql      # SQL to pre-load a DuckDB :memory: for projection tests
```

### Writing a reader test

```python
# tests/stages/readers/test_numfocus_reader.py
from pathlib import Path
from hinge.kernel.schema import TypedNode, TypedEdge, NodeType, EdgeType
from hinge.kernel.schema.schema_violation import SchemaViolation
from hinge.stages.readers.numfocus_reader import NumFocusReader

FIXTURE = Path("tests/fixtures/events_10.jsonl")

def test_fixture_produces_nodes_and_edges():
    nodes, edges, violations = [], [], []
    for el in NumFocusReader(FIXTURE).iter_elements():
        if isinstance(el, TypedNode): nodes.append(el)
        elif isinstance(el, TypedEdge): edges.append(el)
        elif isinstance(el, SchemaViolation): violations.append(el)
    assert len(nodes) > 0 and len(edges) > 0 and violations == []
```

### Writing an exporter test

```python
# tests/stages/exporters/test_gml.py
import io
from hinge.kernel.projection.projected_graph import ProjectedGraph
from hinge.kernel.schema import NodeType, EdgeType, TypedNode, TypedEdge
from hinge.stages.exporters.gml_exporter import GmlExporter

def test_gml_node_count():
    handle = ProjectedGraph(
        nodes=[TypedNode(type=NodeType.USER, id="user:alice")],
        edges=[],
    )
    sink = io.BytesIO()
    receipt = GmlExporter().write(handle, sink)
    assert sink.getvalue().decode().count("node [") == 1
    assert receipt.format == "gml"
    assert receipt.schema_version >= 1
```

### Writing a projection test

```python
# tests/stages/projection/test_dev_interaction.py
from hinge.stages.store.duckdb_store import DuckDBStore
from hinge.stages.projection.dbt_projection import DbtProjection

def test_dev_interaction_produces_user_edges(tmp_path):
    # seed a store, then run the projection against it
    store = DuckDBStore(path=tmp_path / "test.duckdb")
    # ... upsert fixture nodes/edges ...
    proj = DbtProjection(db_path=tmp_path / "test.duckdb")
    handle = proj.run("dev-interaction", params={})
    edges = list(handle.iter_edges())
    assert len(edges) > 0
```

### Running tests

```bash
uv run pytest                          # full suite
uv run pytest tests/kernel/            # kernel only (fast, no I/O)
uv run pytest tests/stages/exporters/  # all exporter tests
uv run pytest -x -q                    # stop on first failure, minimal output
```

---

## Coding conventions

### One class per file

**Every public class lives in its own file.** File name is the class name in `snake_case` (e.g. `GmlExporter` → `gml_exporter.py`, `TypedNode` → `typed_node.py`).

Allowed in the same file as a class:
- A `NamedTuple` or `dataclass` that is only ever returned by that class and has no other use (e.g. `ExportReceipt` alongside `GmlExporter`).
- Module-level constants that configure that class only.

Not allowed in the same file as a class:
- Another public class, even a small one.
- A Protocol or abstract base used by more than one class — that gets its own file.

When in doubt, split.

### Types

- **All public functions have type annotations.** Private helpers (`_name`) may omit them if the types are obvious from context, but annotate anything that could be called from a test.
- Use `collections.abc` for abstract types in annotations (`Iterator`, `Iterable`, `Sequence`) rather than `list`, `tuple`, `set`.
- Prefer `from __future__ import annotations` at the top of every module to enable forward references without runtime cost.
- `hinge.kernel` types are Pydantic `BaseModel` subclasses. Everywhere else, prefer plain `dataclasses.dataclass` or `typing.NamedTuple` — do not spread Pydantic into stages or frontends.

### Naming

| Thing | Convention | Example |
|---|---|---|
| Stage class | `<Dataset/Format><Role>` | `GmlExporter`, `NumFocusReader`, `DbtProjection` |
| Entry-point key | `kebab-case` | `"numfocus"`, `"gml"`, `"dev-interaction"` |
| Kernel value objects | `PascalCase` | `TypedNode`, `StoreFingerprint`, `ReaderDescriptor` |
| dbt model files | `snake_case.sql` | `dev_interaction.sql`, `fork_dynamics.sql` |
| Test files | `test_<module>.py` | `test_gml.py`, `test_duckdb.py` |
| Fixture files | descriptive, no version numbers | `events_10.jsonl` |

### Style

- `ruff` for linting and formatting. Config lives in `pyproject.toml`. Never suppress a ruff error without a comment explaining why.
- `mypy --strict` on `hinge.kernel` and `hinge.frontends`. Stages are checked with `mypy` but not `--strict` (external library stubs are incomplete).
- **No comments that describe what the code does.** Only write a comment when the *why* is non-obvious: a hidden constraint, a workaround for an external bug, a deliberate performance trade-off.
- **No docstrings on private methods.** Public protocol methods may have a one-line docstring if the method name alone is ambiguous.
- `raise` domain exceptions from `hinge.kernel.schema` (e.g., `SchemaViolation`) when validation fails. Never raise `ValueError` or `AssertionError` in kernel code.

### What never to do

- **Never import a stage from another stage.** If two stages share logic, extract it into `hinge/stages/readers/_format_utils.py` (for readers) or a new `hinge/stages/_shared/` module.
- **Never catch a broad `Exception` in a stage.** Let errors propagate to the runner, which handles reporting.
- **Never hard-code a file path inside a stage class.** Paths come in via the constructor or the registry factory.
- **Never write a stage that does both reading from files and writing to DuckDB.** The reader yields graph elements; the store upserts them. They communicate through `run_ingest`, not directly.
- **Never bump `SchemaVersion` without also updating the migration guard** in `DuckDBStore.open()` — a store with a mismatched version must raise `SchemaMismatchError`, not silently corrupt data.
- **Never add an entry-point for a class that is not yet tested.** Tests and registration must land in the same commit.

---

## Package manager — uv

**uv is the only package manager for this project.** Do not use `pip`, `poetry`, `conda`, or `pipenv` for anything.

| Task | Command |
|---|---|
| Install all deps (including dev) | `uv sync --all-extras` |
| Add a runtime dependency | `uv add <package>` |
| Add a dev-only dependency | `uv add --dev <package>` |
| Run a command in the project env | `uv run <command>` |
| Update the lockfile | `uv lock` |

`uv.lock` is committed to the repository. Never edit it by hand; always let `uv` regenerate it. The lockfile guarantees bit-for-bit reproducibility across machines and inside containers.

`pyproject.toml` is the single source of truth for all metadata, dependencies, entry-points, and tool configuration (ruff, mypy, pytest, import-linter). There is no `setup.py`, `setup.cfg`, or `requirements.txt`.

## Build and dev commands

```bash
# Install with all dev dependencies
uv sync --all-extras

# Type checking
uv run mypy hinge/kernel hinge/frontends
uv run mypy hinge/stages

# Lint + format check
uv run ruff check .
uv run ruff format --check .

# Fix lint and format in place
uv run ruff check --fix .
uv run ruff format .

# Full test suite with coverage
uv run pytest --cov=hinge --cov-report=term-missing

# Emit the public JSON Schema artefact
uv run python -m hinge.kernel.schema emit-schema > schema.json

# Ingest (--reader is always required)
uv run hinge ingest num_focus/dev_slice.jsonl --reader numfocus
# → prints Dataset ID: <hex>

# List all ingested datasets
uv run hinge list datasets

# Export using the printed dataset ID
uv run hinge export \
  --dataset <hex> \
  --projection dev-interaction \
  --format gml \
  -o out.gml

# Run with verbose logging (all pipeline milestones + dbt output)
HINGE_LOG_LEVEL=DEBUG uv run hinge ingest num_focus/dev_slice.jsonl --reader numfocus

# Persist logs to a file while keeping stderr output
HINGE_LOG_FILE=hinge.log uv run hinge ingest num_focus/dev_slice.jsonl --reader numfocus
```

---

## Logging

Logging is initialised once at startup by `hinge/config/logging_setup.py`. Every module uses `logging.getLogger(__name__)` — no print statements.

### Log levels

| Level | What you see |
|---|---|
| `INFO` (default) | Pipeline milestones: ingest start/end, violation count, projection start/end, export start/end |
| `DEBUG` | Everything above + batch upsert counts, store open/close, full dbt output line-by-line, exact dbt command |
| `WARNING` / `ERROR` | Violations and stage failures only |

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `HINGE_LOG_LEVEL` | Verbosity for `hinge.*` loggers | `INFO` |
| `HINGE_LOG_FILE` | If set, logs are also written to this path at `DEBUG` detail (rotating, max 10 MB × 3 backups) | _(stderr only)_ |

`HINGE_LOG_FILE` is the recommended way to capture a persistent audit trail for long ingest runs or CI pipelines.

### Adding logging to a new stage

Every stage file should declare a module-level logger and use it instead of print:

```python
import logging
logger = logging.getLogger(__name__)

# INFO for user-visible milestones
logger.info("stage started — key=%s", value)

# DEBUG for internal detail useful during development
logger.debug("batch processed — count=%d", n)

# WARNING for recoverable issues (e.g. schema violations)
logger.warning("violation [%s] line %d — %s", code, line, message)
```

`setup_logging()` is called once in `hinge/frontends/cli/app.py`. When `hinge` is used as a library, the caller is responsible for configuring logging (standard Python convention).

---

## Containerisation

The tool must run entirely inside Docker. No dependency is expected to be installed on the host machine other than Docker and `uv` (for local development only). The project provides:

```
hinge/
├── Dockerfile             # multi-stage build: builder + slim runtime image
├── docker-compose.yml     # wires the tool container with external service containers
└── .dockerignore
```

### Service containers

All current export targets (GML, GraphML, GEXF, Parquet, JSON-LD, DOT) are file-based and require no external service. The tool container is self-contained for all built-in stages.

If a future exporter or stage requires a networked service, it **must run as its own container** declared in `docker-compose.yml` under a Compose profile, and it must never be assumed to run on `localhost`. Add it to a service table here before writing any code that connects to it.

### Dockerfile structure

Use a two-stage build. The builder stage installs dependencies with `uv`; the runtime stage copies only the installed env and the package source — no build tools.

```dockerfile
# ── Builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy lockfile + metadata first (layer-cache friendly)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY hinge/ ./hinge/
COPY hinge/dbt/ ./hinge/dbt/

# ── Runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/hinge   ./hinge

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["hinge"]
```

Rules for the Dockerfile:
- `uv sync --frozen` — never allow the lockfile to drift inside the image.
- No `--no-cache-dir` flag; layer caching is the point.
- The runtime stage must not contain `uv`, build tools, or test dependencies.
- DuckDB data is **never baked into the image** — always mounted as a volume.

### docker-compose.yml structure

```yaml
services:
  hinge:
    build: .
    volumes:
      - ./data:/data          # input files (JSONL, CSV, Parquet)
      - ./output:/output      # exported graphs
      - hinge-store:/store      # DuckDB store file (persistent named volume)
    environment:
      HINGE_STORE_PATH: /store/network.duckdb
      HINGE_LOG_LEVEL: INFO

volumes:
  hinge-store:
```

When a future stage requires an external networked service, add it as a separate Compose service with its own profile (so it only starts when explicitly requested with `docker compose --profile <name> up`). Add a `depends_on` with a health-check to the `hinge` service at that point.

### Environment variables

All runtime configuration comes from environment variables, never from hardcoded values or config files baked into the image.

| Variable | Purpose | Default |
|---|---|---|
| `HINGE_STORE_PATH` | Path to the DuckDB file inside the container | `/store/network.duckdb` |
| `HINGE_LOG_LEVEL` | Logging verbosity (`DEBUG` / `INFO` / `WARNING` / `ERROR`) | `INFO` |
| `HINGE_LOG_FILE` | Optional persistent log file path (full `DEBUG` detail, rotating) | _(stderr only)_ |

Stage implementations must read these via `os.environ` or a small `hinge/config/settings.py` module — never via a constructor argument that the user must remember to pass.

### .dockerignore

`.dockerignore` must exclude everything that does not belong in the image:

```
.git/
.venv/
__pycache__/
*.pyc
*.pyo
.mypy_cache/
.ruff_cache/
.pytest_cache/
tests/
docs/
*.md
*.drawio
data/
output/
*.duckdb
```

---

## .gitignore

The repository must include a `.gitignore` covering Python, uv, and Docker artefacts. At minimum:

```gitignore
# Python
__pycache__/
*.py[cod]
*.so
*.egg
*.egg-info/
dist/
build/
.eggs/

# uv
.venv/
# uv.lock is intentionally committed — do NOT add it here

# Type checking / linting caches
.mypy_cache/
.ruff_cache/

# Testing
.pytest_cache/
htmlcov/
.coverage
coverage.xml

# DuckDB store files (data, not code)
*.duckdb
*.duckdb.wal

# Exported graphs (outputs, not source)
*.gml
*.graphml
*.gexf
*.dot

# Development dataset (large files — never commit)
num_focus/

# Docker
.dockerignore

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.iml
```

**`uv.lock` is always committed.** Never add it to `.gitignore`. It is the reproducibility guarantee for both CI and container builds.

---

## Dependency rules (enforced by import-linter)

```
hinge.kernel        → stdlib, pydantic
hinge.stages.*      → hinge.kernel, stdlib, own deps
hinge.frontends.*   → hinge.kernel, stdlib, own deps
hinge.*             → NOT each other laterally (no stage imports stage, no frontend imports frontend)
```

If you add a dependency that violates this graph, `uv run lint-imports` will fail in CI. Fix the import, not the linter config.

---

## Dataset identity

Every ingest run produces a **Dataset ID** — a UUID hex string generated by the runner and stored in the `datasets` table of the DuckDB file. It is printed to the terminal and included in `IngestReport.dataset_id`.

The Dataset ID is required by all downstream commands. There is no default — you must always pass `--dataset <id>` explicitly. This prevents accidental mixing of datasets in a projection.

```bash
# The ID is printed after ingest
uv run hinge ingest events.jsonl --reader numfocus
# → Dataset ID: 78fc87c370944dc2b4a4e2d4bdd97ce1

# It is also queryable
uv run hinge list datasets
```

The DuckDB store partitions `nodes`, `edges`, and `contract_*` tables by `dataset_id`. Before each dbt run, `DbtProjection` creates active scoped views (notably `active_hin_nodes`, `active_hin_edges`, and `active_contract_*`) filtered to the requested dataset. Projection SQL files always read from these views.

---

## Snapshot identity

Every export produces an `ExportReceipt` with a `snapshot_id` field. It is a SHA-256 hex digest of:

```
store.fingerprint(dataset_id)   # hash of ONE dataset's nodes + edges
+ proj.fingerprint()            # hash of dbt project files
+ schema.schema_version (int)   # from types.yaml
+ tool_version (str)
```

The fingerprint is **dataset-scoped** — ingesting an unrelated dataset does
not change the snapshot of a dataset you exported yesterday. Tests that
produce exports must assert the receipt's `schema_version` equals
`HINSchema.from_yaml(types_yaml_path()).schema_version`.

**Schema version** lives in `hinge/config/types.yaml` and is the only place
to read it. It is independent of `DuckDBStore._STORAGE_VERSION`, which guards
the DuckDB table layout. If a `network.duckdb` was written with a different
storage layout, `DuckDBStore` raises `SchemaMismatchError` on open — delete
the file and re-ingest.
