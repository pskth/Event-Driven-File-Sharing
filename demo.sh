#!/bin/bash
# ==============================================================================
# DEMO: Two-Phase Commit + Automated S3 Cleanup via DynamoDB TTL
#
# ABOUT "filename" vs the actual file:
#   The "filename" field you send to the Gatekeeper is just metadata — a label
#   stored in DynamoDB so you know what the file was called. The S3 key is
#   always uploads/<uuid>, regardless of the name. So the actual file you
#   upload via curl can be any local file. Here we create top_secret.txt so
#   the label and the local file match for clarity.
# ==============================================================================

export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="us-east-1"
ENDPOINT="http://localhost:4566"

# --- Create the file we are going to upload -----------------------------------
echo "TOP SECRET: Launch codes 1-2-3-4-5" > top_secret.txt
echo "(Created top_secret.txt — this is the actual local file that will be uploaded)"

echo ""
echo "==========================================================="
echo "  1. Requesting Upload Link (Gatekeeper / Phase 1 + 2)"
echo "==========================================================="
# expiration_seconds=15 means:
#   - the Presigned URL is valid for 15 seconds
#   - the DynamoDB TTL fires 15 seconds from now

aws --endpoint-url=$ENDPOINT lambda invoke \
  --function-name gatekeeper-function \
  --payload '{"body": "{\"filename\": \"top_secret.txt\", \"expiration_seconds\": 15}"}' \
  response.json > /dev/null

echo "Gatekeeper response:"
cat response.json | jq .

BODY_JSON=$(cat response.json | jq -r .body)
STATUS_CODE=$(cat response.json | jq -r .statusCode)
URL=$(echo "$BODY_JSON" | jq -r .upload_url)
FILE_ID=$(echo "$BODY_JSON" | jq -r .file_id)

if [[ "$STATUS_CODE" != "200" ]]; then
  echo "Gatekeeper returned non-200. Aborting demo."
  exit 1
fi

echo ""
echo "=> FILE_ID : $FILE_ID"
echo "=> Presigned URL : (generated, see above)"

echo ""
echo "==========================================================="
echo "  2. Uploading top_secret.txt directly to S3"
echo "==========================================================="
echo "   (This bypasses Lambda entirely — client -> S3 direct)"
curl -s -X PUT -T top_secret.txt "$URL"
echo ""
echo "Upload done."

echo ""
echo "=> Confirming file is in S3:"
aws --endpoint-url=$ENDPOINT s3 ls s3://secure-file-share-bucket/uploads/$FILE_ID

echo ""
echo "=> Confirming record is ACTIVE in DynamoDB:"
aws --endpoint-url=$ENDPOINT dynamodb get-item \
  --table-name file-meta-data \
  --key "{\"file_id\": {\"S\": \"$FILE_ID\"}}" \
  --output json \
  | jq '.Item | {file_id: .file_id.S, filename: .filename.S, status: .status.S, expires_at: .expires_at.N}'

echo ""
echo "==========================================================="
echo "  3. Triggering DynamoDB TTL sweep"
echo "==========================================================="
echo "   LocalStack's TTL worker runs every 60 minutes by default — far too slow"
echo "   to demo. LocalStack exposes an internal endpoint to trigger it immediately:"
echo "   DELETE /_aws/dynamodb/expired"
echo ""
echo "   Waiting 18 seconds for the item's 15s TTL to actually expire first..."
sleep 18

echo ""
echo "=> Triggering the TTL sweep now..."
curl -s -X DELETE http://localhost:4566/_aws/dynamodb/expired | jq .

echo ""
echo "=> Confirming DynamoDB record was deleted by the TTL sweep:"
DB_OUT=$(aws --endpoint-url=$ENDPOINT dynamodb get-item \
  --table-name file-meta-data \
  --key "{\"file_id\": {\"S\": \"$FILE_ID\"}}" \
  --output json 2>/dev/null | jq '.Item' 2>/dev/null)

if [[ "$DB_OUT" == "null" ]]; then
    echo "   DynamoDB record is GONE. TTL sweep deleted it."
else
    echo "   DynamoDB record still exists (item may not have expired yet)."
    echo "   Current item: $DB_OUT"
fi

echo ""
echo "   Waiting 5 seconds for Stream -> Lambda -> S3 deletion chain..."
sleep 5

DELETED=0
S3_OUT=$(aws --endpoint-url=$ENDPOINT s3 ls s3://secure-file-share-bucket/uploads/$FILE_ID 2>/dev/null || true)
if [[ -z "$S3_OUT" ]]; then
    echo ""
    echo "SUCCESS! The full chain worked:"
    echo "   TTL expired -> DynamoDB auto-deleted record -> Stream fired REMOVE event"
    echo "   -> automated_cleanup Lambda invoked -> S3 file permanently wiped."
    DELETED=1
else
    echo "   S3 file not yet gone. Polling for 20 more seconds..."
    for i in {1..4}; do
        sleep 5
        S3_OUT=$(aws --endpoint-url=$ENDPOINT s3 ls s3://secure-file-share-bucket/uploads/$FILE_ID 2>/dev/null || true)
        if [[ -z "$S3_OUT" ]]; then
            echo "SUCCESS! File deleted from S3!"
            DELETED=1
            break
        fi
        echo -n "  [$(( i * 5 ))s] waiting..."
    done
fi

if [[ "$DELETED" == "0" ]]; then
    echo "FAILED! File is still in S3. Check Lambda logs below."
fi

echo ""
echo "==========================================================="
echo "  4. Cleanup Lambda Logs (last invocation)"
echo "==========================================================="
STREAM=$(aws --endpoint-url=$ENDPOINT logs describe-log-streams \
  --log-group-name /aws/lambda/automated-cleanup-function \
  --order-by LastEventTime --descending \
  --query 'logStreams[0].logStreamName' --output text)

aws --endpoint-url=$ENDPOINT logs get-log-events \
  --log-group-name /aws/lambda/automated-cleanup-function \
  --log-stream-name "$STREAM" \
  --query 'events[].message' --output text

# Clean up local temp files
rm -f top_secret.txt upload_test.txt response.json

echo ""
echo "==========================================================="
echo "  Demo complete."
echo "==========================================================="
