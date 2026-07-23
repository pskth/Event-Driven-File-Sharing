import boto3
import os

# Initialize the S3 client
s3_client = boto3.client('s3')

# Pull the bucket name from environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')

def lambda_handler(event, context):
    try:
        # Loop through the records provided by the DynamoDB Stream payload
        for record in event.get('Records', []):
            
            # We only care about deleted items (TTL expirations)
            if record.get('eventName') == 'REMOVE':
                
                # Extract the file_id from the deleted DynamoDB record
                deleted_item = record.get('dynamodb', {}).get('OldImage', {})
                file_id = deleted_item.get('file_id', {}).get('S')
                
                if file_id:
                    s3_key = f"uploads/{file_id}"
                    print(f"TTL expired for {file_id}. Wiping from S3...")
                    
                    # Perform the final S3 wipe
                    s3_client.delete_object(
                        Bucket=BUCKET_NAME,
                        Key=s3_key
                    )
                    print(f"Successfully deleted {s3_key} from S3.")
                    
        return {
            'statusCode': 200,
            'body': 'Cleanup executed successfully.'
        }
        
    except Exception as e:
        print(f"Error during automated cleanup: {str(e)}")
        return {
            'statusCode': 500,
            'body': 'Internal Server Error during cleanup.'
        }