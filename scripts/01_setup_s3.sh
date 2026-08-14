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
aws --endpoint-url=$ENDPOINT s3api create-bucket --bucket "$BUCKET_NAME" --region "$AWS_DEFAULT_REGION"

echo "Applying strict public access block to secure the bucket..."
aws --endpoint-url=$ENDPOINT s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "S3 setup completed successfully!"
