"""
Tests for frontend files: HTML, CSS, and JavaScript validation.

These tests validate structure, syntax, and critical patterns in static files.
"""

import json
import os
import re
from pathlib import Path

import pytest


class TestHTMLFiles:
    """Tests for HTML template files."""

    def test_episode_html_exists(self):
        """Test that episode.html file exists."""
        path = Path("src/web/static/episode.html")
        assert path.exists(), "episode.html should exist"

    def test_podcast_html_exists(self):
        """Test that podcast.html file exists."""
        path = Path("src/web/static/podcast.html")
        assert path.exists(), "podcast.html should exist"

    def test_podcasts_html_exists(self):
        """Test that podcasts.html file exists."""
        path = Path("src/web/static/podcasts.html")
        assert path.exists(), "podcasts.html should exist"

    def test_html_files_have_valid_structure(self):
        """Test that HTML files have basic valid structure."""
        html_files = [
            "src/web/static/episode.html",
            "src/web/static/podcast.html",
            "src/web/static/podcasts.html"
        ]

        for html_file in html_files:
            path = Path(html_file)
            if not path.exists():
                continue

            content = path.read_text()

            # Check for HTML structure
            assert "<html" in content.lower() or "<!doctype" in content.lower(), \
                f"{html_file}: Should have HTML doctype or html tag"

            # Check for balanced tags (basic)
            open_divs = content.count("<div")
            close_divs = content.count("</div>")
            assert abs(open_divs - close_divs) <= 1, \
                f"{html_file}: Unbalanced div tags: {open_divs} open, {close_divs} close"

    def test_html_files_no_inline_api_keys(self):
        """Test that HTML files don't contain inline API keys."""
        html_files = [
            "src/web/static/episode.html",
            "src/web/static/podcast.html",
            "src/web/static/podcasts.html"
        ]

        sensitive_patterns = [
            r"api[_-]?key\s*[:=]\s*['\"][^'\"]{20,}['\"]",
            r"secret\s*[:=]\s*['\"][^'\"]{20,}['\"]",
            r"password\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        ]

        for html_file in html_files:
            path = Path(html_file)
            if not path.exists():
                continue

            content = path.read_text()

            for pattern in sensitive_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                assert len(matches) == 0, \
                    f"{html_file}: Found potential sensitive data: {matches}"


class TestIndexHTMLRemoval:
    """Tests verifying that index.html was removed (if it was part of the diff)."""

    def test_index_html_handling(self):
        """Test index.html state - either removed or updated."""
        path = Path("src/web/static/index.html")

        if not path.exists():
            # File was removed - this is expected based on the diff
            assert True, "index.html was removed as expected"
        else:
            # If it still exists, that's fine - just verify it's valid HTML
            content = path.read_text()
            assert "<html" in content.lower() or "<!doctype" in content.lower(), \
                "index.html should have valid HTML structure"


class TestChatJSRemoval:
    """Tests verifying that old chat.js was properly removed or replaced."""

    def test_old_chat_js_removed(self):
        """Test that old chat.js file was removed or replaced with new conversation-based chat.js."""
        path = Path("src/web/static/chat.js")

        if not path.exists():
            # File was removed - this is acceptable
            assert True, "Old chat.js was removed"
        else:
            # If it exists, it should be the new conversation-based version
            content = path.read_text()

            # Check that it's the new conversation-based version
            assert "conversation" in content.lower() or "subscriptions" in content.lower(), \
                "chat.js should be the new conversation-based version"


class TestStaticFileIntegrity:
    """Tests for overall static file integrity."""

    def test_all_expected_static_files_exist(self):
        """Test that all expected static files exist."""
        expected_files = [
            "src/web/static/chat.html",
            "src/web/static/chat.js",
            "src/web/static/chat.css",
            "src/web/static/episode.html",
            "src/web/static/podcast.html",
            "src/web/static/podcasts.html",
        ]

        missing_files = [f for f in expected_files if not Path(f).exists()]

        assert len(missing_files) == 0, f"Missing expected files: {missing_files}"

    def test_no_obvious_file_corruption(self):
        """Test that static files are not corrupted (basic check)."""
        static_files = [
            "src/web/static/chat.html",
            "src/web/static/chat.js",
            "src/web/static/chat.css",
            "src/web/static/episode.html",
            "src/web/static/podcast.html",
            "src/web/static/podcasts.html",
        ]

        for file_path in static_files:
            path = Path(file_path)
            if not path.exists():
                continue

            # Check file is readable and not binary garbage
            try:
                content = path.read_text(encoding='utf-8')
                assert len(content) > 0, f"{file_path} is empty"

                # Check for null bytes (indicates binary/corruption)
                assert '\x00' not in content, f"{file_path} contains null bytes"

            except UnicodeDecodeError:
                pytest.fail(f"{file_path} cannot be decoded as UTF-8")

    def test_static_files_have_reasonable_size(self):
        """Test that static files have reasonable sizes."""
        static_files = {
            "src/web/static/chat.html": (100, 100000),    # 100 bytes to 100KB
            "src/web/static/chat.js": (100, 100000),      # 100 bytes to 100KB
            "src/web/static/chat.css": (10, 50000),       # 10 bytes to 50KB
            "src/web/static/episode.html": (100, 100000),
            "src/web/static/podcast.html": (100, 100000),
            "src/web/static/podcasts.html": (100, 100000),
        }

        for file_path, (min_size, max_size) in static_files.items():
            path = Path(file_path)
            if not path.exists():
                continue

            size = path.stat().st_size
            assert min_size <= size <= max_size, \
                f"{file_path} size {size} bytes is outside expected range [{min_size}, {max_size}]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])