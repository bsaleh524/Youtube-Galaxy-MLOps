FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests beautifulsoup4 boto3

# Copy the existing Fandom scraper (unchanged from the original repo)
COPY fandom/my_combined.py .
COPY fandom/run.sh .
RUN chmod +x run.sh

CMD ["bash", "run.sh"]
