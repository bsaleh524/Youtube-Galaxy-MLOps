#!/bin/bash
# Entry point for the scraper Kubernetes Job.
# Runs the Fandom scraper, then uploads output to Oracle Object Storage.
set -euo pipefail

OUTPUT_FILE="/tmp/youtubers_data_combined.json"
RUN_DATE=$(date -u +%Y-%m-%d)

echo "=== Galaxy Fandom Scraper ==="
echo "Date: $RUN_DATE"

# Run the scraper
python my_combined.py --output "$OUTPUT_FILE"

CREATOR_COUNT=$(python -c "import json; data=json.load(open('$OUTPUT_FILE')); print(len(data))")
echo "Scraped $CREATOR_COUNT creators"

# Upload to Oracle Object Storage (S3-compatible)
if [ -n "${OCI_ENDPOINT_URL:-}" ]; then
    DEST_KEY="raw/fandom/$RUN_DATE/youtubers_data_combined.json"
    LATEST_KEY="raw/fandom/latest/youtubers_data_combined.json"

    python - <<EOF
import boto3, os

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["OCI_ENDPOINT_URL"],
    aws_access_key_id=os.environ["OCI_ACCESS_KEY"],
    aws_secret_access_key=os.environ["OCI_SECRET_KEY"],
)
bucket = os.environ["OUTPUT_BUCKET"]
s3.upload_file("$OUTPUT_FILE", bucket, "$DEST_KEY")
s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": "$DEST_KEY"}, Key="$LATEST_KEY")
print(f"Uploaded to s3://{bucket}/$DEST_KEY")
EOF
else
    echo "[LOCAL] OCI_ENDPOINT_URL not set — skipping upload (file at $OUTPUT_FILE)"
fi

# Write XCom for Airflow KubernetesPodOperator
mkdir -p /airflow/xcom
python -c "
import json
with open('/airflow/xcom/return.json', 'w') as f:
    json.dump({
        'creator_count': $CREATOR_COUNT,
        's3_path': 's3://${OUTPUT_BUCKET:-local}/raw/fandom/$RUN_DATE/youtubers_data_combined.json'
    }, f)
"

echo "Done."
