"""
Feast feature view definitions for the Galaxy project.

Four views, each backed by a Parquet file written by train.py or the scraper:
  1. creator_profile   — basic metadata from the scraper
  2. creator_embedding — UMAP coordinates + embedding metadata from training
  3. creator_yt_stats  — Phase 2 stretch goal (no YouTube API for now)
  4. creator_ranking   — Phase 2 stretch goal
"""

import os
from datetime import timedelta

from feast import FeatureView, Field, FileSource
from feast.types import Float64, Int64, String

from entities import creator_entity

_DATA_DIR = os.environ.get("FEAST_DATA_DIR", "./data/features")


# ── View 1: Creator profile (from scraper output) ─────────────────────────────

creator_profile_source = FileSource(
    path=f"{_DATA_DIR}/profiles/profiles.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

creator_profile_fv = FeatureView(
    name="creator_profile",
    entities=[creator_entity],
    ttl=timedelta(days=7),
    schema=[
        Field(name="display_name", dtype=String),
        Field(name="cluster_id", dtype=Int64),
        Field(name="cluster_name", dtype=String),
        Field(name="thumbnail_url", dtype=String),
        Field(name="youtube_url", dtype=String),
    ],
    source=creator_profile_source,
    tags={"team": "galaxy", "version": "v1"},
)


# ── View 2: Embeddings (from training output) ─────────────────────────────────
# The full 1024-dim vector lives in Weaviate (too large for Redis).
# Feast stores the UMAP projection (x/y/z) and the model version that produced them.

creator_embedding_source = FileSource(
    path=f"{_DATA_DIR}/embeddings/embeddings.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

creator_embedding_fv = FeatureView(
    name="creator_embedding",
    entities=[creator_entity],
    ttl=timedelta(days=7),
    schema=[
        Field(name="umap_x", dtype=Float64),
        Field(name="umap_y", dtype=Float64),
        Field(name="umap_z", dtype=Float64),
        Field(name="mlflow_run_id", dtype=String),
    ],
    source=creator_embedding_source,
    tags={"team": "galaxy", "version": "v1"},
)


# ── Views 3 & 4: Phase 2 placeholders ────────────────────────────────────────
# Uncomment and implement when building Phase 2 rankings.
# These will use historical bio-text snapshots + DistilBERT sentiment scores.
#
# creator_ranking_fv = FeatureView(
#     name="creator_ranking",
#     entities=[creator_entity],
#     ttl=timedelta(days=1),
#     schema=[
#         Field(name="newest_added_score", dtype=Float64),
#         Field(name="cluster_highlight_score", dtype=Float64),
#         Field(name="sentiment_drift_score", dtype=Float64),   # Phase 2
#         Field(name="content_shift_score", dtype=Float64),     # Phase 2
#     ],
#     source=...,
# )
