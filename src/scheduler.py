from apscheduler.schedulers.blocking import BlockingScheduler
from file_manager import FileManager
from config import Config
from argparse_shared import get_base_parser

if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Scheduled podcast transcription."
    args = parser.parse_args()

    def run_file_manager(env_file=None):
        config = Config(env_file=env_file)
        file_manager = FileManager(config=config, dry_run=False)
        file_manager.process_directory()

    print(f"Environment file: {args.env_file}") 
    run_file_manager(env_file=args.env_file)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_file_manager,
        'interval',
        hours=1,
        kwargs={'env_file': args.env_file}
    )

    scheduler.start()
