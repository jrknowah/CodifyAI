# Production go-live runbook

First production deploy of Codelyst for Urgent Care at The Pointe. Target: live
Saturday Oct 10, 2026, 8 pm CT. Every step is run by hand from a laptop; GitHub
Actions takes over only after step 7.

Prod holds real PHI. Staging is skipped for this first deploy and stood up next
week (`./infra/deploy.sh staging`).

## 0. Blockers (stop if any is not done)

- [ ] GitHub repo is **private**: Settings → General → Danger zone → Change visibility.
- [ ] Anthropic BAA covers the API organization whose key you will paste in step 3.
- [ ] Microsoft BAA is accepted for the subscription (it is part of the Microsoft
      Product Terms; confirm in the Service Trust Portal). Every service in
      `main.bicep` is on Microsoft's HIPAA in-scope list; confirm before go-live.
- [ ] Your Azure account is Owner on the subscription (the templates create role assignments).

## 1. Tools (5 min)

```bash
az version            # 2.60 or newer
az bicep install      # or: az bicep upgrade
az login
az account set --subscription "<subscription name or id>"
```

## 2. Get the code (2 min)

```bash
git clone https://github.com/jrknowah/codifyai && cd codifyai
git checkout infra/prod-go-live    # or main, once this branch is merged
```

## 3. Deploy prod (25–35 min, mostly PostgreSQL)

```bash
ALLOW_PROD_BUILD=1 ./infra/deploy.sh prod
```

It asks you to type `prod`, then for the Anthropic API key (input hidden). It
builds both images in Azure, generates the database password, JWT keys and the
MFA encryption key straight into Key Vault (you never see them), and prints the
app URL at the end.

`ALLOW_PROD_BUILD=1` is only for this first deploy, because staging does not
exist yet. Never use it again once staging is up.

## 4. Smoke test (5 min)

```bash
./infra/smoke-test.sh https://ca-codelyst-web-prod.<...>.azurecontainerapps.io
```

Both lines must say `ok`. Then open the URL: you should get the login page over HTTPS.

## 5. First admin and coder accounts (10 min)

```bash
az containerapp exec -g rg-codelyst-prod -n ca-codelyst-api-prod \
  --command "python -m app.cli create-admin --email you@example.com --name 'JR Cunningham'"
```

Sign in, enroll MFA (required in prod), then create The Pointe coder from the
Admin page. The coder enrolls MFA on first sign-in.

## 6. Go / no-go (15 min)

- [ ] Login page loads over HTTPS; plain `http://` redirects
- [ ] Run one **synthetic** note through Analyze; suggestions come back
- [ ] Log Analytics → `ContainerAppConsoleLogs_CL`: request lines show paths only, no note text
- [ ] Admin → Audit log shows the login and the analyze
- [ ] Postgres → Backups shows automatic backups on (35-day retention, geo-redundant)

All ticked → run the first real claim with the coder, with you watching.
Any unticked → no-go; The Pointe stays on its current setup and you retry Sunday.

## 7. After go-live (next week)

```bash
./infra/deploy.sh staging                                  # stand up staging
./infra/setup-github-oidc.sh jrknowah/codifyai             # or the company org after the transfer
```

After that, merges to main deploy staging automatically, and **Actions → Promote
to prod** ships a tested image to prod (it is also the rollback: enter an older SHA).
Run the OIDC script again after the repo moves to the company org, because the
Azure trust is tied to the exact repo name.

## If something breaks

| Symptom | Look at |
| --- | --- |
| Deploy fails on a role assignment | Your account lacks Owner on the subscription |
| API container restarting | `az containerapp logs show -g rg-codelyst-prod -n ca-codelyst-api-prod --follow`. A startup line `Unsafe production configuration` names the setting |
| Web loads, API calls fail | `/healthz` in the smoke test; the web app reaches the API over the internal FQDN |
| Need to roll back | `az containerapp revision list -g rg-codelyst-prod -n ca-codelyst-api-prod`, then `az containerapp revision activate` on the previous one |

## What this deploy includes

- Private PostgreSQL 16 (no public endpoint, TLS required, 35-day geo-redundant backups)
- Key Vault behind a private endpoint holding every secret; apps read it by managed identity
- API with internal-only ingress; the web container is the only thing on the internet
- MFA required for every user; CPT codes stay off until the AMA license is signed
- Failing SQL statements are kept out of the Postgres logs (they can contain clinical text)
- Append-only audit log (database trigger blocks UPDATE, DELETE and TRUNCATE)

Rough cost while idle: about $100–150 a month (PostgreSQL, one always-warm API
and web replica, registry, Key Vault private endpoint, Log Analytics).

## Not in this deploy (scheduled)

| Item | Window |
| --- | --- |
| Staging environment + GitHub Actions OIDC | Oct 12–14 |
| Azure Language PHI masking + token vault | Oct 12–22 |
| Hash-chained audit log + nightly verification | Oct 15–24 |
| Custom domain (e.g. app.codelyst.com) | After the domain is secured |
| LOI facility onboarding | After one clean week at The Pointe |
