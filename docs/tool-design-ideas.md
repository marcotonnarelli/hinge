# Tool design ideas: GitHub Network Composer

Working notes for a tool-demo paper. This document focuses on the *network-construction logic* and the researcher-facing interface. Engineering details are intentionally lightweight: the current assumption is that we keep raw GitHub JSONL as the durable source, query it through DuckDB, normalize it into a small typed graph schema, and then export ordinary node/edge lists for downstream tools.

## Design premise

Researchers should be able to ask for a network in domain language:

```bash
ghnet build pr-review --repo pandas-dev/pandas --mode author-to-reviewer
```

rather than writing the plumbing themselves:

```sql
SELECT ...
FROM actions
WHERE action IN (...)
JOIN ...
GROUP BY ...
```

The tool's core contribution is to hide the event-to-network transformation while making it auditable. Users choose the network, filters, projection mode, and weighting scheme; the tool records exactly which raw actions and transformations produced the edge list.

## Data strategy

Use the action JSONL as the source of truth.

```text
14914741/
  NumFocus_Jan22-Dec24_GH_Actions.jsonl
  NumFocus_Jan22-Dec24_GH_Activities.jsonl
  action-schema.json
  activity-schema.json
```

The `Activities` file can be useful for convenience, but it mostly groups actions already available in the action stream. The initial tool should treat `Actions.jsonl` as canonical.

### Storage pattern

```text
Raw JSONL
   ↓
DuckDB raw table
   ↓
normalized HIN tables
   ↓
recipe-specific network views
   ↓
node list + edge list exports
```

The intended workflow is:

1. Ingest raw JSONL into DuckDB.
2. Normalize users, repositories, artifacts, and typed edges.
3. Build requested networks as views over the normalized HIN.
4. Export edge lists / node lists.
5. Optionally export to GraphML, GEXF, Parquet, CSV, NetworkX, igraph, graph-tool, etc.

Once we have a clean edge list, we are mostly done. Export formats are adapters, not the core scientific problem.

## Constructible networks from the current data

The current scrape supports event-derived GitHub networks, not the full catalogue in `types_of_networks.md`.

| Network | Status | Main source actions |
|---|---:|---|
| Star network | supported | `StarRepository` |
| Fork network | supported | `ForkRepository` |
| Pull-request review network | supported | `OpenPullRequest`, `CreatePullRequestReview`, `CreatePullRequestComment`, `CreatePullRequestReviewComment`, `MergePullRequest`, `ClosePullRequest`, `ReopenPullRequest` |
| Issue/comment network | supported | `OpenIssue`, `CreateIssueComment`, `CloseIssue`, `ReopenIssue` |
| Developer--repository affiliation | supported | configurable contribution actions |
| Repo--repo shared-contributor network | supported as projection | projected from developer--repository affiliation |
| User--user co-participation networks | supported as projection | projected from user--issue or user--PR incidence |

Unsupported from this scrape alone:

| Network | Reason unavailable |
|---|---|
| Follow | no follower/following data |
| Watch | no subscriber/watch data |
| @-mention network | no body text or timeline mention events |
| Artifact-reference network | no `#N` references or timeline reference events |
| True co-commit / co-edit network | no commit SHAs, parent graph, touched files, or diffs |

The tool should expose unavailable networks through `ghnet available` and `ghnet explain`, but refuse to silently approximate them.

## Canonical HIN model

The normalized substrate is a heterogeneous information network (HIN):

```text
User
Repo
Artifact
```

where `Artifact` is subtyped as:

```text
pull_request
issue
comment
review
push
release
branch
wiki_page
```

The practical implementation can use relational tables, not an in-memory graph.

### Raw action table

```text
raw_actions
-----------
event_id          string
action            string
date              timestamp
actor_id          integer
actor_login       string
repo_id           integer
repo_name         string
repo_org          string
repo_org_id       integer
details_json      json
```

### Node tables

