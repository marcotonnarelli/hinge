# hinge — Architecture

Microkernel + pipeline. Every extensible thing — readers, stores, projection
engines, projection specs, exporters — plugs in through the same mechanism:
a Python entry-point. The kernel never imports a concrete plugin.

```
Frontends ─▶ kernel.runner ─▶ Reader → Store → DatasetView → Projection → Exporter
                                     ▲          ▲                                ▲
                                     │          │                                │
                                     └── all stages and projection specs are
                                         discovered through kernel.registry
                                         (importlib.metadata entry-points)
```

## Layer rules (enforced by `import-linter`)

1. `hinge.kernel` imports nothing outside stdlib + Pydantic + PyYAML.
2. `hinge.stages.*` imports only from `hinge.kernel` and its own direct
   dependencies (duckdb, dbt-core, pyarrow, …). Stages never import other
   stages or frontends.
3. `hinge.frontends.*` imports from `hinge.kernel` only. Frontends never
   import concrete stage classes.

## Kernel

The kernel is the smallest set of contracts plus a thin runner.

| Module | What it owns |
|---|---|
| `schema/typed_node.py`, `typed_edge.py` | The data carriers. `type` is **open `str`** — projections may emit new labels without touching any enum. |
| `schema/hin_schema.py` | The vocabulary of *accepted ingest-time* labels, loaded from `config/types.yaml`. Single source of truth for both the label set and the schema version. |
| `schema/schema_violation.py` | What readers emit instead of raising for bad records. |
| `protocols/reader_stage.py` | `Iterator[TypedNode \| TypedEdge \| SchemaViolation]` — the protocol matches reality. |
| `protocols/store_stage.py` | Persistence + a `scope_to_dataset(dataset_id) → DatasetView` method. The store, not the projection, knows how its data is stored. |
| `protocols/dataset_view.py` | What the store hands the projection: `db_path`, `nodes_view`, `edges_view`. The projection never opens DuckDB itself. |
| `protocols/projection_stage.py` | `run(spec, params, view) → ProjectedGraphHandle`. Takes a `ProjectionSpec` value object, not a name. |
| `protocols/exporter_stage.py` | `write(handle, sink) → ExportReceipt`. |
| `projection/projection_spec.py` | Plain Pydantic model. One spec per task-specific subgraph. |
| `projection/projected_graph.py` | `ProjectedGraphHandle` protocol (lazy cursor) and an in-memory implementation for tests. |
| `registry.py` | `get_<role>(name)` + `list_registered(role)`. Five groups: `hinge.readers`, `hinge.stores`, `hinge.projections`, `hinge.projection_specs`, `hinge.exporters`. |
| `runner.py` | `run_ingest` (transactional — discards the dataset on failure), `run_projection`, `run_export` (computes `snapshot_id`). |

Everything else is a stage.

## Stages

| Stage | Class | Notes |
|---|---|---|
| Reader | `NumFocusReader` | Subclass to support other flat-event schemas. |
| Store | `DuckDBStore` | Context manager — `with` blocks make the file-lock lifecycle explicit. Creates dataset-scoped views in `scope_to_dataset`. |
| Projection (engine) | `DbtProjection` | Materialises one SQL model per run. Receives a `DatasetView`; never opens the store. |
| Projection (specs) | one module per spec under `stages/projection/specs/` | Each exports a `SPEC = ProjectionSpec(...)`. Registered as a `hinge.projection_specs` entry-point. |
| Exporters | `GmlExporter`, plus stubs | Stream bytes to a `BinaryIO`. |

## Pipeline sequences

### `hinge ingest <file> --reader numfocus`

```
CLI → lib.ingest()
    → HINSchema.from_yaml(types.yaml)          # vocabulary + version
    → registry.get_reader("numfocus", path)
    → with registry.get_store() as store:
        → runner.run_ingest(reader, store, schema)
            → dataset_id = uuid4().hex
            → store.begin_dataset(dataset_id, …)
            → for element in reader.iter_elements():
                  validate against schema → count violation or buffer
                  flush every 5 000 elements
            → store.finalise_dataset(…)
            (on any exception: store.discard_dataset(dataset_id); raise)
    → print "Dataset ID: <hex>"
```

