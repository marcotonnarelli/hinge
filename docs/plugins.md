# Plugins

`hinge` is extensible through Python's standard
[entry-points](https://packaging.python.org/en/latest/specifications/entry-points/)
mechanism. The kernel never imports concrete stage classes — it discovers them
at startup by scanning installed packages for five entry-point groups. Any
package on PyPI that declares the same groups becomes a `hinge` plugin once it
is installed in the same environment.

There is no plugin API beyond these entry-points and the kernel protocols, and
no central plugin registry: publish your package to PyPI and `pip install`
makes it available.

## Extension points

| Entry-point group | What you register | Protocol / type |
|---|---|---|
| `hinge.readers` | Class that parses a source format into typed nodes/edges | [`ReaderStage`](../hinge/kernel/protocols/reader_stage.py) (or `BulkIngestReader` for store-native loads) |
| `hinge.stores` | Class that persists the HIN | [`StoreStage`](../hinge/kernel/protocols/store_stage.py) |
| `hinge.projections` | Class that runs projections | [`ProjectionStage`](../hinge/kernel/protocols/projection_stage.py) |
| `hinge.projection_specs` | A `ProjectionSpec` **instance** describing one task-specific subgraph | [`ProjectionSpec`](../hinge/kernel/projection/projection_spec.py) |
| `hinge.exporters` | Class that writes a `ProjectedGraphHandle` to a file format | [`ExporterStage`](../hinge/kernel/protocols/exporter_stage.py) |

Built-in stages (`numfocus` reader, `duckdb` store, `dbt` projection,
`csv` / `gml` / `networkx` exporters) register through the **same**
mechanism in `hinge`'s own `pyproject.toml`. Plugins are not second-class.

The protocols are `typing.Protocol` classes — structural, not nominal. A
plugin does not need to inherit from them; matching the signatures is enough,
and lets `mypy` verify the contract.

## Worked example — a JSON exporter

Project layout for a third-party package `hinge-json-exporter`:

```
hinge-json-exporter/
├── pyproject.toml
└── hinge_json_exporter/
    ├── __init__.py
    └── exporter.py
```

`hinge_json_exporter/exporter.py`:

```python
import json
from typing import BinaryIO

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.protocols.exporter_stage import ExportReceipt


class JsonExporter:
    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt:
        nodes = list(handle.nodes())
        edges = list(handle.edges())
        sink.write(json.dumps({"nodes": nodes, "edges": edges}).encode())
        return ExportReceipt(
            format="json",
            content_hash=handle.content_hash,
            schema_version=1,
            node_count=len(nodes),
            edge_count=len(edges),
        )
```

`pyproject.toml`:

```toml
[project]
name = "hinge-json-exporter"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["hinge>=0.1"]

[project.entry-points."hinge.exporters"]
json = "hinge_json_exporter.exporter:JsonExporter"
```

End-user flow — no change to `hinge`, no config:

```bash
pip install hinge hinge-json-exporter
hinge list exporters                              # 'json' now appears
hinge export --dataset <id> --projection ... \
  --format json -o out.json
```

## Other extension points in brief

**Reader (`hinge.readers`).** Implement `iter_elements()` and `describe()`.
Yield `TypedNode` / `TypedEdge` for valid records and `SchemaViolation` for
records you cannot map — the runner counts violations rather than aborting.
For store-native bulk loads (e.g. `COPY INTO` against DuckDB), implement
`BulkIngestReader` instead — the runner detects the shape and skips the
per-row Python path.

**Projection spec (`hinge.projection_specs`).** Register a `ProjectionSpec`
**instance** (not a class). The spec points at a dbt model file and declares
its output node/edge types. For one-off SQL projections you do not need to
ship a plugin at all — `hinge export-sql` runs a local `.sql` file against
the built-in dbt project. See [custom-projections.md](custom-projections.md).

**Store (`hinge.stores`) and projection engine (`hinge.projections`).**
Replacing these is rare — the built-in DuckDB store and dbt projection cover
the standard pipeline. New backends are possible but should follow the
respective protocols precisely; the rest of the system assumes their
behaviour.

## Conventions

These are recommendations, not enforced:

- Name packages `hinge-<thing>-<kind>` — e.g. `hinge-gephi-exporter`,
  `hinge-bigquery-reader`.
- Pin a lower bound on `hinge` (`hinge>=0.1`); the protocols may evolve
  before 1.0.
- Pick a **unique** entry-point name. If two installed plugins register the
  same name in the same group, the loader resolves to whichever the
  importer reaches first — that is install-order dependent and brittle.

## Publishing

A plugin publishes the same way `hinge` itself does — there is no
plugin-specific tooling:

```bash
uv build
uv publish
```

Once on PyPI, any user can `pip install` your plugin and it will appear
under `hinge list <role>` in their next CLI invocation.