```text
users
-----
user_id
login
is_bot_guess

repos
-----
repo_id
full_name
org
org_id

artifacts
---------
artifact_key       -- e.g. pr:1076700899, issue:1084229330
artifact_type      -- pull_request, issue, comment, review, push
repo_id
number             -- issue/PR number where available
github_id          -- GitHub API id where available
title
state
created_at
updated_at
closed_at
merged_at
attrs_json
```

### Edge table

One generic edge table is easiest to reason about in the paper:

```text
edges
-----
src_type          -- user, repo, artifact
src_id
src_label
dst_type
dst_id
dst_label
edge_type         -- starred, fork_of, opened, commented_on, reviewed, contains, etc.
timestamp
event_id
repo_id
weight
attrs_json
```

Implementation can split this into typed tables if needed for performance, but the conceptual model should be one typed edge stream.

## Researcher-facing interfaces

### 1. Availability check

```bash
ghnet available --data 14914741/
```

Example output:

```text
Available from this dataset:
  ✓ star
  ✓ fork
  ✓ pr-review
  ✓ issue-comment
  ✓ dev-repo
  ✓ repo-repo-shared-contributors
  ✓ pr-user-projection
  ✓ issue-user-projection

Unavailable:
  ✗ follow              requires follower/following data
  ✗ watch               requires subscriber data
  ✗ mention             requires comment bodies or timeline events
  ✗ artifact-artifact-reference  requires body/timeline reference data
  ✗ co-commit           requires git commit-level data
```

### 2. Explain a network recipe

```bash
ghnet explain pr-review
```

Example output:

```text
Network: pr-review
Base incidence: User × PullRequest
Actions used:
  - OpenPullRequest
  - CreatePullRequestReview
  - CreatePullRequestComment
  - CreatePullRequestReviewComment
  - MergePullRequest
  - ClosePullRequest
  - ReopenPullRequest
Supported modes:
  - bipartite-user-pr
  - author-to-reviewer
  - user-projection
Default weighting:
  - distinct_prs
Caveats:
  - Review state unavailable in the current scrape.
  - Comment/review text unavailable in the current scrape.
```

### 3. Build a network

```bash
ghnet build pr-review \
  --data 14914741/ \
  --repo pandas-dev/pandas \
  --since 2023-01-01 \
  --until 2024-12-31 \
  --mode author-to-reviewer \
  --weight distinct_prs \
  --exclude-bots \
  --out outputs/pandas_pr_review_edges.parquet
```

### 4. YAML config for reproducibility

```yaml
network: pr-review
mode: author-to-reviewer

data:
  path: 14914741/

filters:
  repos:
    - pandas-dev/pandas
  since: 2023-01-01
  until: 2024-12-31
  exclude_bots: true

weighting:
  method: distinct_prs

projection:
  min_weight: 2
  weight: shared_count

output:
  edges: outputs/pandas_pr_review_edges.parquet
  nodes: outputs/pandas_pr_review_nodes.parquet
  metadata: outputs/pandas_pr_review_metadata.json
```

### 5. Python API

```python
import ghnet

ds = ghnet.Dataset("14914741/")

edges, nodes = (
    ds.network("pr-review")
      .repo("pandas-dev/pandas")
      .between("2023-01-01", "2024-12-31")
      .mode("author-to-reviewer")
      .weight("distinct_prs")
      .exclude_bots()
      .to_tables()
)
```

## Core network-science transformations

The tool needs only a small number of graph operations.

### 1. Slice

Select a subset of the HIN by node type, edge type, action type, time window, repository, organization, or actor class.

Example:

```text
all User--Artifact edges
  → User--PullRequest edges
  → only edge_type in {opened, reviewed, commented_on}
```

### 2. Aggregate

Collapse repeated events into a weighted edge.

Example:

```text
User reviewed PR X three times
  → User --reviewed--> PR X, weight = 3
```

Aggregation choices are network-science choices, not just engineering choices. Possible edge weights include:

