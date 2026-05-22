from __future__ import annotations

from hinge.kernel import registry
from hinge.kernel.projection.projection_spec import ProjectionSpec


def test_built_in_stages_are_discoverable() -> None:
    assert "numfocus" in registry.list_registered("reader")
    assert "duckdb" in registry.list_registered("store")
    assert "dbt" in registry.list_registered("projection")
    assert "gml" in registry.list_registered("exporter")


def test_projection_specs_are_discoverable() -> None:
    """Projection specs plug in through the same mechanism as stages."""
    names = registry.list_registered("projection_spec")
    assert "user-user-repo-collaboration" in names


def test_get_projection_spec_returns_a_spec() -> None:
    spec = registry.get_projection_spec("user-user-repo-collaboration")
    assert isinstance(spec, ProjectionSpec)
    assert spec.model_name == "dev_interaction"
