#!/bin/bash
set -e

TABLE_NAME="file-meta-data"

echo "Creating DynamoDB table: $TABLE_NAME..."
awslocal dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions \
        AttributeName=file_id,AttributeType=S \
    --key-schema \
        AttributeName=file_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

echo "Waiting for DynamoDB table to become active..."
awslocal dynamodb wait table-exists --table-name "$TABLE_NAME"

echo "Enabling TTL on attribute 'expires_at' for automated resource cleanup..."
awslocal dynamodb update-time-to-live \
    --table-name "$TABLE_NAME" \
    --time-to-live-specification "Enabled=true, AttributeName=expires_at"

echo "DynamoDB setup completed successfully!"