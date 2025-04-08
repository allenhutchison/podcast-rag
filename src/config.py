import os

from dotenv import load_dotenv


class Config:
    def __init__(self, env_file=None):
        # Load environment variables from the specified .env file or default location
        if (env_file):
            load_dotenv(env_file)
        else:
            load_dotenv()

        # Environment-based configuration
        self.BASE_DIRECTORY = os.getenv("MEDIA_EMBED_BASE_DIRECTORY", "/opt/podcasts")
        
        # Transcription-related constants
        self.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
        self.TRANSCRIPTION_TEMP_FILE_SUFFIX = ".transcription_in_progress"

        # ChromaDB-related constants
        self.CHROMA_DB_HOST = os.getenv("CHROMA_DB_HOST", "localhost")
        self.CHROMA_DB_PORT = os.getenv("CHROMA_DB_PORT", 50051)
        self.CHROMA_DB_COLLECTION = os.getenv("CHROMA_DB_COLLECTION", "podcasts_collection")
        self.INDEX_OUTPUT_SUFFIX = "_index.txt"
        self.INDEX_TEMP_FILE_SUFFIX = ".index_in_progress"

        # Model configuration
        self.OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:27b")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

        # Prompts configuration
        base_dir = os.path.dirname(__file__)
        default_prompts_dir = os.path.join(base_dir, "../prompts")
        self.PROMPTS_DIR = os.getenv("PROMPTS_DIR", default_prompts_dir)

    def load_config(self):
        '''Logs or prints the configuration for debugging purposes.'''
        print(f"Base Directory: {self.BASE_DIRECTORY}")
        print(f"Transcription Suffix: {self.TRANSCRIPTION_OUTPUT_SUFFIX}")

    # Utility functions related to file paths and suffixes
    def build_transcription_file(self, episode_path):
        """Build the path for the transcription file."""
        if not episode_path:
            return None
        return os.path.splitext(episode_path)[0] + ".txt"
        
    def build_temp_file(self, transcription_file):
        """Build the path for the temp file."""
        if not transcription_file:
            return None
        return transcription_file + ".transcription_in_progress"
        
    def is_transcription_in_progress(self, temp_file):
        """Check if transcription is in progress."""
        return temp_file and os.path.exists(temp_file)
        
    def transcription_exists(self, transcription_file):
        """Check if transcription file exists."""
        return transcription_file and os.path.exists(transcription_file)

    def is_mp3_file(self, file_path):
        '''Check if the given file is an MP3.'''
        return os.path.isfile(file_path) and file_path.endswith(".mp3")

# Helper functions
def does_transcription_exist(transcription_file):
    '''Check if the transcription file exists and is not empty.'''
    return os.path.exists(transcription_file) and os.path.getsize(transcription_file) > 0
