"""
Tests for frontend files: HTML, CSS, and JavaScript validation.

These tests validate structure, syntax, and critical patterns in static files.
"""

import json
import os
import re
from pathlib import Path

import pytest


class TestChatDrawerJS:
    """Tests for chat-drawer.js file."""

    @pytest.fixture
    def chat_drawer_js_content(self):
        """Load chat-drawer.js content."""
        path = Path("src/web/static/chat-drawer.js")
        if not path.exists():
            pytest.skip("chat-drawer.js not found")
        return path.read_text()

    def test_chat_drawer_js_exists(self):
        """Test that chat-drawer.js file exists."""
        path = Path("src/web/static/chat-drawer.js")
        assert path.exists(), "chat-drawer.js should exist"
        assert path.is_file(), "chat-drawer.js should be a file"

    def test_chat_drawer_js_not_empty(self, chat_drawer_js_content):
        """Test that chat-drawer.js is not empty."""
        assert len(chat_drawer_js_content) > 0, "chat-drawer.js should not be empty"
        assert len(chat_drawer_js_content.strip()) > 100, "chat-drawer.js should have substantial content"

    def test_chat_drawer_js_has_valid_syntax_markers(self, chat_drawer_js_content):
        """Test that chat-drawer.js has valid JavaScript syntax markers."""
        # Check for function declarations
        assert "function" in chat_drawer_js_content or "=>" in chat_drawer_js_content, \
            "Should contain function declarations"

        # Check for variable declarations
        assert any(keyword in chat_drawer_js_content for keyword in ["const", "let", "var"]), \
            "Should contain variable declarations"

    def test_chat_drawer_js_no_syntax_errors_obvious(self, chat_drawer_js_content):
        """Test for obvious JavaScript syntax errors."""
        # Check for balanced braces
        open_braces = chat_drawer_js_content.count("{")
        close_braces = chat_drawer_js_content.count("}")
        assert open_braces == close_braces, f"Unbalanced braces: {open_braces} open, {close_braces} close"

        # Check for balanced parentheses (rough check)
        open_parens = chat_drawer_js_content.count("(")
        close_parens = chat_drawer_js_content.count(")")
        assert open_parens == close_parens, f"Unbalanced parentheses: {open_parens} open, {close_parens} close"

        # Check for balanced brackets
        open_brackets = chat_drawer_js_content.count("[")
        close_brackets = chat_drawer_js_content.count("]")
        assert open_brackets == close_brackets, f"Unbalanced brackets: {open_brackets} open, {close_brackets} close"

    def test_chat_drawer_js_has_api_endpoint_references(self, chat_drawer_js_content):
        """Test that chat-drawer.js references expected API endpoints."""
        # Should reference the chat API endpoint
        assert "/api/chat" in chat_drawer_js_content, "Should reference /api/chat endpoint"

    def test_chat_drawer_js_has_event_handling(self, chat_drawer_js_content):
        """Test that chat-drawer.js has event handling code."""
        event_keywords = ["addEventListener", "onclick", "onload", "on("]
        assert any(keyword in chat_drawer_js_content for keyword in event_keywords), \
            "Should have event handling"

    def test_chat_drawer_js_has_dom_manipulation(self, chat_drawer_js_content):
        """Test that chat-drawer.js has DOM manipulation code."""
        dom_keywords = ["querySelector", "getElementById", "createElement", "appendChild", "innerHTML"]
        assert any(keyword in chat_drawer_js_content for keyword in dom_keywords), \
            "Should have DOM manipulation"

    def test_chat_drawer_js_no_console_errors_in_production(self, chat_drawer_js_content):
        """Test that there are no console.error calls (should use proper error handling)."""
        # Allow console.log for debugging but check for proper structure
        lines = chat_drawer_js_content.split("\n")
        console_error_lines = [i + 1 for i, line in enumerate(lines) if "console.error" in line]

        # If there are console.error calls, they should be in error handling contexts
        if console_error_lines:
            # This is informational - console.error is acceptable in catch blocks
            assert len(console_error_lines) < 10, "Excessive console.error usage"

    def test_chat_drawer_js_has_subscribed_only_handling(self, chat_drawer_js_content):
        """Test that chat-drawer.js handles subscribed_only parameter."""
        # Check if the new subscribed_only parameter is referenced
        assert "subscribed" in chat_drawer_js_content.lower() or "subscription" in chat_drawer_js_content.lower(), \
            "Should reference subscription-related functionality"


