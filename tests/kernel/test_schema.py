from __future__ import annotations

from hinge.config.settings import types_yaml_path
from hinge.kernel.schema import HINSchema, TypedEdge, TypedNode


def test_typed_node_open_label() -> None:
    n = TypedNode(type="user", id="user:alice", attrs={"login": "alice"})
    assert n.model_dump()["type"] == "user"


def test_typed_edge_open_label() -> None:
    # Projections can use labels not in types.yaml — TypedEdge accepts any string.
    e = TypedEdge(type="interacted_with", src_id="user:a", dst_id="user:b")
    assert e.type == "interacted_with"


def test_hin_schema_loads_from_yaml() -> None:
    schema = HINSchema.from_yaml(types_yaml_path())
    assert "user" in schema.node_types
    assert "opened" in schema.edge_types
    assert schema.schema_version >= 1


def test_hin_schema_allows_listed_labels() -> None:
    schema = HINSchema.from_yaml(types_yaml_path())
    assert schema.allows_node("user")
    assert schema.allows_edge("opened")


def test_hin_schema_rejects_unlisted_labels() -> None:
    schema = HINSchema(schema_version=1, node_types={"user"}, edge_types={"opened"})
    assert not schema.allows_node("repo")
    assert not schema.allows_edge("merged")
