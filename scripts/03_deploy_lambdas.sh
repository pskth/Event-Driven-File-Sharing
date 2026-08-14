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

echo "=== Deploying Lambdas to LocalStack ==="

# 1. Zip Gatekeeper
echo "Zipping Gatekeeper..."
cd src/gatekeeper_api
zip -r function.zip app.py > /dev/null
cd ../..

# 2. Deploy Gatekeeper
echo "Deploying gatekeeper-function..."
aws --endpoint-url=$ENDPOINT lambda delete-function --function-name gatekeeper-function 2>/dev/null || true
aws --endpoint-url=$ENDPOINT lambda create-function \
    --function-name gatekeeper-function \
    --runtime python3.9 \
    --handler app.lambda_handler \
    --role arn:aws:iam::000000000000:role/dummy-role \
    --zip-file fileb://src/gatekeeper_api/function.zip \
    --environment Variables="{BUCKET_NAME=$BUCKET_NAME,TABLE_NAME=$TABLE_NAME}" > /dev/null

# 3. Zip Cleanup
echo "Zipping Automated Cleanup..."
cd src/automated_cleanup
zip -r function.zip app.py > /dev/null
cd ../..

# 4. Deploy Cleanup
echo "Deploying automated-cleanup-function..."
aws --endpoint-url=$ENDPOINT lambda delete-function --function-name automated-cleanup-function 2>/dev/null || true
aws --endpoint-url=$ENDPOINT lambda create-function \
    --function-name automated-cleanup-function \
    --runtime python3.9 \
    --handler app.lambda_handler \
    --role arn:aws:iam::000000000000:role/dummy-role \
    --zip-file fileb://src/automated_cleanup/function.zip \
    --environment Variables="{BUCKET_NAME=$BUCKET_NAME}" > /dev/null

# 5. Ensure TTL is enabled on the table (survives restarts)
echo "Ensuring TTL is enabled on $TABLE_NAME..."
aws --endpoint-url=$ENDPOINT dynamodb update-time-to-live \
    --table-name "$TABLE_NAME" \
    --time-to-live-specification "Enabled=true, AttributeName=expires_at" > /dev/null

# 6. Map DynamoDB Stream to Cleanup Lambda
echo "Mapping DynamoDB Stream to Cleanup Lambda..."
STREAM_ARN=$(aws --endpoint-url=$ENDPOINT dynamodb describe-table --table-name "$TABLE_NAME" --query "Table.LatestStreamArn" --output text)

aws --endpoint-url=$ENDPOINT lambda create-event-source-mapping \
    --function-name automated-cleanup-function \
    --event-source-arn $STREAM_ARN \
    --starting-position LATEST > /dev/null

echo "=== Deployment Complete ==="
