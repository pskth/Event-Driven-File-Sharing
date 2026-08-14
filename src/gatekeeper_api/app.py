import json
import os
import secrets
import time

import boto3
from botocore.exceptions import ClientError

# 1. Automatically detect LocalStack internal endpoint
endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
if not endpoint_url and os.environ.get("LOCALSTACK_HOSTNAME"):
    endpoint_url = f"http://{os.environ.get('LOCALSTACK_HOSTNAME')}:4566"

# 2. Initialize boto3 clients pointing to LocalStack
s3_client = boto3.client("s3", endpoint_url=endpoint_url)
dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url)

# 3. Safe environment variable fallbacks
BUCKET_NAME = os.environ.get("BUCKET_NAME") or "secure-file-share-bucket"
TABLE_NAME = os.environ.get("TABLE_NAME") or "file-meta-data"
table = dynamodb.Table(TABLE_NAME)  # type: ignore

# Alphabet excludes visually ambiguous characters (0/O, 1/I/L) so codes are
# easy to read aloud and type by hand.
SHARE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SHARE_CODE_LENGTH = 8


def _generate_share_code() -> str:
    """
    Generates a short, human-typeable share code (e.g. "K4J9XQP2").

    This code doubles as BOTH the DynamoDB partition key (file_id) AND the
    S3 object key suffix — there is no separate lookup index. See
    docs/WEB_APP_DESIGN_DECISIONS.md for the collision-risk tradeoff
    analysis behind this choice.
    """
    return "".join(secrets.choice(SHARE_CODE_ALPHABET) for _ in range(SHARE_CODE_LENGTH))


def _rollback_pending_record(file_id: str) -> None:
    """
    Compensating transaction: delete a PENDING metadata record that never
    reached ACTIVE. Called whenever Phase 1 or Phase 2 fails mid-way so
    that no orphaned record lingers in DynamoDB.
    """
    try:
        table.delete_item(
            Key={"file_id": file_id},
            # Only delete if the record is still PENDING — guards against a
            # race where the record was legitimately promoted by another path.
            ConditionExpression="attribute_exists(file_id) AND #st = :pending",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":pending": "PENDING"},
        )
        print(f"[2PC] Rollback: PENDING record for {file_id} removed.")
    except ClientError as e:
        # ConditionalCheckFailedException means the record was already gone or
        # promoted — either way, rollback is not needed.
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            print(f"[2PC] Rollback warning — could not delete record for {file_id}: {e}")


def lambda_handler(event, context):
    """
    Two-Phase Commit for safe link generation:

    Phase 1 — Prepare:
      a. Generate the S3 presigned URL.
      b. Write a PENDING metadata record to DynamoDB.
      Both must succeed, or we abort and clean up.

    Phase 2 — Commit:
      Promote the record to ACTIVE.
      Only on success do we return the URL to the caller.

    If any step fails, a compensating transaction deletes the PENDING record
    so no orphaned metadata or untracked files are left behind.
    """
    file_id = _generate_share_code()

    try:
        # ── Parse request ──────────────────────────────────────────────────
        body = {}
        if isinstance(event, dict) and "body" in event:
            if isinstance(event["body"], str):
                body = json.loads(event["body"])
            elif isinstance(event["body"], dict):
                body = event["body"]

        filename = body.get("filename", "unnamed_file")
        expiration_seconds = int(body.get("expiration_seconds", 60))

        s3_key = f"uploads/{file_id}"
        expires_at = int(time.time()) + expiration_seconds

        # ── Phase 1a: Generate S3 Presigned URL ───────────────────────────
        # If S3 is down or misconfigured, we fail here before touching
        # DynamoDB — no rollback needed.
        print(f"[2PC] Phase 1a: Generating presigned URL for {file_id}...")
        try:
            presigned_url = s3_client.generate_presigned_url(
                "put_object",
                Params={"Bucket": BUCKET_NAME, "Key": s3_key},
                ExpiresIn=expiration_seconds,
            )
        except ClientError as e:
            print(f"[2PC] Phase 1a FAILED — S3 error: {e}")
            return {
                "statusCode": 503,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Storage service unavailable. No action was taken.",
                    "detail": str(e),
                }),
            }

        # ── Phase 1b: Write PENDING record to DynamoDB ────────────────────
        # The record is marked PENDING so the cleanup Lambda and any reader
        # know this upload has NOT been confirmed yet.
        print(f"[2PC] Phase 1b: Writing PENDING record for {file_id}...")
        try:
            table.put_item(
                Item={
                    "file_id": file_id,
                    "filename": filename,
                    "s3_key": s3_key,
                    "expires_at": expires_at,
                    "status": "PENDING",
                    "created_at": int(time.time()),
                },
                # Defensive guard: abort if somehow this file_id already exists.
                ConditionExpression="attribute_not_exists(file_id)",
            )
        except ClientError as e:
            print(f"[2PC] Phase 1b FAILED — DynamoDB error: {e}")
            # No record was written, so nothing to roll back.
            return {
                "statusCode": 503,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Metadata service unavailable. No action was taken.",
                    "detail": str(e),
                }),
            }

        # ── Phase 2: Commit — promote record to ACTIVE ────────────────────
        # Both preparatory steps succeeded. Now we finalise by marking the
        # record ACTIVE. If this update fails, we roll back the PENDING record
        # so the system stays consistent.
        print(f"[2PC] Phase 2: Committing record {file_id} to ACTIVE...")
        try:
            table.update_item(
                Key={"file_id": file_id},
                UpdateExpression="SET #st = :active",
                ConditionExpression="#st = :pending",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":active": "ACTIVE",
                    ":pending": "PENDING",
                },
            )
        except ClientError as e:
            print(f"[2PC] Phase 2 FAILED — DynamoDB commit error: {e}")
            _rollback_pending_record(file_id)
            return {
                "statusCode": 503,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Failed to finalise the upload session. The operation was rolled back.",
                    "detail": str(e),
                }),
            }

        # ── Success ───────────────────────────────────────────────────────
        print(f"[2PC] Commit successful. file_id={file_id} is now ACTIVE.")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Secure upload link generated successfully",
                "file_id": file_id,
                "upload_url": presigned_url,
                "expires_in_seconds": expiration_seconds,
            }),
        }

    except Exception as e:
        # Unexpected error — attempt rollback as a safety net.
        print(f"[2PC] Unexpected error: {e}")
        _rollback_pending_record(file_id)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error.", "detail": str(e)}),
        }
