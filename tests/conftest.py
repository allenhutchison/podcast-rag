"""
Pytest configuration and fixtures for podcast-rag tests.

This module runs before any test imports, setting up the test environment.
Environment variables are explicitly set to ensure deterministic test behavior
regardless of external environment configuration.
"""

import os

# Minimum length for JWT secret key (32 bytes for HS256)
_MIN_JWT_SECRET_LENGTH = 32

# Test JWT secret that meets minimum length requirements
_TEST_JWT_SECRET = "test-jwt-secret-key-for-pytest-minimum-32-chars"

# Force DEV_MODE for tests - ensures consistent behavior
os.environ["DEV_MODE"] = "true"

# Force JWT_SECRET_KEY to a compliant test value
# Overwrite if missing or shorter than required minimum
current_secret = os.environ.get("JWT_SECRET_KEY", "")
if len(current_secret) < _MIN_JWT_SECRET_LENGTH:
    os.environ["JWT_SECRET_KEY"] = _TEST_JWT_SECRET