```text
event_count
active_days
distinct_artifacts
distinct_repos
sum_push_commit_count
binary
```

### 3. Project

Convert a bipartite incidence relation into a one-mode network.

Example:

```text
User × Repo
  → Repo × Repo shared-contributor network
```

or:

```text
User × Issue
  → User × User co-participation network
```

Projection needs explicit weighting rules. The default should be the most transparent construction: **shared count**. That is, after converting the base incidence relation to the chosen unit of analysis, the projected edge weight is the number of distinct shared neighbors.

Examples:

```text
Repo--repo projection from User × Repo:
  weight(repo_a, repo_b) = number of users active in both repos

User--user projection from User × Issue:
  weight(user_a, user_b) = number of issues both users participated in
```

The tool should avoid built-in statistical normalizations such as Jaccard, cosine similarity, association strength, or resource allocation. Those are downstream analytic choices. The tool's job is to produce honest edge lists with interpretable weights.

Projection weight modes:

```text
shared_count        -- number of distinct shared contexts; default
event_weighted      -- weighted projection using event counts in each shared context
```

Important convention: `shared_count` counts **distinct shared contexts**, not raw event multiplicities. If Alice comments 10 times on Issue 1 and Bob comments once on Issue 1, their issue co-participation shared count is still 1 issue, not 10 pairwise comment combinations.

If the user explicitly requests `event_weighted`, then repeated actions do count. In matrix terms, this is the weighted projection of an incidence matrix whose cells contain event counts.

### 4. Filter / sparsify

Projected networks can become dense very quickly. The tool should warn about this and expose explicit user-selected filters:

```text
min_weight
min_shared_neighbors
exclude_bots
exclude_high_activity_actors
```

Example risk:

```text
500 users on one issue → 124,750 user-user projection edges
```

The tool should not silently downweight, normalize, or drop high-degree artifacts by default. It can expose simple graph-construction filters such as `--min-shared` or `--min-weight`, and it should warn when a requested projection will create a very dense graph.

### 5. Temporal slicing

Every edge from the action stream has a timestamp. The tool should make time a first-class option:

```bash
ghnet build dev-repo --bin month
```

Possible temporal outputs:

```text
static graph over full window
time-sliced edge lists, e.g. month-by-month
event stream with timestamps preserved
rolling-window graphs
```

The default should probably be a static graph over the requested time window, with the option to emit temporal bins.

## Network recipes

## Recipe: star

### Network-science object

A directed bipartite attention network:

```text
User → Repo
```

### Construction

Use action:

```text
StarRepository
```

Create edge:

```text
actor --starred--> repository
```

### Modes

```text
bipartite-user-repo
repo-projection      -- repos co-starred by users
user-projection      -- users with overlapping starred repos
```

### Recommended default

Use the bipartite graph as the canonical output. Label it as a **star-event network** or **star-acquisition network**, because the current scrape has star events but not unstar events.

## Recipe: fork

### Network-science object

A directed repo--repo lineage network:

```text
ForkRepo → ParentRepo
```

Also optionally a user-mediated fork activity network:

```text
User → ForkRepo → ParentRepo
```

### Construction

Use action:

```text
ForkRepository
```

Create edges:

```text
fork_repo --fork_of--> parent_repo
actor --created_fork--> fork_repo
```

### Modes

```text
repo-fork-tree
user-fork-activity
```

### Recommended default

The default should be the directed repo-fork tree.

## Recipe: PR review

### Network-science object

Base incidence:

```text
User × PullRequest
```

Typed user roles:

```text
opened
commented_on
reviewed
review_commented_on
merged
closed
reopened
```

### Construction

Use actions:

```text
OpenPullRequest
CreatePullRequestComment
CreatePullRequestReview
CreatePullRequestReviewComment
MergePullRequest
ClosePullRequest
ReopenPullRequest
```

Create edges:

