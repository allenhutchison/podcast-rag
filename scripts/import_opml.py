

import os
import sys
import logging
import listparser
from sqlalchemy.orm import Session

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.argparse_shared import get_base_parser, add_log_level_argument
from src.config import Config
from src.db.database import get_db
from src.db.models import Podcast

def import_from_opml(db_session: Session, opml_path: str):
    """
    Parses an OPML file and adds new podcasts to the database.
    
    Args:
        db_session: The SQLAlchemy session to use for database operations.
        opml_path: The file path to the OPML file.
    """
    if not os.path.exists(opml_path):
        logging.error(f"OPML file not found at: {opml_path}")
        return

    logging.info(f"Parsing OPML file: {opml_path}")
    parsed_list = listparser.parse(opml_path)
    
    if not parsed_list.feeds:
        logging.warning("No feeds found in the OPML file.")
        return

    added_count = 0
    skipped_count = 0

    for feed in parsed_list.feeds:
        feed_url = feed.url
        if not feed_url:
            logging.warning(f"Skipping feed with no URL: {feed.title}")
            continue

        # Check if the podcast feed already exists
        exists = db_session.query(Podcast).filter(Podcast.feed_url == feed_url).first()
        if exists:
            logging.debug(f"Skipping existing podcast: {feed.title} ({feed_url})")
            skipped_count += 1
            continue

        # Add the new podcast
        new_podcast = Podcast(
            title=feed.title or "Untitled Podcast",
            feed_url=feed_url,
            author=feed.get("author")
        )
        db_session.add(new_podcast)
        added_count += 1
        logging.info(f"Adding new podcast: {new_podcast.title}")

    if added_count > 0:
        logging.info(f"Committing {added_count} new podcasts to the database.")
        db_session.commit()
    else:
        logging.info("No new podcasts to add.")

    logging.info("\n--- Import Summary ---")
    logging.info(f"New Podcasts Added: {added_count}")
    logging.info(f"Podcasts Skipped (already exist): {skipped_count}")
    logging.info("----------------------")


if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Import podcasts from an OPML file into the database."
    add_log_level_argument(parser)
    parser.add_argument("opml_file", help="Path to the OPML file to import.")
    
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Initialize config to ensure database URL is loaded from the correct .env file
    config = Config(env_file=args.env_file)
    
    db_session: Session = next(get_db())
    try:
        import_from_opml(db_session, args.opml_file)
    finally:
        db_session.close()
