from __future__ import annotations

from pathlib import Path

import pytest

from hinge.kernel.schema import SchemaViolation, TypedEdge, TypedNode
from hinge.stages.readers.numfocus_reader import NumFocusReader

FIXTURE = Path(__file__).parents[2] / "fixtures" / "events_10.jsonl"


def _partition(
    reader: NumFocusReader,
) -> tuple[list[TypedNode], list[TypedEdge], list[SchemaViolation]]:
    nodes, edges, violations = [], [], []
    for el in reader.iter_elements():
        if isinstance(el, TypedNode):
            nodes.append(el)
        elif isinstance(el, TypedEdge):
            edges.append(el)
        elif isinstance(el, SchemaViolation):
            violations.append(el)
    return nodes, edges, violations


def test_fixture_produces_nodes_and_edges() -> None:
    nodes, edges, violations = _partition(NumFocusReader(FIXTURE))
    assert len(nodes) > 0
    assert len(edges) > 0
    assert violations == []


def test_user_nodes_have_correct_label() -> None:
    nodes, _, _ = _partition(NumFocusReader(FIXTURE))
    user_nodes = [n for n in nodes if n.type == "user"]
    assert len(user_nodes) > 0
    assert all(n.id.startswith("user:") for n in user_nodes)


def test_open_pr_emits_opened_and_contains_edges() -> None:
    _, edges, _ = _partition(NumFocusReader(FIXTURE))
    edge_labels = {e.type for e in edges}
    assert "opened" in edge_labels
    assert "contains" in edge_labels


def test_star_targets_repo_directly() -> None:
    _, edges, _ = _partition(NumFocusReader(FIXTURE))
    starred = [e for e in edges if e.type == "starred"]
    assert len(starred) > 0
    assert all(e.dst_id.startswith("repo:") for e in starred)


def test_skipped_action_yields_nothing(tmp_path: Path) -> None:
    f = tmp_path / "skip.jsonl"
    f.write_bytes(b'{"action":"CreateBranch","actor":{},"repository":{}}\n')
    nodes, edges, violations = _partition(NumFocusReader(f))
    assert nodes == [] and edges == [] and violations == []


def test_unknown_action_yields_violation(tmp_path: Path) -> None:
    f = tmp_path / "bad.jsonl"
    f.write_bytes(b'{"action":"AlienThing","actor":{"login":"x"},"repository":{"name":"o/r"}}\n')
    _, _, violations = _partition(NumFocusReader(f))
    assert len(violations) == 1
    assert violations[0].code == "unknown_action"


def test_format_inference_from_extension(tmp_path: Path) -> None:
    content = FIXTURE.read_bytes()
    f = tmp_path / "events.jsonl"
    f.write_bytes(content)
    nodes, _, _ = _partition(NumFocusReader(f))
    assert len(nodes) > 0


def test_unknown_extension_raises(tmp_path: Path) -> None:
    f = tmp_path / "data.xyz"
    f.write_bytes(b"")
    with pytest.raises(ValueError, match="Cannot infer format"):
        NumFocusReader(f)
