from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Podcast(Base):
    __tablename__ = 'podcasts'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    feed_url = Column(String(500), nullable=False)
    image_url = Column(String(500))
    author = Column(String(200))
    language = Column(String(50))
    last_updated = Column(DateTime, default=datetime.utcnow)
    episodes = relationship("Episode", back_populates="podcast")

class Episode(Base):
    __tablename__ = 'episodes'
    
    id = Column(Integer, primary_key=True)
    podcast_id = Column(Integer, ForeignKey('podcasts.id'), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    audio_url = Column(String(500), nullable=False)
    duration = Column(Integer)  # Duration in seconds
    published_date = Column(DateTime)
    local_audio_path = Column(String(500))
    is_downloaded = Column(Boolean, default=False)
    is_transcribed = Column(Boolean, default=False)
    
    podcast = relationship("Podcast", back_populates="episodes")
    transcript = relationship("Transcript", back_populates="episode", uselist=False)
    embeddings = relationship("Embedding", back_populates="episode")

class Transcript(Base):
    __tablename__ = 'transcripts'
    
    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey('episodes.id'), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String(100))  # e.g., "whisper-large-v3"
    
    episode = relationship("Episode", back_populates="transcript")
    segments = relationship("TranscriptSegment", back_populates="transcript")

class TranscriptSegment(Base):
    __tablename__ = 'transcript_segments'
    
    id = Column(Integer, primary_key=True)
    transcript_id = Column(Integer, ForeignKey('transcripts.id'), nullable=False)
    content = Column(Text, nullable=False)
    start_time = Column(Float)  # Start time in seconds
    end_time = Column(Float)    # End time in seconds
    speaker = Column(String(100))  # If speaker diarization is used
    
    transcript = relationship("Transcript", back_populates="segments")
    embedding = relationship("Embedding", back_populates="segment", uselist=False)

class Embedding(Base):
    __tablename__ = 'embeddings'
    
    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey('episodes.id'), nullable=False)
    segment_id = Column(Integer, ForeignKey('transcript_segments.id'))
    embedding_vector = Column(Text, nullable=False)  # Stored as JSON string
    model_used = Column(String(100))  # e.g., "BGE-M3"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    episode = relationship("Episode", back_populates="embeddings")
    segment = relationship("TranscriptSegment", back_populates="embedding") 