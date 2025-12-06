import os

from dotenv import load_dotenv


class Config:
    def __init__(self, env_file=None):
        """
        Initialize configuration by loading environment variables and setting default attributes.
        
        Loads environment variables from the provided .env file path when `env_file` is given; otherwise loads from the default environment. After loading, sets configuration attributes (paths, transcription constants, model and file-search settings, prompts location, web app settings, ADK timeout, database connection parameters, and podcast download options) using environment values with sensible defaults.
        Parameters:
            env_file (str | None): Optional path to a .env file to load environment variables from. If omitted, the default environment or default .env discovery is used.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

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
        self.GCS_METADATA_BUCKET = os.getenv("GCS_METADATA_BUCKET")

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

        # Web application configuration
        self.WEB_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
        self.WEB_MAX_CONVERSATION_TOKENS = int(os.getenv("MAX_CONVERSATION_TOKENS", "200000"))
        self.WEB_STREAMING_DELAY = float(os.getenv("STREAMING_DELAY", "0.05"))
        self.WEB_RATE_LIMIT = os.getenv("RATE_LIMIT", "10/minute")
        self.WEB_PORT = int(os.getenv("PORT", "8080"))

        # ADK (Agent Development Kit) configuration
        self.ADK_PARALLEL_TIMEOUT = int(os.getenv("ADK_PARALLEL_TIMEOUT", "30"))

        # Database configuration
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL", "sqlite:///./podcast_rag.db"
        )
        self.DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
        self.DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        self.DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

        # Podcast download configuration
        self.PODCAST_DOWNLOAD_DIRECTORY = os.getenv(
            "PODCAST_DOWNLOAD_DIRECTORY", self.BASE_DIRECTORY
        )
        self.PODCAST_MAX_CONCURRENT_DOWNLOADS = int(
            os.getenv("PODCAST_MAX_CONCURRENT_DOWNLOADS", "10")
        )
        self.PODCAST_DOWNLOAD_RETRY_ATTEMPTS = int(
            os.getenv("PODCAST_DOWNLOAD_RETRY_ATTEMPTS", "3")
        )
        self.PODCAST_DOWNLOAD_TIMEOUT = int(
            os.getenv("PODCAST_DOWNLOAD_TIMEOUT", "300")
        )
        self.PODCAST_CHUNK_SIZE = int(
            os.getenv("PODCAST_CHUNK_SIZE", "8192")
        )

    def load_config(self):
        """
        Prints selected configuration values useful for debugging.
        
        Specifically displays the configured BASE_DIRECTORY and TRANSCRIPTION_OUTPUT_SUFFIX to standard output.
        """
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