import pytest
import os
from src.db.metadatadb import PodcastDB
from src.util.opml_importer import OPMLImporter

@pytest.fixture
def db():
    # Use a temporary database file for testing
    db_path = "test_podcasts.db"
    db = PodcastDB(db_path)
    yield db
    # Cleanup after tests
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def importer(db):
    return OPMLImporter(db)

def test_parse_opml(importer):
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="1.1">
        <body>
            <outline text="Test Podcast 1" type="rss" xmlUrl="https://example.com/feed1.xml" description="A test podcast" imageUrl="https://example.com/image1.jpg"/>
            <outline text="Test Podcast 2" type="rss" xmlUrl="https://example.com/feed2.xml" description="Another test podcast" imageUrl="https://example.com/image2.jpg"/>
        </body>
    </opml>
    """
    
    podcasts = importer.parse_opml(opml_content)
    assert len(podcasts) == 2
    assert podcasts[0]['title'] == "Test Podcast 1"
    assert podcasts[0]['feed_url'] == "https://example.com/feed1.xml"
    assert podcasts[0]['image_url'] == "https://example.com/image1.jpg"
    assert podcasts[1]['title'] == "Test Podcast 2"
    assert podcasts[1]['feed_url'] == "https://example.com/feed2.xml"
    assert podcasts[1]['image_url'] == "https://example.com/image2.jpg"

def test_import_from_string(importer):
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="1.1">
        <body>
            <outline text="Test Podcast" type="rss" xmlUrl="https://example.com/feed.xml" description="A test podcast" imageUrl="https://example.com/image.jpg"/>
        </body>
    </opml>
    """
    
    imported_count = importer.import_from_string(opml_content)
    assert imported_count == 1
    
    # Verify the podcast was added to the database
    podcast = importer.db.get_podcast_by_url("https://example.com/feed.xml")
    assert podcast is not None
    assert podcast.title == "Test Podcast"
    assert podcast.description == "A test podcast"
    assert podcast.image_url == "https://example.com/image.jpg"

def test_invalid_image_url(importer):
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="1.1">
        <body>
            <outline text="Test Podcast" type="rss" xmlUrl="https://example.com/feed.xml" description="A test podcast" imageUrl="not-a-valid-url"/>
        </body>
    </opml>
    """
    
    podcasts = importer.parse_opml(opml_content)
    assert len(podcasts) == 1
    assert podcasts[0]['image_url'] == ''  # Invalid image URL should be cleared

def test_duplicate_import(importer):
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="1.1">
        <body>
            <outline text="Test Podcast" type="rss" xmlUrl="https://example.com/feed.xml" description="A test podcast"/>
        </body>
    </opml>
    """
    
    # Import twice
    imported_count1 = importer.import_from_string(opml_content)
    imported_count2 = importer.import_from_string(opml_content)
    
    assert imported_count1 == 1
    assert imported_count2 == 0  # Should not import duplicate

def test_invalid_opml(importer):
    invalid_opml = "This is not valid OPML content"
    podcasts = importer.parse_opml(invalid_opml)
    assert len(podcasts) == 0

def test_invalid_feed_url(importer):
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="1.1">
        <body>
            <outline text="Test Podcast" type="rss" xmlUrl="not-a-valid-url" description="A test podcast"/>
        </body>
    </opml>
    """
    
    podcasts = importer.parse_opml(opml_content)
    assert len(podcasts) == 0  # Invalid URL should be filtered out 