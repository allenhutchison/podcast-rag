#!/bin/bash
# Setup Cloud Run environment variables and secrets for podcast-rag-web
# Reads configuration from .env file as single source of truth

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# Check if .env exists
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    exit 1
fi

echo "🚀 Setting up Cloud Run environment from .env file"
echo "=================================================="
echo "Reading configuration from: $ENV_FILE"
echo ""

# Load .env file (handle comments and empty lines)
set -a  # Export all variables
# More robust .env parsing that handles inline comments
while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    # Remove inline comments and export
    line="${line%%#*}"
    [[ -n "$line" ]] && export "$line"
done < "$ENV_FILE"
set +a

# Validate required Cloud Run variables
if [[ -z "$CLOUD_RUN_SERVICE" ]]; then
    echo "❌ Error: CLOUD_RUN_SERVICE not set in .env"
    exit 1
fi

if [[ -z "$CLOUD_RUN_REGION" ]]; then
    echo "❌ Error: CLOUD_RUN_REGION not set in .env"
    exit 1
fi

if [[ -z "$CLOUD_RUN_URL" ]]; then
    echo "❌ Error: CLOUD_RUN_URL not set in .env"
    exit 1
fi

echo "Service: $CLOUD_RUN_SERVICE"
echo "Region: $CLOUD_RUN_REGION"
echo "URL: $CLOUD_RUN_URL"
echo ""

# Step 1: Create secrets for sensitive values
echo "📦 Step 1: Creating/updating secrets in Secret Manager..."
echo ""

# create_or_update_secret creates or updates a Google Secret Manager secret with the provided value.
# If a secret with the given name exists, a new version is added; otherwise the secret is created.
# secret_name is the Secret Manager secret name.
# secret_value is the value to store; if empty, the function does nothing and leaves existing secrets unchanged.
create_or_update_secret() {
    local secret_name=$1
    local secret_value=$2

    if [[ -z "$secret_value" ]]; then
        echo "  ⚠️  Skipping $secret_name (empty value)"
        return
    fi

    if gcloud secrets describe "$secret_name" &>/dev/null; then
        echo "  ↻ Updating existing secret: $secret_name"
        echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=-
    else
        echo "  ✓ Creating new secret: $secret_name"
        echo -n "$secret_value" | gcloud secrets create "$secret_name" --data-file=-
    fi
}

# Define which variables should be secrets (sensitive data)
# Store DATABASE_URL as secret instead of exposing password
create_or_update_secret "podcast-rag-database-url" "$DATABASE_URL"
create_or_update_secret "podcast-rag-supabase-service-key" "$SUPABASE_SERVICE_ROLE_KEY"
create_or_update_secret "podcast-rag-gemini-api-key" "$GEMINI_API_KEY"
create_or_update_secret "podcast-rag-google-client-secret" "$GOOGLE_CLIENT_SECRET"
create_or_update_secret "podcast-rag-jwt-secret" "$JWT_SECRET_KEY"

# Optional: SMTP password if configured
if [[ -n "$SMTP_PASSWORD" ]]; then
    create_or_update_secret "podcast-rag-smtp-password" "$SMTP_PASSWORD"
fi

echo ""
echo "✓ All secrets created/updated successfully!"
echo ""

# Step 2: Build environment variables string (non-sensitive config)
echo "⚙️  Step 2: Preparing environment variables..."
echo ""

# Build env vars string for gcloud command
# Include all non-sensitive configuration
ENV_VARS="DB_POOL_SIZE=${DB_POOL_SIZE}"
ENV_VARS="${ENV_VARS},DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW}"
ENV_VARS="${ENV_VARS},DB_POOL_PRE_PING=${DB_POOL_PRE_PING}"
ENV_VARS="${ENV_VARS},DB_ECHO=${DB_ECHO}"
ENV_VARS="${ENV_VARS},SUPABASE_URL=${SUPABASE_URL}"
ENV_VARS="${ENV_VARS},SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}"
ENV_VARS="${ENV_VARS},GEMINI_MODEL=${GEMINI_MODEL}"
ENV_VARS="${ENV_VARS},GEMINI_FILE_SEARCH_STORE_NAME=${GEMINI_FILE_SEARCH_STORE_NAME}"
ENV_VARS="${ENV_VARS},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}"
ENV_VARS="${ENV_VARS},GOOGLE_REDIRECT_URI=${CLOUD_RUN_URL}/auth/callback"
ENV_VARS="${ENV_VARS},JWT_EXPIRATION_DAYS=${JWT_EXPIRATION_DAYS}"
ENV_VARS="${ENV_VARS},COOKIE_SECURE=${COOKIE_SECURE}"
ENV_VARS="${ENV_VARS},ALLOWED_ORIGINS=${ALLOWED_ORIGINS}"
ENV_VARS="${ENV_VARS},MAX_CONVERSATION_TOKENS=${MAX_CONVERSATION_TOKENS}"
ENV_VARS="${ENV_VARS},STREAMING_DELAY=${STREAMING_DELAY}"
ENV_VARS="${ENV_VARS},RATE_LIMIT=${RATE_LIMIT}"
# Note: PORT is automatically set by Cloud Run, don't override it
ENV_VARS="${ENV_VARS},ADK_PARALLEL_TIMEOUT=${ADK_PARALLEL_TIMEOUT}"

