

import os
import sys
import boto3
import logging
import threading
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.argparse_shared import get_base_parser, add_log_level_argument
from src.config import Config

# Thread-local storage for boto3 clients
thread_local = threading.local()

def init_worker(config: Config):
    """Initializer for each worker thread. Creates a thread-local boto3 client."""
    if not hasattr(thread_local, 's3_client'):
        logging.debug(f"Initializing S3 client for thread: {threading.get_ident()}")
        if not all([config.S3_ENDPOINT_URL, config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY]):
            # Cannot log error here as it's in a different process space
            # The main thread will catch this.
            return
        thread_local.s3_client = boto3.client(
            's3',
            endpoint_url=config.S3_ENDPOINT_URL,
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name='auto'
        )

def upload_worker(bucket_name, local_file_path, object_key):
    """
    Worker function using a thread-local client to upload a single file.
    """
    s3_client = thread_local.s3_client
    try:
        local_size = os.path.getsize(local_file_path)
        
        try:
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            remote_size = response['ContentLength']
            
            if local_size == remote_size:
                return 'verified'
            else:
                logging.warning(f"Re-uploading {object_key} due to size mismatch.")
                s3_client.upload_file(local_file_path, bucket_name, object_key)
                return 'reuploaded'

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                s3_client.upload_file(local_file_path, bucket_name, object_key)
                return 'uploaded'
            else:
                raise

    except Exception as e:
        logging.error(f"Error on {local_file_path}: {e}")
        return 'error'

def main():
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.add_argument("-w", "--workers", type=int, default=10, help="Number of parallel upload workers.")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), "INFO"),
                        format="%(asctime)s - %(thread)d - %(levelname)s - %(message)s",
                        handlers=[logging.StreamHandler()])

    config = Config(env_file=args.env_file)
    
    bucket_name = config.S3_BUCKET_NAME
    local_media_path = config.BASE_DIRECTORY

    if not all([bucket_name, config.S3_ENDPOINT_URL, config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY]):
        logging.error("Error: S3/R2 configuration is incomplete in your .env file.")
        exit(1)

    if not os.path.isdir(local_media_path):
        logging.error(f"Error: Local media directory '{local_media_path}' not found.")
        exit(1)

    logging.info(f"Scanning '{local_media_path}' for .mp3 files...")
    tasks = []
    for root, _, files in os.walk(local_media_path):
        for filename in files:
            if filename.endswith(".mp3"):
                local_file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_file_path, local_media_path)
                object_key = f"podcasts/{relative_path}"
                tasks.append((local_file_path, object_key))

    if not tasks:
        logging.info("No .mp3 files found to process.")
        return

    logging.info(f"Found {len(tasks)} files. Starting parallel processing with {args.workers} workers...")

    results = {'verified': 0, 'uploaded': 0, 'reuploaded': 0, 'error': 0}
    
    try:
        with ThreadPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(config,)) as executor:
            future_to_task = {executor.submit(upload_worker, bucket_name, task[0], task[1]): task for task in tasks}
            
            for future in tqdm(as_completed(future_to_task), total=len(tasks), desc="Verifying/Uploading Files"):
                result = future.result()
                if result in results:
                    results[result] += 1
    except KeyboardInterrupt:
        logging.info("\nCtrl+C detected. Shutting down gracefully...")

    logging.info("\n--- Backup Summary ---")
    logging.info(f"Files Verified & Skipped: {results['verified']}")
    logging.info(f"New Files Uploaded: {results['uploaded']}")
    logging.info(f"Mismatched Files Re-uploaded: {results['reuploaded']}")
    logging.info(f"Errors: {results['error']}")
    logging.info("----------------------")

if __name__ == "__main__":
    main()
