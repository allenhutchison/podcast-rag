import logging
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.file_manager import FileManager


def job_listener(event):
    if event.exception:
        logging.error("Job failed: %s", event.exception)
    else:
        logging.info("Job completed successfully")

def run_file_manager(config):
    """Run the file manager with the given configuration."""
    file_manager = FileManager(config=config, dry_run=False)
    file_manager.process_directory()

if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Scheduled podcast transcription."
    args = parser.parse_args()

    # Set up logging - log to stdout for Docker
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Set the log level for the httpx and httpcore libraries
    # because they are super chatty on INFO.
    if args.log_level == "INFO":
        logging.getLogger('httpx').setLevel("WARNING")
        logging.getLogger('httpcore').setLevel("WARNING")

    # Create config instance once
    config = Config(env_file=args.env_file)

    logging.info("Podcast RAG Scheduler starting...")
    logging.info(f"Media directory: {config.BASE_DIRECTORY}")
    logging.info(f"Processing interval: 1 hour")

    # Run the file manager once before starting the scheduler
    logging.info("Running initial podcast processing...")
    run_file_manager(config=config)

    scheduler = BlockingScheduler()
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        run_file_manager,
        'interval',
        hours=1,
        args=[config]
    )

    logging.info("Scheduler configured. Starting scheduled execution...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
        scheduler.shutdown()
