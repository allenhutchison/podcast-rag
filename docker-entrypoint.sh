#!/bin/sh
set -e

# If DOPPLER_TOKEN is set, wrap the command with doppler run
# to inject secrets from Doppler into the environment.
# Otherwise, execute the command directly (backward compatibility
# for CI, Cloud Run with direct env vars, local dev).
if [ -n "$DOPPLER_TOKEN" ]; then
    exec doppler run -- "$@"
else
    exec "$@"
fi