```text
PR author --opened--> PR
actor --commented_on--> PR
actor --reviewed--> PR
actor --review_commented_on--> PR
actor --merged--> PR
actor --closed--> PR
actor --reopened--> PR
repo --contains--> PR
```

### Modes

#### `bipartite-user-pr`

Preserves the most information:

```text
User ↔ PullRequest
```

#### `author-to-reviewer`

Directed user-user graph:

```text
PR author → reviewer/commenter
```

This captures who receives review/comment attention from whom.

Potential edge weights:

```text
distinct_prs          -- default; number of PRs connecting author and reviewer/commenter
event_weighted        -- count review/comment events connecting author and reviewer/commenter
review_event_count
review_comment_count
all_pr_interaction_count
```

#### `reviewer-co-participation`

Undirected user-user graph:

```text
Reviewer A -- Reviewer B
```

Users are connected when they review/comment on the same PR.

### Recommended default

Default mode:

```text
author-to-reviewer
```

Default weight:

```text
distinct_prs
```

Rationale: event counts can overweight long arguments on one PR; distinct PR count better captures repeated collaboration/review relation across artifacts.

### Caveats

The current scrape lacks review state, so the tool cannot distinguish approvals from change requests.

## Recipe: issue-comment

### Network-science object

Base incidence:

```text
User × Issue
```

Typed user roles:

```text
opened
commented_on
closed
reopened
```

### Construction

Use actions:

```text
OpenIssue
CreateIssueComment
CloseIssue
ReopenIssue
```

Create edges:

```text
issue author --opened--> Issue
actor --commented_on--> Issue
actor --closed--> Issue
actor --reopened--> Issue
repo --contains--> Issue
```

### Modes

#### `bipartite-user-issue`

Preserves the most information.

#### `user-co-participation`

Undirected user-user projection:

```text
User A -- User B
```

Users are connected if they participate in the same issue.

#### `opener-to-responder`

Directed user-user graph:

```text
Issue opener → commenter/closer
```

This may be useful for maintainer-response questions but should be documented as more interpretive.

### Recommended default

Default mode:

```text
bipartite-user-issue
```

Rationale: issue threads vary enormously in size and function. The bipartite object preserves more structure and avoids overclaiming that co-commenting necessarily means collaboration.

## Recipe: dev-repo affiliation

### Network-science object

A bipartite affiliation network:

```text
User × Repo
```

This captures participation in repositories.

### Construction

Aggregate user actions by repo.

Default included actions:

```text
PushCommits
OpenPullRequest
CreatePullRequestReview
CreatePullRequestComment
CreatePullRequestReviewComment
MergePullRequest
OpenIssue
CreateIssueComment
CloseIssue
ReopenIssue
CommentCommit
```

Default excluded actions:

```text
StarRepository
ForkRepository
CreateBranch
DeleteBranch
CreateTag
DeleteTag
ManageWikiPage
PublishRelease
MakeRepositoryPublic
CreateRepository
AddMember
```

The inclusion/exclusion boundary is a network-science decision. The default should represent *contribution*, not attention or repository administration.

### Weight options

```text
event_count
active_days
distinct_prs
distinct_issues
sum_push_commit_count
weighted_activity_score
binary
```

### Recommended default

Default weight:

```text
event_count
```

Rationale: simplest and most transparent for a first tool demo. Researchers can later rescale or transform edge weights as appropriate for their analysis.

Useful alternatives:

```text
active_days
binary
weighted_activity_score
```

## Recipe: repo-repo-shared-contributors

### Network-science object

A one-mode repo projection induced by shared contributors:

```text
Repo × Repo
```

Base incidence:

```text
User × Repo
```

Projection:

```text
A_RepoRepo = B_UserRepo^T B_UserRepo
```

where `B` is the user--repo incidence or weighted affiliation matrix.

### Construction

1. Build `dev-repo` affiliation graph.
2. Optionally filter users/bots/high-degree actors.
3. Project onto repos.
4. Weight repo--repo edges.

### Weight options

