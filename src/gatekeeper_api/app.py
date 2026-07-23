import json
import boto3
import time
import uuid
import os

# 1. Automatically detect LocalStack internal endpoint
endpoint_url = os.environ.get('AWS_ENDPOINT_URL')
if not endpoint_url and os.environ.get('LOCALSTACK_HOSTNAME'):
    endpoint_url = f"http://{os.environ.get('LOCALSTACK_HOSTNAME')}:4566"

# 2. Initialize boto3 clients pointing to LocalStack
s3_client = boto3.client('s3', endpoint_url=endpoint_url)
dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)

# 3. Safe environment variable fallbacks
BUCKET_NAME = os.environ.get('BUCKET_NAME') or 'secure-file-share-bucket'
TABLE_NAME = os.environ.get('TABLE_NAME') or 'file-meta-data'
table = dynamodb.Table(TABLE_NAME) # type: ignore

def lambda_handler(event, context):
    try:
        # Parse request body safely
        body = {}
        if isinstance(event, dict) and 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            elif isinstance(event['body'], dict):
                body = event['body']

        filename = body.get('filename', 'unnamed_file')
        expiration_seconds = int(body.get('expiration_seconds', 60))

        file_id = str(uuid.uuid4())
        s3_key = f"uploads/{file_id}"
        expires_at = int(time.time()) + expiration_seconds

        # Generate S3 Presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=expiration_seconds
        )

        # Record metadata in DynamoDB
        table.put_item(
            Item={
                'file_id': file_id,
                'filename': filename,
                'expires_at': expires_at
            }
        )

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'Secure upload link generated successfully',
                'file_id': file_id,
                'upload_url': presigned_url,
                'expires_in_seconds': expiration_seconds
            })
        }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }