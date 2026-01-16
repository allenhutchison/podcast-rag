"""Tests for prompt manager module."""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch

from src.prompt_manager import PromptManager, _extract_placeholders


class TestExtractPlaceholders:
    """Tests for _extract_placeholders helper function."""

    def test_extract_dollar_identifier(self):
        """Test extracting $identifier style placeholders."""
        result = _extract_placeholders("Hello $name!")
        assert result == {"name"}

    def test_extract_braced_identifier(self):
        """Test extracting ${identifier} style placeholders."""
        result = _extract_placeholders("Hello ${name}!")
        assert result == {"name"}

    def test_extract_multiple_placeholders(self):
        """Test extracting multiple placeholders."""
        result = _extract_placeholders("Hello $name, today is ${day}!")
        assert result == {"name", "day"}

    def test_extract_no_placeholders(self):
        """Test with no placeholders."""
        result = _extract_placeholders("Hello world!")
        assert result == set()

    def test_extract_repeated_placeholder(self):
        """Test that repeated placeholders appear once."""
        result = _extract_placeholders("$name and $name")
        assert result == {"name"}

    def test_extract_underscored_placeholder(self):
        """Test placeholder with underscore."""
        result = _extract_placeholders("Hello $first_name!")
        assert result == {"first_name"}


class TestPromptManager:
    """Tests for PromptManager class."""

    @pytest.fixture
    def prompts_dir(self, tmp_path):
        """Create a temporary prompts directory with test templates."""
        prompts = tmp_path / "prompts"
        prompts.mkdir()

        # Create test prompt files
        (prompts / "greeting.txt").write_text("Hello $name!")
        (prompts / "complex.txt").write_text("Hello $name, you are ${age} years old.")
        (prompts / "no_vars.txt").write_text("This is a static prompt.")

        return prompts

    @pytest.fixture
    def mock_config(self, prompts_dir):
        """Create mock config pointing to prompts directory."""
        config = Mock()
        config.PROMPTS_DIR = str(prompts_dir)
        return config

    def test_init_loads_templates(self, mock_config):
        """Test that init loads prompt templates."""
        manager = PromptManager(mock_config, print_results=False)

        assert "greeting" in manager._templates
        assert "complex" in manager._templates
        assert "no_vars" in manager._templates

    def test_init_extracts_placeholders(self, mock_config):
        """Test that init extracts placeholders from templates."""
        manager = PromptManager(mock_config, print_results=False)

        assert manager._template_placeholders["greeting"] == {"name"}
        assert manager._template_placeholders["complex"] == {"name", "age"}
        assert manager._template_placeholders["no_vars"] == set()

    def test_build_prompt_simple(self, mock_config):
        """Test building a simple prompt."""
        manager = PromptManager(mock_config, print_results=False)

        result = manager.build_prompt("greeting", name="World")

        assert result == "Hello World!"

    def test_build_prompt_multiple_vars(self, mock_config):
        """Test building prompt with multiple variables."""
        manager = PromptManager(mock_config, print_results=False)

        result = manager.build_prompt("complex", name="Alice", age="30")

        assert result == "Hello Alice, you are 30 years old."

    def test_build_prompt_no_vars(self, mock_config):
        """Test building prompt with no variables."""
        manager = PromptManager(mock_config, print_results=False)

        result = manager.build_prompt("no_vars")

        assert result == "This is a static prompt."

    def test_build_prompt_missing_template(self, mock_config):
        """Test error when template not found."""
        manager = PromptManager(mock_config, print_results=False)

        with pytest.raises(ValueError) as exc_info:
            manager.build_prompt("nonexistent")

        assert "No template named 'nonexistent'" in str(exc_info.value)

    def test_build_prompt_missing_placeholder(self, mock_config):
        """Test error when required placeholder is missing."""
        manager = PromptManager(mock_config, print_results=False)

        with pytest.raises(ValueError) as exc_info:
            manager.build_prompt("greeting")  # Missing 'name'

        assert "Missing required placeholders" in str(exc_info.value)
        assert "name" in str(exc_info.value)

    def test_build_prompt_extra_kwargs_ignored(self, mock_config):
        """Test that extra kwargs don't cause errors."""
        manager = PromptManager(mock_config, print_results=False)

        # Should not raise, extra 'unused' is ignored
        result = manager.build_prompt("greeting", name="World", unused="value")

        assert result == "Hello World!"


class TestPromptManagerEdgeCases:
    """Edge case tests for PromptManager."""

    def test_missing_prompts_directory(self, tmp_path):
        """Test handling of missing prompts directory."""
        config = Mock()
        config.PROMPTS_DIR = str(tmp_path / "nonexistent")

        # Should not raise, just log warning
        manager = PromptManager(config, print_results=False)

        assert manager._templates == {}

    def test_empty_prompts_directory(self, tmp_path):
        """Test handling of empty prompts directory."""
        empty_dir = tmp_path / "empty_prompts"
        empty_dir.mkdir()

        config = Mock()
        config.PROMPTS_DIR = str(empty_dir)

        manager = PromptManager(config, print_results=False)

        assert manager._templates == {}

    def test_non_txt_files_ignored(self, tmp_path):
        """Test that non-.txt files are ignored."""
        prompts = tmp_path / "prompts"
        prompts.mkdir()

        (prompts / "valid.txt").write_text("Hello $name!")
        (prompts / "invalid.md").write_text("# Markdown file")
        (prompts / "config.json").write_text("{}")

        config = Mock()
        config.PROMPTS_DIR = str(prompts)

        manager = PromptManager(config, print_results=False)

        assert "valid" in manager._templates
        assert "invalid" not in manager._templates
        assert "config" not in manager._templates
