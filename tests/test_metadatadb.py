import pytest
import os
from src.db.metadatadb import PodcastDB

@pytest.fixture
def db():
    # Use a temporary database file for testing
    db_path = "test_podcasts.db"
    db = PodcastDB(db_path)
    yield db
    # Cleanup after tests
    if os.path.exists(db_path):
        os.remove(db_path)

def test_add_podcast(db):
    podcast = db.add_podcast(
        title="Test Podcast",
        description="A test podcast",
        feed_url="https://example.com/feed.xml"
    )
    assert podcast.title == "Test Podcast"
    assert podcast.feed_url == "https://example.com/feed.xml"

def test_get_podcast_by_url(db):
    # Add a podcast first
    db.add_podcast(
        title="Test Podcast",
        description="A test podcast",
        feed_url="https://example.com/feed.xml"
    )
    
    # Retrieve it
    podcast = db.get_podcast_by_url("https://example.com/feed.xml")
    assert podcast is not None
    assert podcast.title == "Test Podcast"

def test_update_podcast(db):
    # Add a podcast first
    db.add_podcast(
        title="Test Podcast",
        description="A test podcast",
        feed_url="https://example.com/feed.xml"
    )
    
    # Update it
    success = db.update_podcast(
        "https://example.com/feed.xml",
        title="Updated Title"
    )
    assert success is True
    
    # Verify the update
    podcast = db.get_podcast_by_url("https://example.com/feed.xml")
    assert podcast.title == "Updated Title"

def test_delete_podcast(db):
    # Add a podcast first
    db.add_podcast(
        title="Test Podcast",
        description="A test podcast",
        feed_url="https://example.com/feed.xml"
    )
    
    # Delete it
    success = db.delete_podcast("https://example.com/feed.xml")
    assert success is True
    
    # Verify it's gone
    podcast = db.get_podcast_by_url("https://example.com/feed.xml")
    assert podcast is None

def test_get_all_podcasts(db):
    # Add multiple podcasts
    db.add_podcast(
        title="Podcast 1",
        description="First podcast",
        feed_url="https://example.com/feed1.xml"
    )
    db.add_podcast(
        title="Podcast 2",
        description="Second podcast",
        feed_url="https://example.com/feed2.xml"
    )
    
    # Get all podcasts
    podcasts = db.get_all_podcasts()
    assert len(podcasts) == 2
    assert {p.title for p in podcasts} == {"Podcast 1", "Podcast 2"} 