# Optional: SMTP configuration (non-sensitive parts)
if [[ -n "$SMTP_HOST" ]]; then
    ENV_VARS="${ENV_VARS},SMTP_HOST=${SMTP_HOST}"
    ENV_VARS="${ENV_VARS},SMTP_PORT=${SMTP_PORT}"
    ENV_VARS="${ENV_VARS},SMTP_USERNAME=${SMTP_USERNAME}"
    ENV_VARS="${ENV_VARS},SMTP_USE_TLS=${SMTP_USE_TLS}"
    ENV_VARS="${ENV_VARS},SMTP_FROM_EMAIL=${SMTP_FROM_EMAIL}"
    ENV_VARS="${ENV_VARS},SMTP_FROM_NAME=${SMTP_FROM_NAME}"
    ENV_VARS="${ENV_VARS},SMTP_TIMEOUT=${SMTP_TIMEOUT}"
fi

# Optional: Email digest settings
if [[ -n "$EMAIL_DIGEST_SEND_HOUR" ]]; then
    ENV_VARS="${ENV_VARS},EMAIL_DIGEST_SEND_HOUR=${EMAIL_DIGEST_SEND_HOUR}"
    ENV_VARS="${ENV_VARS},EMAIL_DIGEST_TIMEZONE=${EMAIL_DIGEST_TIMEZONE}"
fi

# Build secrets string
SECRETS="DATABASE_URL=podcast-rag-database-url:latest"
SECRETS="${SECRETS},SUPABASE_SERVICE_ROLE_KEY=podcast-rag-supabase-service-key:latest"
SECRETS="${SECRETS},GEMINI_API_KEY=podcast-rag-gemini-api-key:latest"
SECRETS="${SECRETS},GOOGLE_CLIENT_SECRET=podcast-rag-google-client-secret:latest"
SECRETS="${SECRETS},JWT_SECRET_KEY=podcast-rag-jwt-secret:latest"

if [[ -n "$SMTP_PASSWORD" ]]; then
    SECRETS="${SECRETS},SMTP_PASSWORD=podcast-rag-smtp-password:latest"
fi

echo "✓ Configuration prepared"
echo ""

# Step 3: Update Cloud Run service
echo "☁️  Step 3: Updating Cloud Run service..."
echo ""

# First, remove any environment variables that should become secrets
# This prevents conflicts when converting from env var to secret
VARS_TO_REMOVE="DATABASE_URL,GEMINI_API_KEY,GOOGLE_CLIENT_SECRET,JWT_SECRET_KEY,SUPABASE_SERVICE_ROLE_KEY"
if [[ -n "$SMTP_PASSWORD" ]]; then
    VARS_TO_REMOVE="${VARS_TO_REMOVE},SMTP_PASSWORD"
fi

echo "Removing conflicting environment variables..."
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --region "$CLOUD_RUN_REGION" \
  --remove-env-vars="$VARS_TO_REMOVE" \
  --quiet 2>/dev/null || true  # Ignore errors if vars don't exist

echo "Updating with secrets and environment variables..."
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --region "$CLOUD_RUN_REGION" \
  --update-secrets="$SECRETS" \
  --update-env-vars="$ENV_VARS"

echo ""
echo "✓ Service configuration updated successfully!"
echo ""

# Step 4: Verify configuration
echo "🔍 Step 4: Verifying configuration..."
echo ""

echo "Environment variables configured:"
gcloud run services describe "$CLOUD_RUN_SERVICE" --region "$CLOUD_RUN_REGION" \
  --format='value(spec.template.spec.containers[0].env[].name)' | sort

echo ""
echo "Secrets mounted:"
gcloud run services describe "$CLOUD_RUN_SERVICE" --region "$CLOUD_RUN_REGION" \
  --format='value(spec.template.spec.containers[0].env[].valueFrom.secretKeyRef.name)' | \
  grep -v '^$' | sort | uniq

echo ""
echo "=================================================="
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Verify Google OAuth redirect URI includes:"
echo "     ${CLOUD_RUN_URL}/auth/callback"
echo "     → https://console.cloud.google.com/apis/credentials"
echo ""
echo "  2. Merge PR #46 to trigger auto-deployment with new dependencies"
echo ""
echo "  3. Test the deployment:"
echo "     curl ${CLOUD_RUN_URL}/health"
echo ""
echo "  4. Check logs if needed:"
echo "     gcloud run services logs read $CLOUD_RUN_SERVICE --region $CLOUD_RUN_REGION --limit 50"
echo ""