"""Tests for argparse_shared module."""

import argparse
import pytest

from src.argparse_shared import (
    get_base_parser,
    add_dry_run_argument,
    add_log_level_argument,
    add_episode_path_argument,
    add_query_argument,
    add_sync_remote_argument,
    add_skip_vectordb_argument,
)


class TestGetBaseParser:
    """Tests for get_base_parser function."""

    def test_returns_argument_parser(self):
        """Test that get_base_parser returns an ArgumentParser."""
        parser = get_base_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_has_env_file_argument(self):
        """Test that the parser has --env-file argument."""
        parser = get_base_parser()
        args = parser.parse_args(["-e", "/path/to/.env"])
        assert args.env_file == "/path/to/.env"

    def test_env_file_defaults_to_none(self):
        """Test that env-file defaults to None."""
        parser = get_base_parser()
        args = parser.parse_args([])
        assert args.env_file is None

    def test_long_form_env_file(self):
        """Test the long form --env-file argument."""
        parser = get_base_parser()
        args = parser.parse_args(["--env-file", "/custom/.env"])
        assert args.env_file == "/custom/.env"


class TestAddDryRunArgument:
    """Tests for add_dry_run_argument function."""

    def test_adds_dry_run_argument(self):
        """Test that dry-run argument is added."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_dry_run_defaults_to_false(self):
        """Test that dry-run defaults to False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_short_form_dry_run(self):
        """Test the short form -d argument."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["-d"])
        assert args.dry_run is True


class TestAddLogLevelArgument:
    """Tests for add_log_level_argument function."""

    def test_adds_log_level_argument(self):
        """Test that log-level argument is added."""
        parser = argparse.ArgumentParser()
        add_log_level_argument(parser)
        args = parser.parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_log_level_defaults_to_info(self):
        """Test that log-level defaults to INFO."""
        parser = argparse.ArgumentParser()
        add_log_level_argument(parser)
        args = parser.parse_args([])
        assert args.log_level == "INFO"

    def test_short_form_log_level(self):
        """Test the short form -l argument."""
        parser = argparse.ArgumentParser()
        add_log_level_argument(parser)
        args = parser.parse_args(["-l", "WARNING"])
        assert args.log_level == "WARNING"


class TestAddEpisodePathArgument:
    """Tests for add_episode_path_argument function."""

    def test_adds_episode_path_argument(self):
        """Test that episode-path argument is added."""
        parser = argparse.ArgumentParser()
        add_episode_path_argument(parser)
        args = parser.parse_args(["--episode-path", "/path/to/episode.mp3"])
        assert args.episode_path == "/path/to/episode.mp3"

    def test_short_form_episode_path(self):
        """Test the short form -p argument."""
        parser = argparse.ArgumentParser()
        add_episode_path_argument(parser)
        args = parser.parse_args(["-p", "/path/to/file.mp3"])
        assert args.episode_path == "/path/to/file.mp3"

    def test_episode_path_is_required(self):
        """Test that episode-path is required."""
        parser = argparse.ArgumentParser()
        add_episode_path_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestAddQueryArgument:
    """Tests for add_query_argument function."""

    def test_adds_query_argument(self):
        """Test that query argument is added."""
        parser = argparse.ArgumentParser()
        add_query_argument(parser)
        args = parser.parse_args(["--query", "test query"])
        assert args.query == "test query"

    def test_short_form_query(self):
        """Test the short form -q argument."""
        parser = argparse.ArgumentParser()
        add_query_argument(parser)
        args = parser.parse_args(["-q", "search term"])
        assert args.query == "search term"

    def test_query_is_required(self):
        """Test that query is required."""
        parser = argparse.ArgumentParser()
        add_query_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestAddSyncRemoteArgument:
    """Tests for add_sync_remote_argument function."""

    def test_adds_sync_remote_argument(self):
        """Test that sync-remote argument is added."""
        parser = argparse.ArgumentParser()
        add_sync_remote_argument(parser)
        args = parser.parse_args(["--sync-remote"])
        assert args.sync_remote is True

    def test_sync_remote_defaults_to_false(self):
        """Test that sync-remote defaults to False."""
        parser = argparse.ArgumentParser()
        add_sync_remote_argument(parser)
        args = parser.parse_args([])
        assert args.sync_remote is False


class TestAddSkipVectordbArgument:
    """Tests for add_skip_vectordb_argument function."""

    def test_adds_skip_vectordb_argument(self):
        """Test that skip-vectordb argument is added."""
        parser = argparse.ArgumentParser()
        add_skip_vectordb_argument(parser)
        args = parser.parse_args(["--skip-vectordb"])
        assert args.skip_vectordb is True

    def test_skip_vectordb_defaults_to_false(self):
        """Test that skip-vectordb defaults to False."""
        parser = argparse.ArgumentParser()
        add_skip_vectordb_argument(parser)
        args = parser.parse_args([])
        assert args.skip_vectordb is False


class TestCombinedArguments:
    """Tests for combining multiple arguments."""

    def test_all_arguments_together(self):
        """Test using all argument helpers together."""
        parser = get_base_parser()
        add_dry_run_argument(parser)
        add_log_level_argument(parser)
        add_sync_remote_argument(parser)
        add_skip_vectordb_argument(parser)

        args = parser.parse_args([
            "-e", "/path/.env",
            "-d",
            "-l", "DEBUG",
            "--sync-remote",
            "--skip-vectordb",
        ])

        assert args.env_file == "/path/.env"
        assert args.dry_run is True
        assert args.log_level == "DEBUG"
        assert args.sync_remote is True
        assert args.skip_vectordb is True
