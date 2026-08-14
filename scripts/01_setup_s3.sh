#!/bin/bash
set -e

# Load configuration from .env file
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

echo "Creating S3 bucket: $BUCKET_NAME..."
aws --endpoint-url=$ENDPOINT s3api create-bucket --bucket "$BUCKET_NAME" --region "$AWS_DEFAULT_REGION" 2>/dev/null \
    || echo "Bucket already exists — continuing."

echo "Applying strict public access block to secure the bucket..."
aws --endpoint-url=$ENDPOINT s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# CORS allows the browser (served from the Flask app's origin, e.g.
# localhost:5000) to PUT/GET objects directly against LocalStack S3
# (localhost:4566) without a proxy. This is intentionally permissive
# (AllowedOrigins: "*") because this is a same-laptop local demo — see
# docs/WEB_APP_DESIGN_DECISIONS.md for why this must be tightened before
# any real deployment.
echo "Configuring CORS for browser-based direct uploads/downloads..."
aws --endpoint-url=$ENDPOINT s3api put-bucket-cors \
    --bucket "$BUCKET_NAME" \
    --cors-configuration "file://$(dirname "$0")/cors-config.json"

echo "S3 setup completed successfully!"
