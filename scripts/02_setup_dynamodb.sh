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

echo "Creating DynamoDB table: $TABLE_NAME..."
aws --endpoint-url=$ENDPOINT dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions \
        AttributeName=file_id,AttributeType=S \
    --key-schema \
        AttributeName=file_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$AWS_DEFAULT_REGION"

echo "Waiting for DynamoDB table to become active..."
aws --endpoint-url=$ENDPOINT dynamodb wait table-exists --table-name "$TABLE_NAME"

echo "Enabling TTL on attribute 'expires_at' for automated resource cleanup..."
aws --endpoint-url=$ENDPOINT dynamodb update-time-to-live \
    --table-name "$TABLE_NAME" \
    --time-to-live-specification "Enabled=true, AttributeName=expires_at"

echo "DynamoDB setup completed successfully!"
