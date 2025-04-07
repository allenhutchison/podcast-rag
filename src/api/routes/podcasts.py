from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List
import logging
import os

from db.database import get_db
from core.podcast import podcast_manager
from db.models import Podcast as DBPodcast, Episode as DBEpisode
from schemas import Podcast, Episode, PodcastCreate, PodcastUpdate

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/podcasts", tags=["podcasts"])

@router.post("/", response_model=Podcast)
def create_podcast(feed_url: str, db: Session = Depends(get_db)):
    """Create a new podcast from a feed URL."""
    try:
        return podcast_manager.create_podcast(db, feed_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/import-opml", response_model=List[Podcast])
async def import_opml(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import podcasts from an OPML file."""
    try:
        content = await file.read()
        opml_content = content.decode("utf-8")
        
        imported_podcasts = podcast_manager.import_from_opml(db, opml_content)
        
        if not imported_podcasts:
            return {"message": "No new podcasts were imported"}
        
        return imported_podcasts
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error importing OPML: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error importing OPML: {str(e)}")

@router.get("/export-opml", response_class=PlainTextResponse)
def export_opml(db: Session = Depends(get_db)):
    """Export all podcasts to OPML format."""
    try:
        opml_content = podcast_manager.export_to_opml(db)
        return opml_content
    except Exception as e:
        logger.error(f"Error exporting to OPML: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting to OPML: {str(e)}")

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

@router.get("/episodes/{episode_id}/audio")
def get_episode_audio(episode_id: int, db: Session = Depends(get_db)):
    """Get the audio file for an episode."""
    episode = podcast_manager.get_episode(db, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if not episode.is_downloaded or not episode.local_audio_path:
        raise HTTPException(status_code=404, detail="Episode audio not downloaded")
    
    if not os.path.exists(episode.local_audio_path):
        raise HTTPException(status_code=404, detail="Episode audio file not found")
    
    return FileResponse(
        episode.local_audio_path,
        media_type="audio/mpeg",
        filename=os.path.basename(episode.local_audio_path)
    ) 