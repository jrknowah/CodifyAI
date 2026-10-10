# Codelyst — Azure infrastructure

Two environments, each in its own resource group, built from the same template:

| | Staging | Prod |
|---|---|---|
| Resource group | `rg-codelyst-staging` | `rg-codelyst-prod` |
| Data | **Synthetic only — never real PHI** | Real PHI (pilot facilities) |
| PostgreSQL | B1ms, 7-day backups | B2s, 35-day geo-redundant backups |
| Apps | Scale to zero when idle | Always one replica warm |
| Logs kept | 30 days | 365 days |
| Rough cost | ~$30/mo | ~$110–130/mo |

Plus `rg-codelyst-shared` with one container registry (~$20/mo). Images are built once
for staging, and the same tagged image is promoted to prod.

```
Internet ──TLS──▶ web (nginx, public)  ──TLS /api──▶  api (FastAPI, internal only)
                                                        │              │
                                              private endpoint   VNet-injected
                                                        ▼              ▼
                                                    Key Vault     PostgreSQL 16
```

The database and Key Vault have no public endpoints. Secrets live only in Key Vault and
reach the API through its managed identity. All resources are HIPAA-eligible services
covered by the Microsoft BAA.

**First production go-live: follow [GO-LIVE.md](GO-LIVE.md).**

## One-time setup

1. Install the Azure CLI and Bicep: `az bicep install`
2. `az login`, then `az account set --subscription <DreamLogic subscription>`
3. Your account needs **Owner** on the subscription (the templates create role assignments).
4. Turn on Defender for Cloud for the services used (billed per resource):
   ```bash
   az security pricing create -n Containers --tier standard
   az security pricing create -n KeyVaults --tier standard
   az security pricing create -n OpenSourceRelationalDatabases --tier standard
   ```

## Deploy

```bash
./infra/deploy.sh staging    # builds images from the current commit, deploys staging
./infra/deploy.sh prod       # promotes the same commit's images to prod
```

The first run of each environment generates the database password and JWT secrets,
asks for an Anthropic API key, and takes 15–25 minutes. **For prod, use the key from the
Anthropic organization covered by your BAA.** Staging gets its own separate key.

Later runs keep existing secrets. To replace the Anthropic key:
`ROTATE_ANTHROPIC_KEY=1 ./infra/deploy.sh prod`

If the first deploy fails on a Key Vault secret reference, the role assignment had not
propagated yet. Wait two minutes and run it again.

## Pipeline (GitHub Actions)

| Workflow | Runs when | Does |
|---|---|---|
| `CI` | every pull request | backend tests, frontend lint + build, dependency/secret scan |
| `Deploy to staging` | every merge to `main` | CI, then build images once, deploy staging, smoke test |
| `Promote to prod` | you click **Run workflow** | deploy the same images to prod, smoke test |

Running **Promote to prod** is the approval step, and the run log records who approved
which commit and when. To roll back, run it again with an older commit SHA.

GitHub signs in to Azure with OIDC (short-lived tokens, nothing stored). One-time setup,
after the repo is in its company org and each environment has been deployed by hand once:

```bash
./infra/setup-github-oidc.sh <org>/codelyst
```

The pipeline never does a first deploy: those generate secrets and prompt for the
Anthropic key, so they stay manual.

## Facility file drops (SFTP)

Off by default because SFTP is billed hourly (~$220/mo) while enabled. When the first
facility is ready to send exports, set `enableSftpStorage = true` and their office IPs in
`sftpAllowedIps` in `env/prod.bicepparam`, redeploy, then create an SSH-key local user
per facility in the storage account.

## Not in this pass (on the checklist)

- **Front Door + WAF.** Front Door Premium (needed for private origins and managed WAF
  rules) adds ~$330/mo. Ingress is TLS-only today; add it before scaling past the pilots.
- **Custom domain** (for example `app.codelyst.com`) with a managed certificate.
- **Alerts** on 5xx errors, failed logins, and audit-table writes.
- **Database migrations.** The app creates tables at startup (`create_all`) and
  `backend/alembic/versions/` is empty. Generate an initial Alembic migration before prod
  holds data you care about, so schema changes don't require manual SQL.
- **Least-privilege database role.** The app connects as the server admin. Create an
  app role without UPDATE/DELETE on `audit_logs` as part of hardening.

## Tearing down staging

`az group delete -n rg-codelyst-staging`. Key Vault names are reused on rebuild, so purge
the soft-deleted vault first: `az keyvault purge -n <vault name>`. Prod has purge
protection on and cannot be purged.
