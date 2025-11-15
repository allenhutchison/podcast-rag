import os

from dotenv import load_dotenv


class Config:
    def __init__(self, env_file=None):
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # PostgreSQL Configuration
        db_user = os.getenv("POSTGRES_USER", "podcast_rag_user")
        db_password = os.getenv("POSTGRES_PASSWORD", "insecure_password_change_me")
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "podcast_rag_db")
        self.DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        os.environ['DATABASE_URL'] = self.DATABASE_URL # Set it for other modules

        # Environment-based configuration
        self.BASE_DIRECTORY = os.getenv("MEDIA_EMBED_BASE_DIRECTORY", "/opt/podcasts")
        
        # Transcription-related constants
        self.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
        self.TRANSCRIPTION_TEMP_FILE_SUFFIX = ".transcription_in_progress"

        # Model configuration
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Gemini File Search configuration
        self.GEMINI_FILE_SEARCH_STORE_NAME = os.getenv("GEMINI_FILE_SEARCH_STORE_NAME", "podcast-transcripts")
        self.GEMINI_CHUNK_SIZE = int(os.getenv("GEMINI_CHUNK_SIZE", "1000"))
        self.GEMINI_CHUNK_OVERLAP = int(os.getenv("GEMINI_CHUNK_OVERLAP", "100"))

        # File Search compatible models
        self.FILE_SEARCH_COMPATIBLE_MODELS = [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-exp",
            "gemini-2.5-pro-exp"
        ]

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
        '''Generate the transcription file path based on episode file path.'''
        return os.path.splitext(episode_path)[0] + self.TRANSCRIPTION_OUTPUT_SUFFIX

    def build_temp_file(self, transcription_file):
        '''Generate the temp file path for in-progress transcriptions.'''
        return transcription_file + self.TRANSCRIPTION_TEMP_FILE_SUFFIX

    def is_transcription_file(self, file_path):
        '''Check if the given file is a transcription file.'''
        return os.path.isfile(file_path) and file_path.endswith(self.TRANSCRIPTION_OUTPUT_SUFFIX)

    def is_mp3_file(self, file_path):
        '''Check if the given file is an MP3.'''
        return os.path.isfile(file_path) and file_path.endswith(".mp3")

    def is_transcription_in_progress(self, temp_file):
        '''Check if a transcription is in progress.'''
        return os.path.exists(temp_file)

    def transcription_exists(self, transcription_file):
        '''Check if the transcription already exists using helper function from config.'''
        return os.path.exists(transcription_file) and os.path.getsize(transcription_file) > 0

    def validate_file_search_model(self):
        """
        Validate that the configured model is compatible with File Search.

        Raises:
            ValueError: If model is not compatible with File Search
        """
        # Extract base model name (remove version suffixes if present)
        model_base = self.GEMINI_MODEL.split(':')[0]  # Handle versioned models

        if not any(compatible in model_base for compatible in self.FILE_SEARCH_COMPATIBLE_MODELS):
            raise ValueError(
                f"Model '{self.GEMINI_MODEL}' is not compatible with Gemini File Search. "
                f"Compatible models: {', '.join(self.FILE_SEARCH_COMPATIBLE_MODELS)}. "
                f"Please update GEMINI_MODEL in your .env file."
            )

# Helper functions
def does_transcription_exist(transcription_file):
    '''Check if the transcription file exists and is not empty.'''
    return os.path.exists(transcription_file) and os.path.getsize(transcription_file) > 0
