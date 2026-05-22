"""Reader for the NumFocus flat GitHub activity event format.

Supports JSONL, CSV, and Parquet files that follow the schema:

    {
      "action":     "OpenPullRequest",
      "event_id":   "...",
      "date":       "2022-01-01T00:14:19Z",
      "actor":      { "id": ..., "login": "..." },
      "repository": { "id": ..., "name": "org/repo", "organisation": "..." },
      "details":    { ... }
    }

This format is not GH Archive; it is a pre-processed flat representation
of GitHub events collected for NumFocus organisations. Any dataset that
follows this same flat schema can use this reader directly.

To support a different flat schema, subclass NumFocusReader and override
ACTION_MAP, SKIPPED_ACTIONS, or the ``_extract_*`` methods.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from hinge.kernel.protocols.reader_stage import ReaderDescriptor
from hinge.kernel.schema.schema_violation import SchemaViolation
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode
from hinge.stages.readers._format_utils import iter_csv, iter_jsonl, iter_parquet

# action string → (edge_label, artifact_subtype). Both are plain strings —
# the open HIN vocabulary lives in hinge/config/types.yaml.
_DEFAULT_ACTION_MAP: dict[str, tuple[str, str]] = {
    "OpenPullRequest": ("opened", "pull_request"),
    "OpenIssue": ("opened", "issue"),
    "CreatePullRequestReview": ("reviewed", "pull_request"),
    "CreatePullRequestComment": ("commented_on", "pull_request"),
    "CreateIssueComment": ("commented_on", "issue"),
    "CreatePullRequestReviewComment": ("review_commented_on", "pull_request"),
    "MergePullRequest": ("merged", "pull_request"),
    "ClosePullRequest": ("closed", "pull_request"),
    "CloseIssue": ("closed", "issue"),
    "ReopenPullRequest": ("reopened", "pull_request"),
    "ReopenIssue": ("reopened", "issue"),
    "PushCommits": ("pushed", "push"),
    "CommentCommit": ("commented_commits", "push"),
    "ForkRepository": ("created_fork", "branch"),
    "StarRepository": ("starred", "repo"),
    "PublishRelease": ("released", "release"),
    "ManageWikiPage": ("wiki_edited", "wiki_page"),
    "AddMember": ("member_of", "repo"),
}

_DEFAULT_SKIPPED: frozenset[str] = frozenset(
    {
        "CreateBranch",
        "DeleteBranch",
        "CreateTag",
        "DeleteTag",
        "CreateRepository",
        "MakeRepositoryPublic",
    }
)

_FORMAT_ITERS = {
    "jsonl": iter_jsonl,
    "csv": iter_csv,
    "parquet": iter_parquet,
}


class NumFocusReader:
    """Reads a NumFocus-format GitHub activity file and yields typed graph elements.

    The format (JSONL / CSV / Parquet) is inferred from the file extension
    unless overridden via the ``format`` argument.

    Subclassing guide
    -----------------
    Override ACTION_MAP to add or remap action types.
    Override SKIPPED_ACTIONS to silently drop additional action strings.
    Override any ``_extract_*`` method to change how individual fields are
    read — useful when adapting to a slightly different flat schema without
    rewriting the full extraction logic.
    """

    ACTION_MAP: Mapping[str, tuple[str, str]] = _DEFAULT_ACTION_MAP
    SKIPPED_ACTIONS: frozenset[str] = _DEFAULT_SKIPPED

    def __init__(self, path: str | Path, format: str | None = None) -> None:
        self._path = Path(path)
        self._format = format or self._infer_format(self._path)

    # ── ReaderStage protocol ─────────────────────────────────────────────

    def iter_elements(self) -> Iterator[TypedNode | TypedEdge | SchemaViolation]:
        iter_rows = _FORMAT_ITERS[self._format]
        source = str(self._path)
        for data, lineno in iter_rows(self._path):
            yield from self._process_record(data, source, lineno)

    def describe(self) -> ReaderDescriptor:
        return ReaderDescriptor(
            dataset="numfocus",
            format=self._format,
            path=self._path,
            byte_size=self._path.stat().st_size,
        )

    # ── record processing ────────────────────────────────────────────────

    def _process_record(
        self, data: dict[str, Any], source: str, lineno: int
    ) -> Iterator[TypedNode | TypedEdge | SchemaViolation]:
        action = data.get("action")

        if isinstance(action, str) and action in self.SKIPPED_ACTIONS:
            return

        if not isinstance(action, str) or action not in self.ACTION_MAP:
            yield SchemaViolation(
                code="unknown_action",
                message=f"unrecognised action {action!r}",
                source=source,
                line=lineno,
            )
            return

        edge_label, dst_kind = self.ACTION_MAP[action]
        ts = self._extract_timestamp(data)

        actor = data.get("actor") or {}
        repo = data.get("repository") or {}

        # Bot accounts are valid data deliberately excluded — skip silently,
        # not as a violation, so they don't flood the log.
        login = actor.get("login")
        if login and self._is_bot(str(login)):
            return

        user_id = self._extract_user_id(actor)
        repo_id = self._extract_repo_id(repo)

        if not user_id or not repo_id:
            yield SchemaViolation(
                code="missing_field",
                message="actor.login or repository.name absent",
                source=source,
                line=lineno,
            )
            return

        yield TypedNode(type="user", id=user_id, attrs=self._extract_user_attrs(actor))
        yield TypedNode(type="repo", id=repo_id, attrs=self._extract_repo_attrs(repo))

        event_id = data.get("event_id")

        if dst_kind == "repo":
            yield TypedEdge(
                type=edge_label,
                src_id=user_id,
                dst_id=repo_id,
                timestamp=ts,
                attrs={"event_id": event_id},
            )
        else:
            details = data.get("details") or {}
            artifact_id = self._extract_artifact_id(repo["name"], dst_kind, details)
            yield TypedNode(
                type="artifact",
                id=artifact_id,
                timestamp=ts,
                attrs={"subtype": dst_kind, "repo": repo["name"]},
            )
            yield TypedEdge(type="contains", src_id=repo_id, dst_id=artifact_id)
            yield TypedEdge(
                type=edge_label,
                src_id=user_id,
                dst_id=artifact_id,
                timestamp=ts,
                attrs={"event_id": event_id},
            )

    # ── field extraction helpers — override in subclasses ────────────────

    def _extract_timestamp(self, data: dict[str, Any]) -> datetime | None:
        raw = data.get("date")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _extract_user_id(self, actor: dict[str, Any]) -> str | None:
        login = actor.get("login")
        return f"user:{login}" if login else None

    def _is_bot(self, login: str) -> bool:
        """Return True for machine accounts that should be excluded from the graph.

        Override in a subclass to apply a different heuristic. By default any
        login ending in ``[bot]`` or ``_bot`` is treated as a bot.
        """
        return login.endswith("[bot]") or login.endswith("_bot")

    def _extract_repo_id(self, repo: dict[str, Any]) -> str | None:
        name = repo.get("name")
        return f"repo:{name}" if name else None

    def _extract_user_attrs(self, actor: dict[str, Any]) -> dict[str, Any]:
        return {"login": actor.get("login"), "github_id": actor.get("id")}

    def _extract_repo_attrs(self, repo: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": repo.get("name"),
            "organisation": repo.get("organisation"),
            "github_id": repo.get("id"),
        }

    def _extract_artifact_id(self, repo_name: str, kind: str, details: dict[str, Any]) -> str:
        payload = details.get(kind) or {}
        number = payload.get("number") or payload.get("id") or payload.get("tag")
        if number is None and kind == "push":
            push = details.get("push") or {}
            number = push.get("id")
        return f"artifact:{kind}:{repo_name}#{number}"

    @staticmethod
    def _infer_format(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        if ext in _FORMAT_ITERS:
            return ext
        raise ValueError(
            f"Cannot infer format from extension {path.suffix!r}. "
            f"Pass format= explicitly. Supported: {list(_FORMAT_ITERS)}"
        )
