import os

import boto3
from botocore.exceptions import ClientError

# Initialize clients
s3_client = boto3.client("s3")

# Pull the bucket name from environment variables
BUCKET_NAME = os.environ.get("BUCKET_NAME")


def lambda_handler(event, context):
    """
    Triggered by DynamoDB Streams whenever a record is REMOVED (TTL expiry or
    manual delete).

    Two-phase awareness:
    - Only wipes the S3 file if the deleted record had status=ACTIVE.
    - PENDING records that were rolled back have no real file in S3, so they
      are skipped — attempting to delete a non-existent key would waste an API
      call and could mask real errors.
    - S3 failures are caught per-record so one bad deletion does not block the
      rest of the batch. Failed records are reported and DynamoDB Streams will
      retry the batch automatically.
    """
    failed_records = []

    for record in event.get("Records", []):

        if record.get("eventName") != "REMOVE":
            continue

        deleted_item = record.get("dynamodb", {}).get("OldImage", {})
        file_id = deleted_item.get("file_id", {}).get("S")
        status = deleted_item.get("status", {}).get("S", "UNKNOWN")

        if not file_id:
            print("[Cleanup] Record missing file_id — skipping.")
            continue

        # ── Skip rolled-back / incomplete records ─────────────────────────
        # A PENDING record means the gatekeeper Lambda failed after writing to
        # DynamoDB but before committing to ACTIVE. No real file was ever
        # uploaded, so there is nothing to delete in S3.
        if status != "ACTIVE":
            print(
                f"[Cleanup] Skipping {file_id} — status was '{status}', "
                "not ACTIVE. No S3 file to wipe."
            )
            continue

        # ── Delete the actual file from S3 ───────────────────────────────
        s3_key = f"uploads/{file_id}"
        print(f"[Cleanup] TTL expired for ACTIVE record {file_id}. Wiping {s3_key}...")

        try:
            s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
            print(f"[Cleanup] Successfully deleted {s3_key} from S3.")

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            # NoSuchKey means the file was already gone — not a real failure.
            if error_code == "NoSuchKey":
                print(f"[Cleanup] {s3_key} was already absent from S3 — nothing to do.")
            else:
                # Real S3 failure (permissions, bucket gone, network, etc.).
                # Record it and continue processing the rest of the batch.
                # DynamoDB Streams will retry the whole batch, so idempotency
                # (the NoSuchKey guard above) protects already-deleted files.
                print(f"[Cleanup] ERROR deleting {s3_key}: {e}")
                failed_records.append({"file_id": file_id, "error": str(e)})

    if failed_records:
        # Raising an exception signals DynamoDB Streams to retry this batch.
        raise RuntimeError(
            f"[Cleanup] {len(failed_records)} record(s) failed S3 deletion: {failed_records}"
        )

    return {
        "statusCode": 200,
        "body": "Cleanup executed successfully.",
    }
