# agentic_mining

Working repository for a tool-demo paper on **constructing GitHub-derived networks** from raw event scrapes. The goal is a researcher-facing tool (`ghnet`) that turns raw GitHub action JSONL into transparent, auditable node/edge lists for downstream network analysis.

## Contents

| File | Purpose |
|---|---|
| [tool-design-ideas.md](tool-design-ideas.md) | Design doc for the GitHub Network Composer: HIN data model, supported/unsupported networks, recipe definitions, and CLI sketch. |
| [github-network-composer-demo.qmd](github-network-composer-demo.qmd) | Executable Quarto notebook: ingests raw JSONL into DuckDB, normalizes users/repos/artifacts, and builds example edge lists. Acts as an executable spec for the engineering team. |
| [pyproject.toml](pyproject.toml) | `uv`-managed Python environment (`duckdb`, `pandas`, `pyarrow`, `networkx`, `jupyter`). |

## Design premise

Researchers should be able to ask for a network in domain language:

```bash
ghnet build pr-review --repo pandas-dev/pandas --mode author-to-reviewer
```

rather than writing the event-to-network SQL themselves. The tool hides the plumbing while recording exactly which raw actions and transformations produced each edge.

## Data flow

```text
raw JSONL
  → DuckDB raw table
  → normalized HIN tables (User / Repo / Artifact)
  → recipe-specific network views
  → node list + edge list exports (Parquet, GraphML, CSV, NetworkX, ...)
```

Raw JSONL stays the durable source of truth; everything downstream is rebuildable.

## Running the demo notebook

Place the raw action JSONL at:

```text
14914741/NumFocus_Jan22-Dec24_GH_Actions.jsonl
```

(unzip the bundled archive first if needed), then render with Quarto through `uv`:

```bash
uv run quarto render github-network-composer-demo.qmd
```

Outputs land in `outputs/network-composer-demo/` (DuckDB file, Parquet edge lists, metadata JSON) alongside `github-network-composer-demo.html`.

## Networks currently supported

Star, fork, PR review, issue/comment, developer–repository affiliation, and projections (repo–repo shared-contributor, user–user co-participation).

Not supported from this scrape: follow, watch, @-mention, artifact-artifact-reference, and true co-commit/co-edit networks. See [tool-design-ideas.md](tool-design-ideas.md) for the full table and reasons.
