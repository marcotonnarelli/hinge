{{ config(materialized='table') }}

{{ build_incidence(
    left_type='user',
    right_type='artifact',
    edge_types=[
        'authored',
        'committed',
        'coauthored',
        'opened',
        'reviewed',
        'merged',
        'closed',
        'reopened',
        'commented_on',
        'review_commented_on',
        'pushed',
        'touched'
    ],
    weight_mode='event_count'
) }}