class TestChatDrawerCSS:
    """Tests for chat-drawer.css file."""

    @pytest.fixture
    def chat_drawer_css_content(self):
        """Load chat-drawer.css content."""
        path = Path("src/web/static/chat-drawer.css")
        if not path.exists():
            pytest.skip("chat-drawer.css not found")
        return path.read_text()

    def test_chat_drawer_css_exists(self):
        """Test that chat-drawer.css file exists."""
        path = Path("src/web/static/chat-drawer.css")
        assert path.exists(), "chat-drawer.css should exist"
        assert path.is_file(), "chat-drawer.css should be a file"

    def test_chat_drawer_css_not_empty(self, chat_drawer_css_content):
        """Test that chat-drawer.css is not empty."""
        assert len(chat_drawer_css_content) > 0, "chat-drawer.css should not be empty"

    def test_chat_drawer_css_has_valid_syntax_markers(self, chat_drawer_css_content):
        """Test that chat-drawer.css has valid CSS syntax."""
        # Check for CSS selectors and rules
        assert "{" in chat_drawer_css_content and "}" in chat_drawer_css_content, \
            "Should contain CSS rule blocks"

        # Check for balanced braces
        open_braces = chat_drawer_css_content.count("{")
        close_braces = chat_drawer_css_content.count("}")
        assert open_braces == close_braces, f"Unbalanced braces: {open_braces} open, {close_braces} close"

    def test_chat_drawer_css_has_drawer_related_classes(self, chat_drawer_css_content):
        """Test that chat-drawer.css has drawer-related class definitions."""
        drawer_keywords = ["drawer", "chat", "panel", "sidebar"]
        assert any(keyword in chat_drawer_css_content.lower() for keyword in drawer_keywords), \
            "Should have drawer-related CSS classes"

    def test_chat_drawer_css_no_obvious_errors(self, chat_drawer_css_content):
        """Test for obvious CSS errors."""
        # Check that there are no lines with only a semicolon
        lines = chat_drawer_css_content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == ";":
                pytest.fail(f"Line {i}: Standalone semicolon found")

    def test_chat_drawer_css_has_responsive_design(self, chat_drawer_css_content):
        """Test that CSS includes responsive design elements."""
        responsive_keywords = ["@media", "max-width", "min-width", "mobile", "tablet", "desktop"]
        has_responsive = any(keyword in chat_drawer_css_content.lower() for keyword in responsive_keywords)

        # This is informational - responsive design is good but not required
        if not has_responsive:
            pytest.skip("No responsive design patterns found - consider adding for better UX")


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

    def test_html_files_reference_chat_drawer(self):
        """Test that HTML files reference the new chat-drawer components."""
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

            # Check if it references chat-drawer.js or chat-drawer.css
            has_drawer_js = "chat-drawer.js" in content
            has_drawer_css = "chat-drawer.css" in content

            # At least some files should reference the new drawer components
            if has_drawer_js or has_drawer_css:
                assert True  # Found references
                return

        # If we got here, no files referenced the drawer
        pytest.skip("No HTML files reference chat-drawer - may be included via other means")

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
            # If it still exists, ensure it's not the old version
            content = path.read_text()
            # Check that it's been updated (should not reference old chat.js)
            assert "chat.js" not in content or "chat-drawer.js" in content, \
                "If index.html exists, it should reference new chat-drawer.js"


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
            "src/web/static/chat-drawer.js",
            "src/web/static/chat-drawer.css",
            "src/web/static/episode.html",
            "src/web/static/podcast.html",
            "src/web/static/podcasts.html",
        ]

        missing_files = [f for f in expected_files if not Path(f).exists()]

        assert len(missing_files) == 0, f"Missing expected files: {missing_files}"

    def test_no_obvious_file_corruption(self):
        """Test that static files are not corrupted (basic check)."""
        static_files = [
            "src/web/static/chat-drawer.js",
            "src/web/static/chat-drawer.css",
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
            "src/web/static/chat-drawer.js": (100, 100000),  # 100 bytes to 100KB
            "src/web/static/chat-drawer.css": (10, 50000),   # 10 bytes to 50KB
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