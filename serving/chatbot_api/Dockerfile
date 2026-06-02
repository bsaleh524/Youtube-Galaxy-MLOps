FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py rag_pipeline.py ./

# Feast feature repo is mounted as a volume in k8s (see k8s/chatbot-api/deployment.yaml)
ENV FEAST_REPO_PATH=/app/features

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
