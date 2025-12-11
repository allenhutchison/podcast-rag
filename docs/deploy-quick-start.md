# Quick Start: Deploy to Cloud Run

A one-page guide to get your web app deployed quickly.

## Prerequisites Checklist

- [ ] Google Cloud Project with billing enabled
- [ ] `gcloud` CLI installed and authenticated
- [ ] APIs enabled: Cloud Run, Cloud Build, Container Registry
- [ ] `.file_search_cache.json` file exists in project root
- [ ] Gemini API key ready

## 5-Minute Manual Deploy

```bash
# 1. Set your variables
export PROJECT_ID="your-gcp-project-id"
export GEMINI_API_KEY="your-gemini-api-key"
export SERVICE_NAME="podcast-rag-web"
export REGION="us-central1"

# 2. Configure gcloud
gcloud config set project $PROJECT_ID

# 3. Build and push Docker image
docker build -f Dockerfile.web -t gcr.io/$PROJECT_ID/$SERVICE_NAME .
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME

# 4. Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --min-instances 0 \
  --timeout 300 \
  --set-env-vars GEMINI_API_KEY="$GEMINI_API_KEY",GEMINI_MODEL="gemini-2.5-flash",GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts"

# 5. Get your URL
gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)'

# 6. Test it
curl $(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')/health
```

**Done!** Your app is live. 🎉

## Set Up Automated Deploys (Optional)

### Step 1: Store API Key in Secret Manager

```bash
# Create secret
echo -n "$GEMINI_API_KEY" | \
  gcloud secrets create gemini-api-key --data-file=-

# Get your project number
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# Grant Cloud Build access
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 2: Update cloudbuild.yaml

Add secret configuration to `cloudbuild.yaml`:

```yaml
availableSecrets:
  secretManager:
  - versionName: projects/PROJECT_ID/secrets/gemini-api-key/versions/latest
    env: '_GEMINI_API_KEY'
```

Replace `PROJECT_ID` with your actual project ID.

### Step 3: Connect GitHub Repository

1. Go to: https://console.cloud.google.com/cloud-build/triggers
2. Click "Connect Repository"
3. Select GitHub and authorize
4. Choose your `podcast-rag` repository
5. Click "Connect"

### Step 4: Create Build Trigger

1. Click "Create Trigger"
2. Name: `deploy-web-app`
3. Event: Push to branch
4. Source:
   - Repository: Your connected repo
   - Branch: `^main$`
5. Configuration: Cloud Build configuration file
   - Location: `cloudbuild.yaml`
6. Substitution variables:
   - `_REGION`: `us-central1`
   - `_SERVICE_NAME`: `podcast-rag-web`
   - `_GEMINI_MODEL`: `gemini-2.5-flash`
   - `_FILE_SEARCH_STORE_NAME`: `podcast-transcripts`
7. Click "Create"

### Step 5: Deploy by Pushing Code

```bash
git add .
git commit -m "Deploy web app"
git push origin main
```

Cloud Build will automatically build and deploy! 🚀

## Update Deployed App

### Update Code
```bash
git push origin main  # Triggers automatic build
```

### Update Cache File
```bash
# 1. Rebuild cache locally
python scripts/rebuild_cache.py

# 2. Commit and push
git add .file_search_cache.json
git commit -m "Update cache"
git push origin main
```

### Update Environment Variables
```bash
gcloud run services update $SERVICE_NAME \
  --region $REGION \
  --set-env-vars GEMINI_MODEL="gemini-2.5-pro"
```

## Monitoring

### View Logs
```bash
# Stream logs
gcloud run services logs tail $SERVICE_NAME --region $REGION

# View recent logs
gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50
```

### Check Status
```bash
# Service info
gcloud run services describe $SERVICE_NAME --region $REGION

# Recent revisions
gcloud run revisions list --service $SERVICE_NAME --region $REGION
```

### Metrics (Cloud Console)
https://console.cloud.google.com/run?project=$PROJECT_ID

## Troubleshooting

### Build fails: "cache file not found"
```bash
# Make sure cache exists
ls -lh .file_search_cache.json

# Rebuild if needed
python scripts/rebuild_cache.py
```

### Deploy fails: "Permission denied"
```bash
# Grant Cloud Run Admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:your-email@example.com" \
  --role="roles/run.admin"
```

### App returns 500 errors
```bash
# Check logs for errors
gcloud run services logs tail $SERVICE_NAME --region $REGION

# Common issues:
# - GEMINI_API_KEY not set or invalid
# - File Search store name doesn't match
# - Cache file missing from image
```

### Slow responses
```bash
# Increase memory
gcloud run services update $SERVICE_NAME \
  --region $REGION \
  --memory 1Gi
```

## Cost Control

### Set Budget Alert
```bash
# In Cloud Console
# Billing → Budgets & alerts → Create budget
# Set: $10/month alert
```

### Limit Instances
```bash
# Reduce max instances
gcloud run services update $SERVICE_NAME \
  --region $REGION \
  --max-instances 5
```

### Delete Service
```bash
# When done testing
gcloud run services delete $SERVICE_NAME --region $REGION
```

## Custom Domain (Optional)

### Map Your Domain

1. Verify domain ownership in Cloud Console
2. Map domain:
   ```bash
   gcloud run domain-mappings create \
     --service $SERVICE_NAME \
     --domain chat.yourdomain.com \
     --region $REGION
   ```
3. Update DNS records (Cloud Run will show you the records)

## Test Your Deployment

```bash
# Get your URL
URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')

# Health check
curl $URL/health

# Test chat (returns SSE stream)
curl -N "$URL/api/chat?query=What%20topics%20are%20discussed?"

# Open in browser
echo "Open: $URL"
```

## Support

- **Documentation**: See [web-app.md](web-app.md)
- **Issues**: https://github.com/allenhutchison/podcast-rag/issues
- **Cloud Run Docs**: https://cloud.google.com/run/docs

---

**That's it!** Your podcast RAG chat is now live on Cloud Run. 🎉
