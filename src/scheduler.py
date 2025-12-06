import logging
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.repository import SQLAlchemyPodcastRepository
from src.workflow.config import WorkflowConfig
from src.workflow.orchestrator import WorkflowOrchestrator


def job_listener(event):
    if event.exception:
        logging.error("Job failed: %s", event.exception)
    else:
        logging.info("Job completed successfully")


def run_workflow(config, workflow_config, repository):
    """Run the unified workflow orchestrator."""
    orchestrator = WorkflowOrchestrator(
        config=config,
        workflow_config=workflow_config,
        repository=repository,
    )
    result = orchestrator.run_once()
    logging.info(
        f"Workflow complete: {result.total_processed} processed, "
        f"{result.total_failed} failed in {result.duration_seconds:.1f}s"
    )

if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Scheduled podcast processing workflow."
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
        logging.getLogger("httpx").setLevel("WARNING")
        logging.getLogger("httpcore").setLevel("WARNING")

    # Create config instances
    config = Config(env_file=args.env_file)
    workflow_config = WorkflowConfig.from_env()

    # Create repository
    repository = SQLAlchemyPodcastRepository(config.DATABASE_URL)

    interval_seconds = workflow_config.run_interval_seconds
    interval_hours = interval_seconds / 3600

    logging.info("Podcast RAG Scheduler starting...")
    logging.info(f"Database: {config.DATABASE_URL}")
    logging.info(f"Processing interval: {interval_seconds}s ({interval_hours:.1f} hours)")

    # Run the workflow once before starting the scheduler
    logging.info("Running initial workflow...")
    run_workflow(config, workflow_config, repository)

    scheduler = BlockingScheduler()
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        run_workflow,
        "interval",
        seconds=interval_seconds,
        args=[config, workflow_config, repository],
    )

    logging.info("Scheduler configured. Starting scheduled execution...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
        scheduler.shutdown()
