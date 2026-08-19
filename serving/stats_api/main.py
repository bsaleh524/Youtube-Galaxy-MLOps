"""
Stats API
FastAPI service that reads from DuckDB (populated by train_stats.py).

Endpoints:
  GET /health                    — liveness probe
  GET /api/stats/top             — top creators by subscriber count, optionally filtered by cluster
  GET /api/stats/clusters        — cluster summary (archetype name, size, avg stats)
  GET /api/stats/creator/{name}  — single creator's stats + cluster info
  POST /api/admin/reload         — reload DuckDB (noop: the file is updated by the Job, not this service)
"""

import os

import duckdb
from fastapi import FastAPI, HTTPException, Header, Query

app = FastAPI(title="Galaxy Stats API", version="1.0.0")

DUCKDB_PATH  = os.environ.get("DUCKDB_PATH", "/data/youtube_stats.duckdb")
ADMIN_TOKEN  = os.environ.get("ADMIN_TOKEN", "changeme")


def _con() -> duckdb.DuckDBPyConnection:
    """Open a read-only connection. Callers must close it."""
    return duckdb.connect(DUCKDB_PATH, read_only=True)


@app.get("/health")
def health():
    try:
        con = _con()
        count = con.execute("SELECT COUNT(*) FROM creator_stats").fetchone()[0]
        con.close()
        return {"status": "ok", "row_count": count}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/api/stats/top")
def top_creators(
    limit: int = Query(default=20, le=200),
    cluster_id: int | None = Query(default=None),
):
    con = _con()
    where = f"WHERE stat_cluster_id = {cluster_id}" if cluster_id is not None else ""
    rows = con.execute(f"""
        SELECT youtuber_name, subscribers, video_views, uploads, category, country, stat_cluster_id
        FROM creator_stats
        {where}
        ORDER BY subscribers DESC
        LIMIT {limit}
    """).df()
    con.close()
    return rows.to_dict(orient="records")


@app.get("/api/stats/clusters")
def cluster_summary():
    con = _con()
    rows = con.execute("""
        SELECT
            stat_cluster_id,
            COUNT(*)                    AS creator_count,
            ROUND(AVG(subscribers))     AS avg_subscribers,
            ROUND(AVG(video_views))     AS avg_video_views,
            ROUND(AVG(uploads))         AS avg_uploads,
            MODE(category)              AS dominant_category
        FROM creator_stats
        GROUP BY stat_cluster_id
        ORDER BY avg_subscribers DESC
    """).df()
    con.close()
    return rows.to_dict(orient="records")


@app.get("/api/stats/creator/{name}")
def creator_stats(name: str):
    con = _con()
    rows = con.execute(
        "SELECT * FROM creator_stats WHERE youtuber_name ILIKE ? LIMIT 5",
        [f"%{name}%"],
    ).df()
    con.close()
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No creator matching '{name}'")
    return rows.to_dict(orient="records")


@app.post("/api/admin/reload")
def reload(x_admin_token: str = Header(default="")):
    """
    The stats API is read-only; the DuckDB file is written by the training Job.
    This endpoint exists so the Airflow DAG can call the same reload URL pattern
    as the embedding pipeline. It just confirms the file is accessible.
    """
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    try:
        con = _con()
        count = con.execute("SELECT COUNT(*) FROM creator_stats").fetchone()[0]
        con.close()
        return {"status": "ok", "row_count": count}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
