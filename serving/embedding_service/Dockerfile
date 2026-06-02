FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Pre-download model weights (same model as training — shared cache benefits both)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('Alibaba-NLP/gte-large-en-v1.5', trust_remote_code=True)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
