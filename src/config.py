
import os
from dotenv import load_dotenv

class Config:
    def __init__(self, env_file=None):
        # Load environment variables from the specified .env file or default location
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # Environment-based configuration
        self.BASE_DIRECTORY = os.getenv("MEDIA_EMBED_BASE_DIRECTORY", "/opt/podcasts")
        self.WHISPER_PATH = os.getenv("MEDIA_EMBED_WHISPER_PATH", "/path/to/whisper")
        
        # Transcription-related constants
        self.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
        self.TRANSCRIPTION_TEMP_FILE_SUFFIX = ".transcription_in_progress"

    def load_config(self):
        '''Logs or prints the configuration for debugging purposes.'''
        print(f"Base Directory: {self.BASE_DIRECTORY}")
        print(f"Whisper Path: {self.WHISPER_PATH}")
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

# Helper functions
def does_transcription_exist(transcription_file):
    '''Check if the transcription file exists and is not empty.'''
    return os.path.exists(transcription_file) and os.path.getsize(transcription_file) > 0
