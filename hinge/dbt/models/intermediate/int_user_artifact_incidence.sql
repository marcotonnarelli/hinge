{{ config(materialized='table') }}

{{ build_incidence(
    left_type='user',
    right_type='artifact',
    edge_types=['opened', 'reviewed', 'merged', 'closed', 'reopened', 'commented_on', 'review_commented_on', 'pushed'],
    weight_mode='event_count'
) }}
