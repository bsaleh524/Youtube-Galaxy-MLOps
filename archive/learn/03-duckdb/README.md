# Module 03 — DuckDB

DuckDB is an embedded OLAP database. It runs inside your Python process — no server to start, no connection string to manage. You import it, open a file (or run in memory), and query with SQL.

## Why it fits this project

The Kaggle stats data (~1 000 rows) is written once per pipeline run and read many times by the frontend. That is a pure batch-analytics workload. DuckDB handles it with zero operational overhead:

- no separate pod or service
- can read CSV and Parquet directly (including from S3) without loading into memory first
- fast enough for every query the stats API will run
- the `.duckdb` file lives on a PersistentVolumeClaim in k8s; the training Job writes it, the stats API reads it

Postgres would need its own Deployment, PVC, credentials, connection pool, and health checks — none of which adds learning value for a ~1 000-row, read-mostly dataset.

## Concepts section

### How DuckDB is different from SQLite

SQLite is row-oriented: fast for point-lookups and transactional writes. DuckDB is column-oriented: fast for aggregations, filters, and analytics over many rows. Both are embedded (no server). Choose SQLite for operational data; choose DuckDB for analytics — which is what this project needs.

### In-process vs. file-backed

```python
import duckdb

# In-memory (gone when the process exits)
con = duckdb.connect()

# File-backed (persists across restarts)
con = duckdb.connect("youtube_stats.duckdb")
```

### Reading CSV and Parquet directly

DuckDB can query files without loading them first:

```python
# Query a CSV without creating a table
con.execute("SELECT * FROM read_csv('global_youtube_statistics.csv') LIMIT 5").df()

# Register a Parquet as a view
con.execute("CREATE VIEW stats AS SELECT * FROM 'features/stats.parquet'")
```

### Creating and querying a real table

```python
import duckdb
import pandas as pd

con = duckdb.connect("youtube_stats.duckdb")

con.execute("""
    CREATE TABLE IF NOT EXISTS creator_stats (
        youtuber_name   TEXT,
        subscribers     BIGINT,
        video_views     BIGINT,
        uploads         INTEGER,
        category        TEXT,
        country         TEXT,
        stat_cluster_id INTEGER
    )
""")

df = pd.read_csv("global_youtube_statistics.csv")
con.execute("INSERT INTO creator_stats SELECT youtuber, subscribers, video views, uploads, category, Country, NULL FROM df")

# Aggregation query
top = con.execute("""
    SELECT category, AVG(subscribers) AS avg_subs
    FROM creator_stats
    GROUP BY category
    ORDER BY avg_subs DESC
    LIMIT 10
""").df()
```

## Exercises

**Exercise 1** — Load the Kaggle CSV into DuckDB and run three aggregation queries:
  - Top 10 categories by average subscriber count
  - Countries with more than 10 creators in the dataset
  - Distribution of upload frequency (histogram buckets: <10, 10–50, 50–200, 200+)

**Exercise 2** — Add a `stat_cluster_id` column. Write a short script that runs KMeans (k=10) on `[subscribers, video_views, uploads]` after log-scaling, then updates the rows with the cluster assignments.

**Exercise 3** — Expose a query via FastAPI. Create a `/stats/top-by-category` endpoint that reads from the DuckDB file and returns JSON. Verify it works when two processes (a writer and a reader) access the file sequentially (not simultaneously).

## How this maps to the Galaxy project

| Where | What |
|---|---|
| `training/train_stats.py` | Reads the Kaggle CSV, trains KMeans, writes cluster labels back to DuckDB |
| `serving/stats_api/main.py` | FastAPI service that queries DuckDB to serve the Stats tab |
| `k8s/stats-api/deployment.yaml` | Deployment + PVC mount for the DuckDB file |
| `dags/stats_pipeline_dag.py` | Airflow DAG that triggers `train_stats.py` on a schedule |

After completing this module, read `training/train_stats.py` and `serving/stats_api/main.py`.
