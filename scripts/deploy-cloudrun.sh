#!/usr/bin/env bash
# Deploys the production image (site + on-demand analysis in one container) to Google Cloud Run.
# Cloud Build builds the Dockerfile remotely, so Docker is not needed locally. The API key goes
# to Secret Manager, and a Cloud Storage bucket keeps every analysis so no filing is paid for
# twice. The service scales to zero: it costs nothing while nobody uses it.
#
# Requirements: the gcloud CLI logged in on a project with billing enabled, and .env with
# PERPLEXITY_API_KEY and SEC_USER_AGENT.
#
# Optional overrides: GCP_PROJECT, GCP_REGION, SERVICE_NAME, MAX_INSTANCES, RADAR_DAILY_MAX_USD,
# RADAR_TOTAL_MAX_USD.
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
  echo "error: $*" >&2
  exit 1
}

command -v gcloud >/dev/null || fail "gcloud is not installed."

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-earnings-radar}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
# Most the public service may spend on the model in one day (UTC) and over its whole life, in USD.
RADAR_DAILY_MAX_USD="${RADAR_DAILY_MAX_USD:-0.25}"
RADAR_TOTAL_MAX_USD="${RADAR_TOTAL_MAX_USD:-4.00}"
ENV_FILE=".env"
SECRET="earnings-radar-perplexity-api-key"

[[ -n "$GCP_PROJECT" ]] || fail "No GCP project selected. Run 'gcloud init' or set GCP_PROJECT."
[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE not found."
BUCKET="${RADAR_BUCKET:-${GCP_PROJECT}-earnings-radar}"

# Read single values instead of sourcing the file, and drop the quotes around them.
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }
API_KEY="$(env_value PERPLEXITY_API_KEY)"
SEC_USER_AGENT="$(env_value SEC_USER_AGENT)"
[[ -n "$API_KEY" ]] || fail "PERPLEXITY_API_KEY is empty in $ENV_FILE."
[[ "$SEC_USER_AGENT" == *@* ]] || fail "SEC_USER_AGENT in $ENV_FILE needs a contact email."

gcp() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

echo "→ Enabling APIs in $GCP_PROJECT"
gcp services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com

# Source deploys build with, and run as, the Compute Engine default service account.
PROJECT_NUMBER="$(gcp projects describe "$GCP_PROJECT" --format='value(projectNumber)')"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcp projects add-iam-policy-binding "$GCP_PROJECT" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/run.builder --condition=None >/dev/null

echo "→ Secret"
if ! gcp secrets describe "$SECRET" >/dev/null 2>&1; then
  gcp secrets create "$SECRET" --replication-policy automatic >/dev/null
fi
# Only add a version when the key changed, so redeploys don't pile up versions.
if [[ "$(gcp secrets versions access latest --secret "$SECRET" 2>/dev/null || true)" != "$API_KEY" ]]; then
  printf '%s' "$API_KEY" | gcp secrets versions add "$SECRET" --data-file=- >/dev/null
fi
gcp secrets add-iam-policy-binding "$SECRET" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/secretmanager.secretAccessor >/dev/null

echo "→ Bucket gs://$BUCKET"
if ! gcp storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcp storage buckets create "gs://$BUCKET" --location "$GCP_REGION" --uniform-bucket-level-access \
    --public-access-prevention >/dev/null
fi
gcp storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/storage.objectAdmin >/dev/null

echo "→ Building with Cloud Build and deploying '$SERVICE_NAME' to $GCP_REGION (a few minutes)"
# "^|^" makes "|" the separator: the SEC user agent has spaces and an "@", and could have commas.
gcp run deploy "$SERVICE_NAME" \
  --source . \
  --region "$GCP_REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --timeout 120 \
  --set-secrets "PERPLEXITY_API_KEY=$SECRET:latest" \
  --set-env-vars "^|^SEC_USER_AGENT=$SEC_USER_AGENT|RADAR_BUCKET=$BUCKET|RADAR_DAILY_MAX_USD=$RADAR_DAILY_MAX_USD|RADAR_TOTAL_MAX_USD=$RADAR_TOTAL_MAX_USD"

URL="$(gcp run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
if curl -fsS "$URL/api/health" >/dev/null; then
  echo "✓ Deployed: $URL"
else
  fail "Deployed, but $URL/api/health failed. Logs: gcloud run services logs read $SERVICE_NAME --region $GCP_REGION"
fi
