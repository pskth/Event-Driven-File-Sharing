#!/bin/bash
set -e

export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="us-east-1"
ENDPOINT="http://localhost:4566"

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
    --environment Variables="{BUCKET_NAME=secure-file-share-bucket,TABLE_NAME=file-meta-data}" > /dev/null

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
    --environment Variables="{BUCKET_NAME=secure-file-share-bucket}" > /dev/null

# 5. Ensure TTL is enabled on the table (survives restarts)
echo "Ensuring TTL is enabled on file-meta-data..."
aws --endpoint-url=$ENDPOINT dynamodb update-time-to-live \
    --table-name file-meta-data \
    --time-to-live-specification "Enabled=true, AttributeName=expires_at" > /dev/null

# 6. Map DynamoDB Stream to Cleanup Lambda
echo "Mapping DynamoDB Stream to Cleanup Lambda..."
STREAM_ARN=$(aws --endpoint-url=$ENDPOINT dynamodb describe-table --table-name file-meta-data --query "Table.LatestStreamArn" --output text)

aws --endpoint-url=$ENDPOINT lambda create-event-source-mapping \
    --function-name automated-cleanup-function \
    --event-source-arn $STREAM_ARN \
    --starting-position LATEST > /dev/null

echo "=== Deployment Complete ==="
