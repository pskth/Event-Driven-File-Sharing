#!/bin/bash
set -e

# Set dummy credentials required for LocalStack when using standard AWS CLI
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="us-east-1"

TABLE_NAME="file-meta-data"

echo "Creating DynamoDB table: $TABLE_NAME..."
aws --endpoint-url=http://localhost:4566 dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions \
        AttributeName=file_id,AttributeType=S \
    --key-schema \
        AttributeName=file_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

echo "Waiting for DynamoDB table to become active..."
aws --endpoint-url=http://localhost:4566 dynamodb wait table-exists --table-name "$TABLE_NAME"

echo "Enabling TTL on attribute 'expires_at' for automated resource cleanup..."
aws --endpoint-url=http://localhost:4566 dynamodb update-time-to-live \
    --table-name "$TABLE_NAME" \
    --time-to-live-specification "Enabled=true, AttributeName=expires_at"

echo "DynamoDB setup completed successfully!"