"""Public library facade.

``import hinge`` and you get these functions. Each one assembles the pipeline
through the registry and hands it to the runner — frontends do not import
concrete stage classes.

The three-phase export dance (scope → dbt → fingerprint) is explicit here so
the DuckDB single-writer lock is released between phases. The store is a
context manager; the surrounding ``with`` blocks make ownership obvious.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, cast

from hinge.config.settings import types_yaml_path
from hinge.kernel import registry, runner
from hinge.kernel.projection.projection_spec import ProjectionSpec
from hinge.kernel.protocols.store_stage import DatasetMeta
from hinge.kernel.runner import IngestReport
from hinge.kernel.schema.hin_schema import HINSchema


def ingest(path: str | Path, reader: str) -> IngestReport:
    rdr = registry.get_reader(reader, path=path)
    schema = HINSchema.from_yaml(types_yaml_path())
    with registry.get_store() as store:
        return runner.run_ingest(rdr, store, schema)


def export(
    projection_name: str,
    dataset_id: str,
    fmt: str,
    sink: BinaryIO,
    **params: Any,
) -> Any:
    schema = HINSchema.from_yaml(types_yaml_path())
    proj_stage = registry.get_projection("dbt")
    spec = registry.get_projection_spec(projection_name)
    exporter = registry.get_exporter(fmt)

    # Phase 1: writable store creates dataset-scoped views, then releases the
    # file lock so the dbt subprocess can acquire it.
    with registry.get_store() as store:
        view = store.scope_to_dataset(dataset_id)

    # Phase 2: dbt subprocess materialises the projection.
    handle = runner.run_projection(proj_stage, spec, view, params)

    # Phase 3: read-only store for fingerprinting.
    with registry.get_store(read_only=True) as store:
        return runner.run_export(
            handle,
            exporter,
            sink,
            store=store,
            projection=proj_stage,
            schema=schema,
            dataset_id=dataset_id,
        )


def export_sql_projection(
    sql_path: str | Path,
    dataset_id: str,
    fmt: str,
    sink: BinaryIO,
    *,
    name: str | None = None,
    **params: Any,
) -> Any:
    sql_path = Path(sql_path)
    model_name = name or sql_path.stem
    schema = HINSchema.from_yaml(types_yaml_path())
    proj_stage = registry.get_projection(
        "dbt", custom_model_path=sql_path, custom_model_name=model_name
    )
    spec = ProjectionSpec(
        name=model_name,
        description=f"Custom SQL projection from {sql_path}",
        model_name=model_name,
        output_node_types=[],
        output_edge_types=[],
    )
    exporter = registry.get_exporter(fmt)

    with registry.get_store() as store:
        view = store.scope_to_dataset(dataset_id)

    handle = runner.run_projection(proj_stage, spec, view, params)

    with registry.get_store(read_only=True) as store:
        return runner.run_export(
            handle,
            exporter,
            sink,
            store=store,
            projection=proj_stage,
            schema=schema,
            dataset_id=dataset_id,
        )


def project(name: str, dataset_id: str, **params: Any) -> Any:
    proj_stage = registry.get_projection("dbt")
    spec = registry.get_projection_spec(name)
    with registry.get_store() as store:
        view = store.scope_to_dataset(dataset_id)
    return runner.run_projection(proj_stage, spec, view, params)


def project_sql(
    sql_path: str | Path, dataset_id: str, *, name: str | None = None, **params: Any
) -> Any:
    sql_path = Path(sql_path)
    model_name = name or sql_path.stem
    proj_stage = registry.get_projection(
        "dbt", custom_model_path=sql_path, custom_model_name=model_name
    )
    spec = ProjectionSpec(
        name=model_name,
        description=f"Custom SQL projection from {sql_path}",
        model_name=model_name,
        output_node_types=[],
        output_edge_types=[],
    )
    with registry.get_store() as store:
        view = store.scope_to_dataset(dataset_id)
    return runner.run_projection(proj_stage, spec, view, params)


def list_datasets() -> list[DatasetMeta]:
    with registry.get_store(read_only=True) as store:
        return cast(list[DatasetMeta], store.list_datasets())


def list_projections() -> list[str]:
    return registry.list_registered("projection_spec")


def list_exporters() -> list[str]:
    return registry.list_registered("exporter")


def list_readers() -> list[str]:
    return registry.list_registered("reader")
