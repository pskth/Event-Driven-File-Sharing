#!/bin/bash
set -e

export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="us-east-1"

BUCKET_NAME="secure-file-share-bucket"

echo "Creating S3 bucket: $BUCKET_NAME..."
aws --endpoint-url=http://localhost:4566 s3api create-bucket --bucket "$BUCKET_NAME" --region us-east-1

echo "Applying strict public access block to secure the bucket..."
aws --endpoint-url=http://localhost:4566 s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "S3 setup completed successfully!"