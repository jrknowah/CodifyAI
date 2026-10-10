#!/usr/bin/env bash
# ─── Codelyst — deploy one environment to Azure ───────────────────────────────
#
#   ./infra/deploy.sh staging      build images from this commit, deploy staging
#   ./infra/deploy.sh prod         promote an image already tested in staging
#
# Environment variables (all optional):
#   SUBSCRIPTION_ID   Azure subscription to use (default: current `az` account)
#   LOCATION          Azure region (default: southcentralus)
#   IMAGE_TAG         commit SHA to deploy (default: current commit); first 7 chars used
#   ANTHROPIC_API_KEY used on first deploy instead of prompting
#   ROTATE_ANTHROPIC_KEY=1   prompt for a new Anthropic key on a later deploy
#   ALLOW_PROD_BUILD=1       build images straight into prod when they were never
#                            deployed to staging. For the first go-live only; after
#                            that, every prod image must have run in staging first.
#
# In GitHub Actions (CI=true) the script runs non-interactively: no prompts,
# no provider registration, and it refuses to do a first deploy, because first
# deploys generate secrets and must be run by hand once per environment.
#
# Requires: Azure CLI 2.60+ (`az bicep install` once), git, openssl.
# Your account needs Owner (or Contributor + User Access Administrator) on the
# subscription, because the templates create role assignments.

set -euo pipefail

ENV="${1:-}"
if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
  echo "usage: $0 <staging|prod>" >&2
  exit 1
fi

cd "$(dirname "$0")/.."   # repo root

LOCATION="${LOCATION:-southcentralus}"
SHARED_RG="rg-codelyst-shared"
RG="rg-codelyst-${ENV}"
TAG="${IMAGE_TAG:-$(git rev-parse HEAD)}"
TAG="${TAG:0:7}"   # same tag whether deployed by hand or by GitHub Actions
IN_CI="${CI:-false}"

say() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

# ── Account ───────────────────────────────────────────────────────────────────
if [[ -n "${SUBSCRIPTION_ID:-}" ]]; then
  az account set --subscription "$SUBSCRIPTION_ID"
fi
SUB_NAME="$(az account show --query name -o tsv)"
say "Subscription: ${SUB_NAME} | environment: ${ENV} | region: ${LOCATION} | image tag: ${TAG}"

if [[ "$ENV" == "prod" && "$IN_CI" != "true" ]]; then
  echo "This deploys to PRODUCTION, where real PHI lives."
  read -r -p "Type 'prod' to continue: " confirm
  [[ "$confirm" == "prod" ]] || { echo "Aborted."; exit 1; }
fi

if [[ -n "$(git status --porcelain)" && "$ENV" == "staging" ]]; then
  echo "Warning: uncommitted changes. Images are built from the working tree but tagged ${TAG}."
fi

# ── Resource providers (idempotent) ───────────────────────────────────────────
if [[ "$IN_CI" != "true" ]]; then
say "Registering resource providers"
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL \
          Microsoft.KeyVault Microsoft.ManagedIdentity Microsoft.Network \
          Microsoft.OperationalInsights Microsoft.Insights Microsoft.Storage; do
  az provider register --namespace "$ns" --wait -o none
done
fi

# ── Shared registry ───────────────────────────────────────────────────────────
say "Shared container registry"
[[ "$IN_CI" == "true" ]] || az group create -n "$SHARED_RG" -l "$LOCATION" --tags app=codelyst environment=shared -o none
ACR_NAME="$(az deployment group create -g "$SHARED_RG" -n shared \
  --template-file infra/shared.bicep --query properties.outputs.acrName.value -o tsv)"
ACR_SERVER="$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)"

# ── Images: build in staging, promote to prod ─────────────────────────────────
build_images() {
  say "Building images in Azure (no local Docker needed)"
  az acr build -r "$ACR_NAME" -t "codelyst-api:${TAG}" ./backend  -o none
  az acr build -r "$ACR_NAME" -t "codelyst-web:${TAG}" ./frontend -o none
}

image_exists() {   # image_exists <repo>: is ${TAG} in the registry?
  az acr repository show-tags -n "$ACR_NAME" --repository "$1" -o tsv 2>/dev/null | grep -qx "$TAG"
}

if [[ "$ENV" == "staging" ]]; then
  build_images