```text
shared_user_count      -- default; number of contributors shared by two repos
event_weighted         -- weighted projection using user--repo event counts
```

### Recommended default

Default weight:

```text
shared_user_count
```

Rationale: most honest and transparent. A repo--repo edge means exactly "these two repositories share N contributors". If researchers want size correction or similarity measures, they can compute those downstream from the exported edge list and node attributes.

## Recipe: user co-participation in PRs/issues

### Network-science object

One-mode user projection from an artifact incidence graph:

```text
User × Artifact → User × User
```

Potential artifacts:

```text
pull_request
issue
```

### Construction

1. Build user--PR or user--issue incidence.
2. Decide which user roles count.
3. Project onto users.
4. Weight edges as either distinct shared contexts or event-weighted shared contexts.

### Projection risk

Large issues/PRs can create artificial cliques. The tool should make this visible rather than silently correcting it. Optional construction filters:

```text
min_shared_artifacts: configurable
min_weight: configurable
exclude_bots: configurable
```

### Recommended default

Default weight:

```text
shared_artifact_count
```

Optional weight:

```text
event_weighted
```

Rationale: most honest and transparent. A user--user edge means exactly "these two users co-participated in N issues/PRs". If researchers want to account for repeated activity within the same issue/PR, they can request `event_weighted`. If they want statistical normalization, that belongs downstream, not inside this tool.

## Network specification object

Internally, each recipe can be represented as a network spec:

```yaml
name: pr-review
base: user-artifact
artifact_type: pull_request
allowed_edge_types:
  - opened
  - reviewed
  - commented_on
  - review_commented_on
modes:
  - bipartite-user-pr
  - author-to-reviewer
  - reviewer-co-participation
default_mode: author-to-reviewer
default_weight: distinct_prs
caveats:
  - Review state unavailable.
  - Comment bodies unavailable.
```

The query planner maps this spec onto DuckDB SQL.

## DuckDB implementation sketch

The tool can materialize the normalized layer once:

```sql
CREATE TABLE raw_actions AS
SELECT * FROM read_json_auto('14914741/NumFocus_Jan22-Dec24_GH_Actions.jsonl');
```

Then create views/tables:

```sql
CREATE TABLE users AS ...;
CREATE TABLE repos AS ...;
CREATE TABLE artifacts AS ...;
CREATE TABLE edges AS ...;
```

Recipe outputs are SQL views over `edges`.

Example conceptual projection:

```sql
-- user-repo affiliation, then repo-repo projection
WITH user_repo AS (
  SELECT
    src_id AS user_id,
    repo_id,
    COUNT(*) AS w
  FROM edges
  WHERE src_type = 'user'
    AND dst_type IN ('repo', 'artifact')
    AND edge_type IN ('pushed', 'opened_pr', 'reviewed_pr', 'commented_issue')
  GROUP BY 1, 2
)
SELECT
  a.repo_id AS repo_a,
  b.repo_id AS repo_b,
  COUNT(*) AS shared_users
FROM user_repo a
JOIN user_repo b
  ON a.user_id = b.user_id
 AND a.repo_id < b.repo_id
GROUP BY 1, 2;
```

Actual implementation should use recipe templates rather than hand-written SQL per user.

## Output contract

Every network build should produce:

```text
nodes.parquet/csv
edges.parquet/csv
metadata.json
```

### Edge list

```text
source
target
directed
weight
edge_type
first_seen
last_seen
event_count
attrs_json
```

### Node list

```text
node_id
node_type
label
attrs_json
```

### Metadata

```json
{
  "network": "pr-review",
  "mode": "author-to-reviewer",
  "actions_used": [
    "OpenPullRequest",
    "CreatePullRequestReview",
    "CreatePullRequestComment",
    "CreatePullRequestReviewComment"
  ],
  "filters": {
    "repos": ["pandas-dev/pandas"],
    "since": "2023-01-01",
    "until": "2024-12-31",
    "exclude_bots": true
  },
  "weighting": "distinct_prs",
  "projection": null,
  "caveats": [
    "Review state unavailable in source data.",
    "Comment text unavailable in source data."
  ],
  "node_count": 0,
  "edge_count": 0
}
```