### `hinge export --dataset <id> --projection dev-interaction --format gml -o out.gml`

```
CLI → lib.export(dataset_id, projection_name, fmt, sink)
    → HINSchema.from_yaml(…)
    → registry.get_projection("dbt")
    → registry.get_projection_spec("dev-interaction")    # ProjectionSpec instance
    → registry.get_exporter("gml")

    Phase 1 — store creates dataset-scoped views, then releases the file lock:
        with registry.get_store() as store:
            view = store.scope_to_dataset(dataset_id)

    Phase 2 — dbt subprocess materialises the projection:
        handle = runner.run_projection(proj_stage, spec, view, params)

    Phase 3 — read-only store for fingerprinting, then export:
        with registry.get_store(read_only=True) as store:
            runner.run_export(handle, exporter, sink,
                              store=store, projection=proj_stage,
                              schema=schema, dataset_id=dataset_id)
            # snapshot_id = sha256(
            #     store.fingerprint(dataset_id) +    # dataset-scoped, not whole-file
            #     projection.fingerprint() +
            #     schema.schema_version +
            #     tool_version )
    → print "exported N nodes, M edges → out.gml (snapshot …)"
```

## Why this is the shape it is

| Decision | Why |
|---|---|
| Open string labels, not closed enums | A projection can introduce `interacted_with` without anybody touching a Python file. types.yaml validates at ingest only; downstream stages treat labels as opaque. |
| `types.yaml` as the only source of truth | Bump version in one place; the enum/YAML drift is gone. |
| `DatasetView` between Store and Projection | The projection never opens the store's database directly. Swap DuckDB for another SQL backend by implementing one protocol. |
| Projection specs as entry-points (symmetric with stages) | Third-party packages can ship new projections by pip-installing them. No fork required. |
| Store as context manager | DuckDB's single-writer lock is made obvious at the call site. The dbt subprocess can take over the file between two `with` blocks. |
| Dataset-scoped `fingerprint(dataset_id)` | A fresh ingest of an unrelated dataset doesn't invalidate the snapshot of the one you exported yesterday. |
| Transactional `run_ingest` | A reader exception leaves no half-written dataset; `discard_dataset` cleans up. |
| Storage version (DuckDB layout) ≠ HIN schema version | They change independently. The store guards its own layout; the runner records the HIN version on every export receipt. |

## Adding a new ___

| Thing | Where to add it | Entry-point group |
|---|---|---|
| Reader for a new dataset format | `hinge/stages/readers/<name>_reader.py` | `hinge.readers` |
| Store backend | `hinge/stages/store/<name>_store.py` | `hinge.stores` |
| Projection engine (e.g. native-Python instead of dbt) | `hinge/stages/projection/<name>_projection.py` | `hinge.projections` |
| Projection spec (a new task-specific subgraph) | SQL in `hinge/stages/projection/models/<name>.sql` + spec module in `hinge/stages/projection/specs/<name>.py` | `hinge.projection_specs` |
| Exporter for a new file format | `hinge/stages/exporters/<format>_exporter.py` | `hinge.exporters` |
| Node or edge label | one line in `hinge/config/types.yaml` (bump `schema_version`) | n/a |

In every case: register the entry-point in `pyproject.toml`; write a test; no
edits to the kernel.

## Known limitations

* Only one projection can run at a time against the same DuckDB file —
  `active_nodes` / `active_edges` view names are shared. Concurrent runs
  against different datasets would clash. Sequential runs only.
* `DatasetView` is concretely SQL-backed today (path + view names). A future
  in-memory store implementing the protocol would need to write its data
  out to a temporary DuckDB file. This is a deliberate concession: every
  real projection backend wants either SQL or row-streaming, so we model
  what's actually used.
