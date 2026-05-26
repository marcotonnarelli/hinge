# Custom projections

Custom projections let users define local dbt SQL models without packaging a
plugin or registering an entry-point. They support research-specific network
variants while preserving the same HIN contract, macros, and reproducibility
checks as built-in cookbook projections.

## Usage

```bash
uv run hinge export-sql my_projection.sql \
  --dataset <dataset-id> \
  --format gml \
  -o outputs/my_projection.gml
```

`my_projection.sql` is copied into a temporary clone of the built-in dbt project
for that run. The permanent package is not modified.

## Writing a custom SQL projection

A custom projection is a normal dbt model. It should:

1. start with `{{ config(materialized='table') }}`;
2. read from canonical HIN models or intermediate models;
3. transform those rows into a network edge list;
4. emit the standard `network_edges` schema, preferably through the
   `network_edges` macro.

Minimal template:

```sql
{{ config(materialized='table') }}

WITH source_rows AS (
    SELECT *
    FROM {{ ref('hin_edges') }}
    WHERE edge_type = 'starred'
)

{{ network_edges(
    relation='source_rows',
    recipe_name='my_projection',
    source_node_id='source_node_id',
    source_node_type='source_node_type',
    target_node_id='target_node_id',
    target_node_type='target_node_type',
    edge_type="'my_edge_label'",
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_edge_id': edge_id})"
) }}
```

### Available inputs

Use dbt `ref()` so dbt builds dependencies in the right order.

| Model | Use for |
|---|---|
| `ref('hin_nodes')` | All canonical nodes: users, repos, artifacts. |
| `ref('hin_edges')` | All canonical typed HIN edges. |
| `ref('hin_capabilities')` | Adapter capability checks. |
| `ref('int_user_artifact_incidence')` | User-artifact event incidence. |
| `ref('int_developer_repo_affiliation')` | Derived user-repo affiliation. |

The HIN models are built from dataset-scoped `active_*` views. Custom SQL should
not filter by `dataset_id`; that has already happened before dbt runs.

Core `hin_nodes` columns:

```text
node_id, node_type, node_subtype, natural_key, display_name,
created_at, updated_at, observed_at, is_stub, properties
```

Core `hin_edges` columns:

```text
edge_id, source_node_id, source_node_type, source_node_subtype,
target_node_id, target_node_type, target_node_subtype,
edge_type, edge_subtype, directed, occurred_at, observed_at,
valid_from, valid_to, weight, event_count,
context_repo_node_id, context_artifact_node_id,
adapter_run_id, source_record_id, properties
```

### Useful macros

| Macro | Purpose |
|---|---|
| `slice_edges(...)` | Filter canonical HIN edges by type, endpoint type/subtype, bot policy, and time window. |
| `build_incidence(...)` | Build a left-right incidence table from HIN edges. |
| `project_bipartite(...)` | Project an incidence table onto one side, e.g. user-user over shared issues. |
| `collapse_two_hop_path(...)` | Collapse paths such as user → comment → mentioned user. |
| `filter_bots(...)` | Apply a bot policy in custom SQL predicates. |
| `apply_time_window(...)` | Apply `start_date` / `end_date` timestamp filtering. |
| `network_edges(...)` | Emit the standard output schema. |

Bot policies accepted by the macros:

```text
include_bots, exclude_bots, only_bots, human_to_bot, bot_to_human
```

### Pattern: native edge slice

Use this when the desired network is already represented by HIN edges, such as
user-repo stars or repo-repo forks.

```sql
{{ config(materialized='table') }}

WITH starred_edges AS (
    {{ slice_edges(
        edge_types=['starred'],
        source_types=['user'],
        target_types=['repo'],
        bot_policy='exclude_bots',
        start_date='2022-01-01',
        end_date='2025-01-01'
    ) }}
)

{{ network_edges(
    relation='starred_edges',
    recipe_name='custom_star_user_repo',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'repo'",
    edge_type="'custom_starred'",
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_record_id': source_record_id})"
) }}
```

### Pattern: user-user projection over shared artifacts

Use this when users should be tied because they interacted with the same
artifact, repository, commit, file, or other context node.

```sql
{{ config(materialized='table') }}

WITH pr_comments AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS pull_request_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight,
        count(DISTINCT evidence_edge_id) AS n_events
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'pull_request'
      AND role = 'commented_on'
    GROUP BY left_node_id, right_node_id
),

projected AS (
    {{ project_bipartite(
        incidence_relation='pr_comments',
        left_col='user_node_id',
        right_col='pull_request_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

{{ network_edges(
    relation='projected',
    recipe_name='custom_pr_comment_cowork',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'co_commented_pr'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'pull_requests': context_node_ids})"
) }}
```

## Output contract

A custom SQL projection must materialize one table with these columns, in this
order:

```text
recipe_name, recipe_version,
source_node_id, source_node_type,
target_node_id, target_node_type,
directed, edge_type,
weight, weight_kind,
n_contexts, n_events,
first_seen_at, last_seen_at,
time_bin, bot_policy,
properties
```

`properties` must be JSON. Use DuckDB `to_json({...})` for structured metadata.
The exporter derives output nodes from `source_node_id/source_node_type` and
`target_node_id/target_node_type`, so projections that emit no edges also emit
no nodes. For nodes-only outputs, emit self-loop edges and remove those loops in
downstream analysis if needed.

## Naming

The SQL filename stem becomes the dbt model/table name. It must be a valid dbt
identifier: start with a letter or underscore, then use only letters, digits,
and underscores. If needed:

```bash
uv run hinge export-sql ad-hoc.sql --name ad_hoc --dataset <id> --format gml -o out.gml
```

## Validation checklist

Before running a custom projection, check that:

- the SQL file name or `--name` value is a valid dbt model name;
- every input model is referenced with `ref(...)`;
- the final query emits the standard `network_edges` schema;
- custom edge labels are stable and documented in the SQL file or accompanying notes;
- `properties` is valid JSON;
- the projection does not query unscoped store tables such as `nodes`, `edges`,
  or `contract_*` directly.

## Design properties

- no additional kernel protocol
- no registry or installation cycle for local projections
- full access to the HIN algebra used by cookbook models
- reproducible exports: custom SQL bytes are included in the projection fingerprint

## Extension path

A declarative YAML recipe compiler can target the same local-SQL execution path,
keeping SQL and YAML projections on one dbt-backed implementation.
