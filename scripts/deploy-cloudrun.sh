#!/usr/bin/env bash
# Deploys the production image (site + on-demand analysis in one container) to Google Cloud Run.
# Cloud Build builds the Dockerfile remotely, so Docker is not needed locally. The API key goes
# to Secret Manager, and a Cloud Storage bucket keeps every analysis so no filing is paid for
# twice. The service scales to zero: it costs nothing while nobody uses it.
#
# Requirements: the gcloud CLI logged in on a project with billing enabled, and .env with
# SEC_USER_AGENT. PERPLEXITY_API_KEY is stored in Secret Manager when given; without it the key
# already there is used.
#
# Two deployments share the code, the bucket and so the spending ledger and caps:
#   make deploy       earnings-radar, public, on earningsradar.app
#   make deploy-hub   earnings-radar-hub, inside Market Hub: HUB_URL set, only people signed in
#                     to the hub get in (the hub's secret comes from market-hub-session-secret)
#
# Optional overrides: GCP_PROJECT, GCP_REGION, SERVICE_NAME, MAX_INSTANCES, RADAR_DAILY_MAX_USD,
# RADAR_TOTAL_MAX_USD, HUB_URL (from the environment only, never from .env).
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
HUB_URL="${HUB_URL:-}"
if [[ -n "$HUB_URL" && "$SERVICE_NAME" == "earnings-radar" ]]; then
  fail "earnings-radar is the public service of earningsradar.app: it does not go behind the hub's sign-in. Use make deploy-hub."
fi
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
  [[ -n "$API_KEY" ]] || fail "PERPLEXITY_API_KEY is empty in $ENV_FILE and there is no secret $SECRET yet."
  gcp secrets create "$SECRET" --replication-policy automatic >/dev/null
fi
# Only add a version when the key changed, so redeploys don't pile up versions.
if [[ -n "$API_KEY" && "$(gcp secrets versions access latest --secret "$SECRET" 2>/dev/null || true)" != "$API_KEY" ]]; then
  printf '%s' "$API_KEY" | gcp secrets versions add "$SECRET" --data-file=- >/dev/null
fi
gcp secrets add-iam-policy-binding "$SECRET" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/secretmanager.secretAccessor >/dev/null

SECRETS="PERPLEXITY_API_KEY=$SECRET:latest"
HUB_ENV=""
if [[ -n "$HUB_URL" ]]; then
  gcp secrets describe market-hub-session-secret >/dev/null 2>&1 || fail "Market Hub's secret market-hub-session-secret does not exist. Deploy the hub first."
  gcp secrets add-iam-policy-binding market-hub-session-secret \
    --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/secretmanager.secretAccessor >/dev/null
  SECRETS="$SECRETS,HUB_SESSION_SECRET=market-hub-session-secret:latest"
  HUB_ENV="|HUB_URL=$HUB_URL"
  echo "→ Behind Market Hub's sign-in ($HUB_URL)"
fi

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
  --set-secrets "$SECRETS" \
  --set-env-vars "^|^SEC_USER_AGENT=$SEC_USER_AGENT|RADAR_BUCKET=$BUCKET|RADAR_DAILY_MAX_USD=$RADAR_DAILY_MAX_USD|RADAR_TOTAL_MAX_USD=$RADAR_TOTAL_MAX_USD$HUB_ENV"

URL="$(gcp run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  echo "✓ Deployed: $URL"
else
  fail "Deployed, but $URL/api/health failed. Logs: gcloud run services logs read $SERVICE_NAME --region $GCP_REGION"
fi