## Design principle: defaults should be conservative

The tool-demo claim should not be that every event stream can be turned into a meaningful social network automatically. The better claim is:

> We make the construction explicit, reproducible, and difficult to misuse.

Recommended defaults:

```text
Prefer bipartite outputs where interpretation is ambiguous.
Use shared-count projection weights by default.
Offer event-weighted projection as an explicit option where repeated events are substantively meaningful.
Use event_count for developer--repository affiliation by default.
Do not implement statistical normalization inside the tool.
Do not silently downweight or filter projected edges.
Expose bot filtering as an explicit flag.
Flatten time into one static graph by default, with temporal bins as an explicit option.
Emit provenance for every graph.
Refuse unsupported networks rather than approximating silently.
```

## Open network-science design choices

These are the decisions we should settle before implementation.

### 1. Projection weighting

For one-mode projections, what should be the default?

Options:

```text
shared_count      -- default; number of distinct shared contexts
event_weighted    -- optional; weighted projection using event counts
```

Current decision:

```text
Use shared_count as the default for all one-mode projections.
Offer event_weighted as an explicit option for user--user and other projected co-participation networks where repeated events are substantively meaningful.
Do not include built-in Jaccard, cosine, association-strength, or resource-allocation normalization.
```

Rationale: shared count is the most honest default. It reports the direct combinatorial fact induced by the bipartite graph. Event-weighted projection is still a construction choice, not a statistical normalization, so it can be useful when users want repeated interactions within the same context to contribute to tie strength. Any further scaling, normalization, thresholding, or modeling belongs downstream.

### 2. Contribution weighting for dev--repo affiliation

What does it mean for a user to be affiliated with a repo?

Possible defaults:

```text
binary              -- user did anything in repo
active_days         -- number of days with contribution activity
event_count         -- number of contribution events
weighted_activity   -- hand-weighted action types
```

Current decision:

```text
event_count
```

Rationale: simplest and easiest to audit. Other contribution weights can be exposed as options.

### 3. Directionality

Some networks are naturally directed:

```text
star: user → repo
fork: fork → parent
author-to-reviewer: author → reviewer
opener-to-responder: opener → responder
```

But co-participation projections are usually undirected. The tool should force each recipe to declare directionality rather than infer it casually.

### 4. Hyperedge handling

Issues and PRs are really group interaction settings. Projecting them creates cliques. We need a default stance:

```text
preserve bipartite graph by default
project only on request
project with explicit minimum shared-context filters
project with explicit event-weighted edges
```

### 5. Bot and automation filtering

Available bot signal is weak: mostly login strings. Bot handling should therefore be explicit rather than hidden.

Options:

```text
--include-bots      keep all actors
--exclude-bots      remove obvious bots using login heuristics
--only-bots         keep only obvious bots
```

Open decision: whether `--include-bots` or `--exclude-bots` should be the default. This matters because bots are substantively important in some PR-review questions but noise in many collaboration networks.

### 6. Time

The data is naturally temporal. Should the default output be:

```text
static graph over the selected window
time-sliced graphs
timestamped edge stream
```

Current decision:

```text
flatten time into one static graph by default
provide temporal bins / rolling windows as explicit options
```

### 7. High-degree artifacts and hairball prevention

For user-user projections, we may need optional thresholds:

```text
min_shared_artifacts
min_weight
```

These thresholds are not just performance choices; they change the social interpretation of the graph. They should therefore be explicit user choices, not recipe defaults hidden inside the tool.

### 8. Naming conventions

We should be careful with labels:

```text
star-event network, not complete stargazer network
issue co-participation, not necessarily collaboration
PR review interaction, not necessarily approval network
shared-contributor repo network, not general repo influence network
```

Good naming is part of scientific validity.
