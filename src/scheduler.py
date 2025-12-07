"""Podcast pipeline scheduler.

Runs the pipeline-oriented orchestrator optimized for continuous
GPU utilization during transcription.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.repository import SQLAlchemyPodcastRepository
from src.workflow.config import PipelineConfig
from src.workflow.orchestrator import PipelineOrchestrator


def run_pipeline(config: Config, pipeline_config: PipelineConfig, repository):
    """Run the pipeline orchestrator.

    Args:
        config: Application configuration.
        pipeline_config: Pipeline-specific configuration.
        repository: Database repository.
    """
    orchestrator = PipelineOrchestrator(
        config=config,
        pipeline_config=pipeline_config,
        repository=repository,
    )

    stats = orchestrator.run()

    logging.info(
        f"Pipeline complete: "
        f"{stats.episodes_transcribed} transcribed, "
        f"{stats.transcription_failures} failed, "
        f"duration={stats.duration_seconds:.1f}s"
    )

    if stats.post_processing:
        logging.info(
            f"Post-processing: "
            f"metadata={stats.post_processing.metadata_processed}/{stats.post_processing.metadata_failed}, "
            f"indexing={stats.post_processing.indexing_processed}/{stats.post_processing.indexing_failed}, "
            f"cleanup={stats.post_processing.cleanup_processed}/{stats.post_processing.cleanup_failed}"
        )


if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Podcast processing pipeline scheduler."
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
    pipeline_config = PipelineConfig.from_env()

    # Create repository
    repository = SQLAlchemyPodcastRepository(config.DATABASE_URL)

    logging.info("Podcast RAG Pipeline starting...")
    logging.info(f"Database: {config.DATABASE_URL}")
    logging.info(f"Sync interval: {pipeline_config.sync_interval_seconds}s")
    logging.info(f"Download buffer: {pipeline_config.download_buffer_size} episodes")
    logging.info(f"Post-processing workers: {pipeline_config.post_processing_workers}")

    try:
        run_pipeline(config, pipeline_config, repository)
    except KeyboardInterrupt:
        logging.info("Pipeline interrupted by user")
    except Exception:
        logging.exception("Pipeline failed")
        sys.exit(1)
    finally:
        repository.close()
        logging.info("Database connection closed")
