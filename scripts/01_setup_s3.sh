#!/bin/bash
set -e

BUCKET_NAME="secure-file-share-bucket"

echo "Creating S3 bucket: $BUCKET_NAME..."
awslocal s3api create-bucket --bucket "$BUCKET_NAME" --region us-east-1

echo "Applying strict public access block to secure the bucket..."
awslocal s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "S3 setup completed successfully!"