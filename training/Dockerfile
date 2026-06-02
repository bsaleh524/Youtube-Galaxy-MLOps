# Use CUDA base image so GPU passthrough works in k3d.
# On CPU-only systems (M1, Oracle ARM) the CUDA libs are unused but harmless.
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train.py .

# Pre-download the embedding model so the Job doesn't hit HuggingFace at runtime.
# Remove this if you want faster image builds and are okay with download at Job start.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('Alibaba-NLP/gte-large-en-v1.5', trust_remote_code=True)"

CMD ["python", "train.py"]
