import logging

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler

from argparse_shared import add_log_level_argument, get_base_parser
from config import Config
from file_manager import FileManager


def job_listener(event):
    if event.exception:
        logging.error("Job failed: %s", event.exception)
    else:
        logging.info("Job completed successfully")

def run_file_manager(env_file=None):
    """Run the file manager with the given environment file."""
    config = Config(env_file=env_file)
    file_manager = FileManager(config=config, dry_run=False)
    file_manager.process_directory()

if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Scheduled podcast transcription."
    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("scheduler.log"), 
        ],
    )
    # Set the log level for the httpx and httpcore libraries
    # because they are super chatty on INFO.
    if args.log_level == "INFO":
        logging.getLogger('httpx').setLevel("WARNING")
        logging.getLogger('httpcore').setLevel("WARNING")

    # Run the file manager once before starting the scheduler
    run_file_manager(env_file=args.env_file)

    scheduler = BlockingScheduler()
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        run_file_manager,
        'interval',
        hours=1,
        kwargs={'env_file': args.env_file}
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped.")
