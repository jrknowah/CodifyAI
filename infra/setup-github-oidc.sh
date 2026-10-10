#!/usr/bin/env bash
# ─── One-time: let GitHub Actions deploy to Azure without stored passwords ────
#
#   ./infra/setup-github-oidc.sh <github-org>/<repo>
#   e.g. ./infra/setup-github-oidc.sh dreamlogic-solutions/codelyst
#
# Run AFTER the repo is in its final home (the Azure trust is tied to the exact
# repo name) and AFTER `./infra/deploy.sh staging` and `prod` have each been run
# by hand once (so the three resource groups exist).
#
# What it does:
#   1. Creates an Entra app "github-codelyst-deploy" with a service principal.
#   2. Trusts GitHub's OIDC tokens, but only for workflows running on main.
#   3. Grants Owner on the three Codelyst resource groups only (not the
#      subscription). Owner is needed because the templates assign roles.
#   4. Stores the IDs as GitHub repository variables (they are not secrets).
#
# Requires: az (logged in as a subscription Owner), gh (logged in, repo admin).

set -euo pipefail

REPO="${1:?usage: $0 <github-org>/<repo>}"
APP_NAME="github-codelyst-deploy"

SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "▸ Entra app and service principal"
APP_ID="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
fi
az ad sp show --id "$APP_ID" -o none 2>/dev/null || az ad sp create --id "$APP_ID" -o none
SP_OBJECT_ID="$(az ad sp show --id "$APP_ID" --query id -o tsv)"

echo "▸ Trusting GitHub Actions on ${REPO} (main branch only)"
CRED_NAME="github-main"
if ! az ad app federated-credential list --id "$APP_ID" --query "[?name=='${CRED_NAME}']" -o tsv | grep -q .; then
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"${CRED_NAME}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${REPO}:ref:refs/heads/main\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi

echo "▸ Owner on the Codelyst resource groups"
for rg in rg-codelyst-shared rg-codelyst-staging rg-codelyst-prod; do
  az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
    --role Owner --scope "/subscriptions/${SUB_ID}/resourceGroups/${rg}" -o none
done

echo "▸ GitHub repository variables"
gh variable set AZURE_CLIENT_ID       --repo "$REPO" --body "$APP_ID"
gh variable set AZURE_TENANT_ID       --repo "$REPO" --body "$TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUB_ID"

echo "Done. Merges to main now deploy staging; run 'Promote to prod' to ship."
