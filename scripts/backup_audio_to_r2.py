

import os
import sys
import boto3
import logging
from botocore.exceptions import ClientError

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.argparse_shared import get_base_parser, add_log_level_argument
from src.config import Config

def get_r2_client(config: Config):
    """Initializes and returns a boto3 client configured for Cloudflare R2."""
    if not all([config.S3_ENDPOINT_URL, config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY]):
        logging.error("Error: S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY must be set.")
        exit(1)
        
    return boto3.client(
        's3',
        endpoint_url=config.S3_ENDPOINT_URL,
        aws_access_key_id=config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
        region_name='auto'  # R2 specific
    )

def object_exists(client, bucket_name, object_key):
    """Checks if an object exists in the R2 bucket."""
    try:
        client.head_object(Bucket=bucket_name, Key=object_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            logging.error(f"Error checking object {object_key}: {e}")
            raise

def main():
    """
    Scans the local media directory and uploads any new .mp3 files
    to a Cloudflare R2 bucket.
    """
    parser = get_base_parser()
    add_log_level_argument(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    
    s3_client = get_r2_client(config)
    bucket_name = config.S3_BUCKET_NAME
    local_media_path = config.BASE_DIRECTORY

    if not bucket_name:
        logging.error("Error: S3_BUCKET_NAME must be set.")
        exit(1)

    if not os.path.isdir(local_media_path):
        logging.error(f"Error: Local media directory '{local_media_path}' not found.")
        logging.error("Please set the BASE_DIRECTORY environment variable or ensure it exists.")
        exit(1)

    logging.info(f"Starting backup from '{local_media_path}' to R2 bucket: '{bucket_name}'...")
    
    uploaded_count = 0
    skipped_count = 0
    
    for root, _, files in os.walk(local_media_path):
        for filename in files:
            if filename.endswith(".mp3"):
                local_file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_file_path, local_media_path)
                object_key = f"podcasts/{relative_path}"

                logging.info(f"Processing: {local_file_path}")
                logging.debug(f"  -> R2 Object Key: {object_key}")

                try:
                    if object_exists(s3_client, bucket_name, object_key):
                        logging.debug("  -> Status: Already exists in R2. Skipping.")
                        skipped_count += 1
                    else:
                        logging.info("  -> Status: Not found in R2. Uploading...")
                        s3_client.upload_file(local_file_path, bucket_name, object_key)
                        logging.info("  -> Status: Upload complete.")
                        uploaded_count += 1
                except Exception as e:
                    logging.error(f"  -> Status: An error occurred. {e}")

    logging.info("\n--- Backup Summary ---")
    logging.info(f"Files Uploaded: {uploaded_count}")
    logging.info(f"Files Skipped: {skipped_count}")
    logging.info("----------------------")

if __name__ == "__main__":
    main()
