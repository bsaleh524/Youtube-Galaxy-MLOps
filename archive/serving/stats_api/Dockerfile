FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.111.0 \
    uvicorn>=0.29.0 \
    duckdb>=0.10.0 \
    pandas>=2.0.0

COPY main.py .

EXPOSE 8002
# DUCKDB_PATH and ADMIN_TOKEN are injected via k8s Secret/ConfigMap
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
