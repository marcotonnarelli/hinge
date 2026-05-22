"""Entry-point based registry for stage implementations and projection specs.

The kernel never imports a concrete stage class or a built-in spec. At startup
the registry scans installed packages for the entry-point groups declared in
``pyproject.toml`` and exposes them by name. Frontends call ``get_<role>``
to obtain a stage instance and ``get_projection_spec(name)`` to look up a
ProjectionSpec — symmetric: every extensible thing in the system plugs in the
same way.

Registered groups:

  ``hinge.readers``           -> Reader classes
  ``hinge.stores``            -> Store classes
  ``hinge.projections``       -> Projection stage classes (engines)
  ``hinge.projection_specs``  -> ProjectionSpec instances (one per task-specific subgraph)
  ``hinge.exporters``         -> Exporter classes
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from hinge.kernel.projection.projection_spec import ProjectionSpec

_GROUPS = {
    "reader": "hinge.readers",
    "store": "hinge.stores",
    "projection": "hinge.projections",
    "projection_spec": "hinge.projection_specs",
    "exporter": "hinge.exporters",
}


def _load(role: str, name: str) -> Any:
    group = _GROUPS[role]
    matches = [ep for ep in entry_points(group=group) if ep.name == name]
    if not matches:
        available = sorted(ep.name for ep in entry_points(group=group))
        raise LookupError(f"No {role} named {name!r} registered. Available: {available}")
    return matches[0].load()


def get_reader(name: str, **kwargs: Any) -> Any:
    return _load("reader", name)(**kwargs)


def get_store(name: str = "duckdb", **kwargs: Any) -> Any:
    return _load("store", name)(**kwargs)


def get_projection(name: str = "dbt", **kwargs: Any) -> Any:
    return _load("projection", name)(**kwargs)


def get_projection_spec(name: str) -> ProjectionSpec:
    obj = _load("projection_spec", name)
    if not isinstance(obj, ProjectionSpec):
        raise TypeError(
            f"Entry-point hinge.projection_specs:{name} must resolve to a "
            f"ProjectionSpec instance, got {type(obj).__name__}"
        )
    return obj


def get_exporter(name: str, **kwargs: Any) -> Any:
    return _load("exporter", name)(**kwargs)


def list_registered(role: str) -> list[str]:
    return sorted(ep.name for ep in entry_points(group=_GROUPS[role]))
