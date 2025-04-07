from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from src.db.database import get_db
from src.core.podcast import podcast_manager
from src.db.models import Podcast, Episode

router = APIRouter(prefix="/podcasts", tags=["podcasts"])

@router.post("/", response_model=Podcast)
def create_podcast(feed_url: str, db: Session = Depends(get_db)):
    """Create a new podcast from a feed URL."""
    try:
        return podcast_manager.create_podcast(db, feed_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[Podcast])
def list_podcasts(db: Session = Depends(get_db)):
    """List all podcasts."""
    return podcast_manager.list_podcasts(db)

@router.get("/{podcast_id}", response_model=Podcast)
def get_podcast(podcast_id: int, db: Session = Depends(get_db)):
    """Get a podcast by ID."""
    podcast = podcast_manager.get_podcast(db, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    return podcast

@router.put("/{podcast_id}", response_model=Podcast)
def update_podcast(podcast_id: int, db: Session = Depends(get_db)):
    """Update a podcast and its episodes from the feed."""
    try:
        return podcast_manager.update_podcast(db, podcast_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{podcast_id}")
def delete_podcast(podcast_id: int, db: Session = Depends(get_db)):
    """Delete a podcast and its associated files."""
    try:
        podcast_manager.delete_podcast(db, podcast_id)
        return {"message": "Podcast deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{podcast_id}/episodes", response_model=List[Episode])
def list_episodes(podcast_id: int, db: Session = Depends(get_db)):
    """List all episodes for a podcast."""
    return podcast_manager.list_episodes(db, podcast_id)

@router.get("/episodes/{episode_id}", response_model=Episode)
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    """Get an episode by ID."""
    episode = podcast_manager.get_episode(db, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode

@router.post("/episodes/{episode_id}/download", response_model=Episode)
def download_episode(episode_id: int, db: Session = Depends(get_db)):
    """Download an episode's audio file."""
    try:
        return podcast_manager.download_episode(db, episode_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 