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

        # Podcast directory (where audio files are stored)
        self.PODCAST_DOWNLOAD_DIRECTORY = os.getenv(
            "PODCAST_DOWNLOAD_DIRECTORY", "/opt/podcasts"
        )
        
        # Transcription-related constants
        self.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
        self.TRANSCRIPTION_TEMP_FILE_SUFFIX = ".transcription_in_progress"

        # Whisper transcription configuration
        # Model options: tiny, base, small, medium, large-v3
        # Recommend "medium" for best balance of speed and accuracy
        self.WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
        self.WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
        # Compute type: float16 (GPU), int8 (CPU), float32
        self.WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

        # Model configuration
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Gemini File Search configuration
        self.GEMINI_FILE_SEARCH_STORE_NAME = os.getenv("GEMINI_FILE_SEARCH_STORE_NAME", "podcast-transcripts")

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

        # Web app base URL (used for email links and OAuth redirect)
        web_base_url = os.getenv("WEB_BASE_URL", "")
        if web_base_url and not web_base_url.lower().startswith(("http://", "https://")):
            raise ValueError(
                f"WEB_BASE_URL must start with http:// or https://, got: {web_base_url}"
            )
        self.WEB_BASE_URL = web_base_url.rstrip("/") if web_base_url else ""

        # Google OAuth configuration
        self.GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
        self.GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
        # Derive redirect URI from WEB_BASE_URL if not explicitly set
        self.GOOGLE_REDIRECT_URI = os.getenv(
            "GOOGLE_REDIRECT_URI",
            f"{self.WEB_BASE_URL}/auth/callback" if self.WEB_BASE_URL else ""
        )

        # JWT configuration
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM = "HS256"
        self.JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))

        # Cookie configuration
        self.COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None) or None  # None = current domain
        self.COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

        # Email configuration (Resend)
        self.RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
        self.RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "podcast@podcasts.hutchison.org")
        self.RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "Podcast RAG")

        # Email digest settings
        self.EMAIL_DIGEST_SEND_HOUR = int(os.getenv("EMAIL_DIGEST_SEND_HOUR", "8"))  # 8 AM
        if not 0 <= self.EMAIL_DIGEST_SEND_HOUR <= 23:
            raise ValueError(
                f"EMAIL_DIGEST_SEND_HOUR must be between 0 and 23, got {self.EMAIL_DIGEST_SEND_HOUR}"
            )
        self.EMAIL_DIGEST_TIMEZONE = os.getenv("EMAIL_DIGEST_TIMEZONE", "America/Los_Angeles")

        # Database configuration
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL", "sqlite:///./podcast_rag.db"
        )
        self.DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "3"))  # Supabase-optimized
        self.DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "2"))  # Supabase-optimized
        self.DB_POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
        self.DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

        # Supabase configuration (for future features)
        self.SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        self.SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
        self.SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

        # Podcast download configuration
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
        """
        print(f"Podcast Directory: {self.PODCAST_DOWNLOAD_DIRECTORY}")
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