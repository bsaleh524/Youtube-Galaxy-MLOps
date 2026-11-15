"""
Galaxy MLOps — Streamlit Frontend
Updated version of the original Youtube-Galaxy-Streamlit-App.
Reads from the live API instead of a static Parquet GitHub Release.
"""

import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
PARQUET_URL = os.environ.get(
    "PARQUET_URL",
    # Falls back to the original static Parquet from the old repo if API not available
    "https://github.com/bsaleh524/Youtube-Galaxy-Streamlit-App/releases/download/v1.0/starmap_data.parquet",
)

st.set_page_config(page_title="YouTube Galaxy", layout="wide", page_icon="🌌")


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)   # cache for 1 hour — refreshes after Airflow pipeline runs
def load_starmap_data() -> pd.DataFrame:
    """Load the creator Parquet. Tries the live API first, falls back to static URL."""
    try:
        # Try to load from Oracle Object Storage via the API
        resp = requests.get(f"{API_BASE}/api/data/starmap", timeout=10)
        if resp.ok:
            import io
            return pd.read_parquet(io.BytesIO(resp.content))
    except Exception:
        pass

    # Fallback to static URL (works without the full backend running)
    return pd.read_parquet(PARQUET_URL, engine="pyarrow")


@st.cache_data(ttl=300)   # rankings refresh every 5 minutes
def load_rankings() -> dict:
    try:
        resp = requests.get(f"{API_BASE}/api/rankings", timeout=5)
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return {}


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("🌌 YouTube Galaxy")
st.caption("Creator clusters visualized by content similarity")

tab_galaxy, tab_chat, tab_rankings = st.tabs(["Galaxy", "Chat", "Rankings"])

# Load data
with st.spinner("Loading galaxy data..."):
    df = load_starmap_data()

# Ensure required columns
for col in ["x", "y", "z", "creator_id", "title", "cluster_id"]:
    if col not in df.columns:
        st.error(f"Missing column: {col}")
        st.stop()

if "cluster_name" not in df.columns:
    df["cluster_name"] = df["cluster_id"].astype(str)


# ── Tab 1: Galaxy Visualization ───────────────────────────────────────────────

with tab_galaxy:
    col_main, col_info = st.columns([3, 1])

    with col_main:
        # Search
        search_query = st.text_input("🔍 Search creator", value="", key="search")
        selected_cluster = st.selectbox(
            "Filter by cluster",
            options=["All"] + sorted(df["cluster_name"].unique().tolist()),
        )

        # Build display dataframe
        display_df = df.copy()
        display_df["size"] = 3
        display_df["color"] = display_df["cluster_name"]

        if search_query:
            mask = display_df["title"].str.contains(search_query, case=False, na=False)
            display_df.loc[mask, "size"] = 20

        if selected_cluster != "All":
            mask = display_df["cluster_name"] == selected_cluster
            display_df.loc[~mask, "color"] = "_dim"
            display_df.loc[mask, "size"] = display_df.loc[mask, "size"].clip(lower=6)

        fig = px.scatter_3d(
            display_df,
            x="x", y="y", z="z",
            color="color",
            hover_name="title",
            custom_data=["creator_id", "title", "cluster_name"],
            size="size",
            size_max=20,
            opacity=0.75,
            title=f"{len(df):,} creators across {df['cluster_id'].nunique()} clusters",
        )
        fig.update_layout(
            height=700,
            scene=dict(
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                zaxis=dict(visible=False),
                bgcolor="#0e1117",
            ),
            paper_bgcolor="#0e1117",
            font=dict(color="white"),
            showlegend=False,
            margin=dict(l=0, r=0, t=30, b=0),
            clickmode="event+select",
        )

        selected = st.plotly_chart(fig, on_select="rerun", use_container_width=True)

    with col_info:
        # Creator detail panel
        if selected and selected.get("selection", {}).get("points"):
            idx = selected["selection"]["points"][0]["point_index"]
            row = display_df.iloc[idx]

            if row.get("thumbnail"):
                st.image(row["thumbnail"], width=120)

            st.subheader(row["title"])
            st.caption(f"Cluster: {row['cluster_name']}")

            if row.get("youtube_url"):
                st.link_button("YouTube Channel", row["youtube_url"])

            if row.get("description"):
                st.write(str(row["description"])[:400] + "...")

            # Nearest neighbors
            st.divider()
            st.subheader("Similar creators")
            creator_row = df[df["creator_id"] == row["creator_id"]]
            if not creator_row.empty:
                import numpy as np
                coords = df[["x", "y", "z"]].values
                query = creator_row[["x", "y", "z"]].values[0]
                dists = np.linalg.norm(coords - query, axis=1)
                df["_dist"] = dists
                neighbors = df[df["creator_id"] != row["creator_id"]].nsmallest(5, "_dist")
                for _, n in neighbors.iterrows():
                    st.write(f"• {n['title']} ({n['cluster_name']})")
                df.drop(columns=["_dist"], inplace=True)
        else:
            st.info("Click a point in the galaxy to see creator details.")

        # Cluster distribution
        st.divider()
        cluster_counts = df["cluster_name"].value_counts().head(15)
        fig_bar = px.bar(
            x=cluster_counts.values,
            y=cluster_counts.index,
            orientation="h",
            title="Top clusters by size",
        )
        fig_bar.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_bar, use_container_width=True)


# ── Tab 2: Chat ───────────────────────────────────────────────────────────────

with tab_chat:
    st.subheader("Ask about the creators")
    st.caption("Powered by Weaviate + LLM. Examples: 'Who is most similar to MrBeast?', 'What do gaming commentators tend to talk about?'")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask a question about YouTube creators..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""

            try:
                import json
                with requests.post(
                    f"{API_BASE}/chat/query",
                    json={"question": prompt},
                    stream=True,
                    timeout=60,
                ) as resp:
                    for line in resp.iter_lines():
                        if line and line.startswith(b"data: "):
                            data = line[6:]
                            if data == b"[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if "token" in chunk:
                                    full_response += chunk["token"]
                                    placeholder.write(full_response + "▌")
                            except json.JSONDecodeError:
                                pass
                placeholder.write(full_response)
            except Exception as e:
                full_response = f"Chat service unavailable: {e}"
                placeholder.write(full_response)

            st.session_state.chat_history.append({"role": "assistant", "content": full_response})


# ── Tab 3: Rankings (Phase 2 placeholder) ────────────────────────────────────

with tab_rankings:
    st.subheader("Creator Rankings")
    st.info(
        "Live rankings are a **Phase 2** feature. "
        "When implemented, you'll see: Newest Added, Cluster Highlights, "
        "Sentiment Drift, and Content Shift rankings — all derived from "
        "Fandom wiki data without external APIs."
    )

    rankings = load_rankings()
    if rankings.get("newest_added"):
        st.subheader("🆕 Newest Added")
        st.dataframe(pd.DataFrame(rankings["newest_added"]))
