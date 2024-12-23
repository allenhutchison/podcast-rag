from apscheduler.schedulers.blocking import BlockingScheduler
from file_manager import FileManager
from config import Config

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Transcribe podcasts using Whisper")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    args = parser.parse_args()

    # Remove the decorator from run_file_manager and define it normally:
    def run_file_manager(env_file=None):
        config = Config(env_file=env_file)
        file_manager = FileManager(config=config, dry_run=False)
        file_manager.process_directory()

    # Now add the job with scheduler.add_job, passing needed kwargs
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_file_manager,
        'cron',
        hour=2,
        kwargs={'env_file': args.env_file}
    )

    scheduler.start()