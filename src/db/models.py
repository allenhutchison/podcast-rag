
import enum
from sqlalchemy import (create_engine, Column, Integer, String, Text,
                        TIMESTAMP, ForeignKey, Enum, ARRAY)
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class EpisodeRole(enum.Enum):
    HOST = "host"
    GUEST = "guest"

class Podcast(Base):
    __tablename__ = 'podcasts'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    
    episodes = relationship("Episode", back_populates="podcast", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = 'episodes'
    id: Mapped[int] = mapped_column(primary_key=True)
    podcast_id: Mapped[int] = mapped_column(ForeignKey('podcasts.id'), nullable=False)
    guid: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    published_date: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    audio_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=True)
    full_transcript: Mapped[str] = mapped_column(Text, nullable=True)
    
    transcription_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    chunking_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    metadata_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    podcast = relationship("Podcast", back_populates="episodes")
    people = relationship("EpisodePeople", back_populates="episode")
    transcript_chunks = relationship("TranscriptChunk", back_populates="episode", cascade="all, delete-orphan")

class Person(Base):
    __tablename__ = 'people'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    episodes = relationship("EpisodePeople", back_populates="person")

class EpisodePeople(Base):
    __tablename__ = 'episode_people'
    episode_id: Mapped[int] = mapped_column(ForeignKey('episodes.id'), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('people.id'), primary_key=True)
    role: Mapped[EpisodeRole] = mapped_column(Enum(EpisodeRole), primary_key=True)

    episode = relationship("Episode", back_populates="people")
    person = relationship("Person", back_populates="episodes")

class TranscriptChunk(Base):
    __tablename__ = 'transcript_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey('episodes.id'), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_time_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    end_time_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))

    episode = relationship("Episode", back_populates="transcript_chunks")