elif image_exists codelyst-api && image_exists codelyst-web; then
  say "Promoting tag ${TAG}, already built for staging"
elif [[ "${ALLOW_PROD_BUILD:-0}" == "1" && "$IN_CI" != "true" ]]; then
  echo "ALLOW_PROD_BUILD=1: tag ${TAG} has not run in staging. Building it for prod."
  build_images
else
  echo "Images for ${TAG} not found. Deploy it to staging first, or set IMAGE_TAG." >&2
  echo "(First go-live without staging: ALLOW_PROD_BUILD=1 ./infra/deploy.sh prod)" >&2
  exit 1
fi

# ── Secrets: generated on first deploy only ───────────────────────────────────
[[ "$IN_CI" == "true" ]] || az group create -n "$RG" -l "$LOCATION" --tags app=codelyst environment="$ENV" -o none

PG_PASSWORD=""; JWT=""; JWT_REFRESH=""; ENCRYPTION=""; ANTHROPIC=""
# "First deploy" = no successful deployment yet in this resource group. If a
# first attempt failed partway, secrets are regenerated and rewritten in full.
DEPLOYED="$(az deployment group list -g "$RG" \
  --query "length([?properties.provisioningState=='Succeeded'])" -o tsv)"

if [[ "$DEPLOYED" == "0" && "$IN_CI" == "true" ]]; then
  echo "${ENV} has never been deployed. Run ./infra/deploy.sh ${ENV} by hand once first." >&2
  exit 1
fi

if [[ "$DEPLOYED" == "0" ]]; then
  say "First deploy of ${ENV}: generating database, JWT and encryption secrets"
  PG_PASSWORD="$(openssl rand -hex 24)"
  JWT="$(openssl rand -hex 64)"
  JWT_REFRESH="$(openssl rand -hex 64)"
  # Fernet key: 32 random bytes, url-safe base64. Encrypts MFA secrets at rest.
  ENCRYPTION="$(openssl rand -base64 32 | tr '+/' '-_')"
  ANTHROPIC="${ANTHROPIC_API_KEY:-}"
fi

if [[ "$DEPLOYED" == "0" || "${ROTATE_ANTHROPIC_KEY:-0}" == "1" ]]; then
  if [[ -z "$ANTHROPIC" ]]; then
    [[ "$ENV" == "prod" ]] && echo "Use the key from the Anthropic org covered by your BAA."
    read -r -s -p "Anthropic API key for ${ENV}: " ANTHROPIC; echo
  fi
  [[ "$ANTHROPIC" == sk-ant-* ]] || { echo "That doesn't look like an Anthropic key (sk-ant-...)." >&2; exit 1; }
fi

# ── Deploy the environment ────────────────────────────────────────────────────
say "Deploying ${RG} (first run takes 15-25 minutes, mostly PostgreSQL)"
export ACR_NAME ACR_RG="$SHARED_RG" \
       BACKEND_IMAGE="${ACR_SERVER}/codelyst-api:${TAG}" \
       FRONTEND_IMAGE="${ACR_SERVER}/codelyst-web:${TAG}"

az deployment group create -g "$RG" -n "codelyst-${ENV}-${TAG}" \
  --parameters "infra/env/${ENV}.bicepparam" \
  --parameters postgresAdminPassword="$PG_PASSWORD" anthropicApiKey="$ANTHROPIC" \
               jwtSecretKey="$JWT" jwtRefreshSecretKey="$JWT_REFRESH" \
               encryptionKey="$ENCRYPTION" \
  -o none

unset PG_PASSWORD JWT JWT_REFRESH ENCRYPTION ANTHROPIC

WEB_URL="$(az deployment group show -g "$RG" -n "codelyst-${ENV}-${TAG}" \
  --query properties.outputs.webUrl.value -o tsv)"

say "Done. ${ENV} is live at ${WEB_URL}"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then echo "web_url=${WEB_URL}" >> "$GITHUB_OUTPUT"; fi
echo "API logs: az containerapp logs show -g ${RG} -n ca-codelyst-api-${ENV} --follow"
if [[ "$DEPLOYED" == "0" ]]; then
  echo "Create the first admin (prompts for a password):"
  echo "  az containerapp exec -g ${RG} -n ca-codelyst-api-${ENV} --command \"python -m app.cli create-admin --email you@example.com --name 'Your Name'\""
fi
