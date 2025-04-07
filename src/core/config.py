from pydantic_settings import BaseSettings
from pathlib import Path
import os

class Settings(BaseSettings):
    # Base directories
    BASE_DIR: Path = Path("data")
    PODCASTS_DIR: Path = BASE_DIR / "podcasts"
    TRANSCRIPTS_DIR: Path = BASE_DIR / "transcripts"
    CHROMA_DIR: Path = BASE_DIR / "chroma"
    
    # Database
    DATABASE_URL: str = "sqlite:///./data/podcast_rag.db"
    
    # API Keys
    OPENAI_API_KEY: str = ""
    
    # Model settings
    TRANSCRIPTION_MODEL: str = "large-v3"
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    
    # API settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Create necessary directories
        self.BASE_DIR.mkdir(exist_ok=True)
        self.PODCASTS_DIR.mkdir(exist_ok=True)
        self.TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        self.CHROMA_DIR.mkdir(exist_ok=True)

# Create global settings instance
settings = Settings() 