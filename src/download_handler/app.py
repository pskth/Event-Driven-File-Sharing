import json
import os
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

# Lifetime of the generated presigned GET URL itself. This is intentionally
# short and unrelated to the file's overall share-expiration timer — it only
# needs to stay valid long enough for the browser to start the download
# immediately after this Lambda responds.
DOWNLOAD_URL_TTL_SECONDS = 60


def _response(status_code: int, body_dict: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_dict),
    }


def lambda_handler(event, context):
    """
    Looks up a share code and, if the file is still valid, returns a
    short-lived presigned GET URL so the browser can download directly
    from S3 (bypassing this Lambda's memory, same principle as the upload
    path).

    IMPORTANT: expiration is re-validated explicitly against `expires_at`
    on every call, rather than trusting "the record still exists in
    DynamoDB" as a proxy for validity. DynamoDB's TTL background sweep is
    NOT instantaneous — on LocalStack it can lag by up to 60 minutes, and
    on real AWS it can take minutes to hours. Without this explicit check,
    a file could remain downloadable well past its advertised expiration
    simply because the janitor hasn't gotten to it yet.
    """
    try:
        body = {}
        if isinstance(event, dict) and "body" in event:
            if isinstance(event["body"], str):
                body = json.loads(event["body"]) if event["body"] else {}
            elif isinstance(event["body"], dict):
                body = event["body"]

        code = (body.get("code") or "").strip().upper()

        if not code:
            return _response(400, {"error": "Missing 'code'."})

        try:
            result = table.get_item(Key={"file_id": code})
        except ClientError as e:
            print(f"[Download] DynamoDB error looking up {code}: {e}")
            return _response(503, {"error": "Metadata service unavailable."})

        item = result.get("Item")

        if not item:
            return _response(404, {"error": "Invalid code. No such file exists."})

        if item.get("status") != "ACTIVE":
            # Covers PENDING records that never completed the 2PC commit —
            # there is no real file in S3 for these.
            return _response(404, {"error": "This file is not available for download."})

        expires_at = int(item.get("expires_at", 0))
        now = int(time.time())
        if expires_at <= now:
            return _response(410, {"error": "This link has expired."})

        s3_key = item["s3_key"]
        filename = item.get("filename", "download")

        try:
            download_url = s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": BUCKET_NAME,
                    "Key": s3_key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=DOWNLOAD_URL_TTL_SECONDS,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                # Metadata says ACTIVE but the physical file is gone — an
                # inconsistent state that should not normally happen, but we
                # surface it clearly rather than handing back a broken link.
                print(f"[Download] {s3_key} missing from S3 despite ACTIVE record.")
                return _response(404, {"error": "File not found in storage."})
            print(f"[Download] S3 error generating presigned GET URL: {e}")
            return _response(503, {"error": "Storage service unavailable."})

        print(f"[Download] Issued download URL for {code} ({filename}).")
        return _response(200, {
            "filename": filename,
            "download_url": download_url,
            "expires_at": expires_at,
            "seconds_remaining": expires_at - now,
        })

    except Exception as e:
        print(f"[Download] Unexpected error: {e}")
        return _response(500, {"error": "Internal server error.", "detail": str(e)})
