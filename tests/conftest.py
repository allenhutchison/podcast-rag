"""
Pytest configuration and fixtures for podcast-rag tests.

This module runs before any test imports, setting up the test environment.
"""

import os

# Set DEV_MODE for tests - this allows the app to run without JWT_SECRET_KEY
# by using an insecure dev key (which is fine for testing)
os.environ.setdefault("DEV_MODE", "true")

# Set a test JWT secret key if not already set
# This ensures consistent behavior across test runs
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
