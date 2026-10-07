# CodifyAI v2

AI-powered medical coding for post-acute care — built security-first.  
**DreamLogic Solutions LLC** · Biloxi, MS

---

## Architecture

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React 18 + Vite + Tailwind | Token in memory (not localStorage) |
| Backend | Python 3.11 + FastAPI | Async, versioned API (`/api/v1`) |
| Database | PostgreSQL 16 | Alembic migrations |
| AI Engine | Anthropic Claude (server-side, under BAA) | Note never persisted — keyed hash only |
| Auth | JWT (access + httpOnly refresh cookie) + DB revocation, TOTP MFA | Account lockout after 5 failed attempts |
| Rate Limiting | SlowAPI | 10 login/min, 10 analyze/min, 60 general/min |
| Security | HIPAA-aligned headers, audit log | Append-only AuditLog table |
| Testing | pytest + Vitest + Playwright | Unit, integration, E2E |
| Containers | Docker + Docker Compose | PostgreSQL service included |

---

## Security Features

- **No PHI stored** — clinical notes are reduced to a keyed HMAC-SHA256 before persistence. Only de-identified results are saved (code, type, official description, confidence). The model's per-code reasons and summary can quote the note, so they are shown to the coder but never stored.
- **Immutable audit log** — logins (successful and failed), lockouts, logouts, analyses, history views, admin actions, MFA changes and audit-log views are recorded with user, IP, user agent and timestamp. Audit rows are committed even when the request fails, and a database trigger rejects `UPDATE`, `DELETE` and `TRUNCATE` on `audit_logs`.
- **Admin-provisioned accounts** — no public sign-up. Admins create, disable and unlock users, change roles, reset MFA and sign users out (`/admin`). Roles: `admin`, `coder` (can analyze), `viewer` (read-only).
- **MFA** — TOTP (authenticator app). Secrets are Fernet-encrypted at rest; codes can't be replayed. `REQUIRE_MFA=true` forces every user to enroll before using the app.
- **Account lockout** — 5 failed passwords or MFA codes lock the account for 15 minutes. Every login failure returns the same message, so responses don't reveal which accounts exist.
- **Revocable sessions** — every JWT has a unique ID kept in a database denylist on logout, and a per-user version that is bumped on password change, role change, deactivation or MFA reset (signing out all of that user's sessions).
- **Refresh token in an httpOnly cookie** — `SameSite=Strict`, scoped to `/api/v1/auth`, rotated on every use. Reusing an old refresh token (a sign it was stolen) signs out every session. Access tokens live 15 minutes, in memory only. Sessions end after 12 hours regardless of activity.
- **Automatic logoff** — the UI signs out after 15 minutes of inactivity (`VITE_IDLE_TIMEOUT_MINUTES`).
- **Security headers** on every response: `X-Frame-Options: DENY`, `Cache-Control: no-store`, CSP, HSTS (production), from both FastAPI and nginx.
- **Proxy-aware** — `X-Forwarded-For` / `X-Forwarded-Proto` are only trusted from `TRUSTED_PROXIES`, so audit-log IPs and rate limits can't be spoofed.
- **Rate limiting** — 10 logins/min and 10 analyses/min per IP; 60/min default on everything else.
- **Safe production config** — with `APP_ENV=production` the app refuses to start unless HTTPS is enforced, the database connection uses TLS and CORS has no localhost origins. API docs are disabled.
- **Password policy** — 12+ chars (≤72 bytes), uppercase, number and special character, enforced at both frontend and backend.

---

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo>
cd codifyai_v2

cp backend/.env.example backend/.env
```

Edit `backend/.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Generate with:
# python -c "import secrets; print(secrets.token_hex(64))"
SECRET_KEY=your-64-char-hex
REFRESH_SECRET_KEY=your-other-64-char-hex

# Generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your-fernet-key
```

### 2. Start with Docker Compose

```bash
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (dev only) | http://localhost:8000/docs |

### 3. Database migrations

The backend container runs `alembic upgrade head` on start. To run them by hand:

```bash
cd backend
alembic upgrade head
```

> **Upgrading a database created by an older version** (tables made by the old
> startup `create_all`, no `alembic_version` table): mark it as the baseline first,
> then upgrade. The upgrade permanently deletes the stored AI summaries and
> per-code reasons, because they can contain PHI.
> ```bash
> alembic stamp 0001_baseline
> alembic upgrade head
> ```

### 4. Create the first administrator

There is no public registration. Create the first admin from the server shell
(the password is prompted for, not passed as an argument):

```bash
cd backend
python -m app.cli create-admin --email you@facility.com --name "Your Name"
```

Then sign in and add everyone else on the **Admin** page.

---

## Running Without Docker

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

---

## Testing

### Backend — Unit + Integration

```bash
cd backend

# Run all tests with coverage
pytest

# Unit tests only
pytest app/tests/unit/

# Integration tests only (requires TEST_DATABASE_URL)
pytest app/tests/integration/

# Coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

> Integration tests require a running PostgreSQL instance.  
> Set `TEST_DATABASE_URL` in `.env` or environment.

Dependency audit:

```bash
pip-audit -r requirements.txt
```

### Frontend — Component Tests (Vitest)

```bash
cd frontend

# Run all component tests
npm run test

# Watch mode
npm run test -- --watch

# Coverage
npm run test -- --coverage
```

### Frontend — E2E Tests (Playwright)

```bash
cd frontend

# Install browsers (first time)
npx playwright install chromium

# E2E runs against a pre-provisioned coder account without MFA (create it on
# /admin). Login is rate limited to 10/min, so start the backend with
# RATE_LIMIT_ENABLED=false for the suite.
export E2E_EMAIL=coder@codifyai.com E2E_PASSWORD='CoderPass123!'

# Run E2E tests (requires backend + frontend running)
npx playwright test

# With UI
npx playwright test --ui

# View last report
npx playwright show-report
```

---

## Project Structure

```
codifyai_v2/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── deps.py          # Auth dependencies
│   │   │   └── endpoints/
│   │   │       ├── admin.py     # User management, audit log review
│   │   │       ├── auth.py      # Login, MFA, logout, refresh
│   │   │       └── coding.py    # Analyze, history
│   │   ├── core/
│   │   │   ├── config.py        # Settings with validation
│   │   │   ├── net.py           # Trusted-proxy client IP
│   │   │   ├── rate_limit.py    # Shared rate limiter
│   │   │   └── security.py      # JWT, hashing, TOTP, encryption
│   │   ├── db/
│   │   │   └── session.py       # Async SQLAlchemy engine
│   │   ├── middleware/
│   │   │   └── security.py      # Headers, HTTPS, logging
│   │   ├── models/
│   │   │   └── models.py        # User, Facility, Encounter, AuditLog
│   │   ├── schemas/
│   │   │   └── schemas.py       # Pydantic v2 with strict validation
│   │   ├── services/
│   │   │   ├── audit_service.py # Append-only audit log writes
│   │   │   ├── coding_service.py# Claude AI + note hashing
│   │   │   ├── token_service.py # Token revocation, refresh cookie
│   │   │   └── user_service.py  # Auth, lockout, password
│   │   ├── tests/
│   │   │   ├── conftest.py      # Fixtures, isolated test DB
│   │   │   ├── unit/            # Security, validation tests
│   │   │   └── integration/     # Auth, MFA, admin, coding endpoint tests
│   │   ├── cli.py               # create-admin bootstrap
│   │   └── main.py              # App, middleware, routers
│   ├── alembic/                 # DB migrations
│   ├── requirements.txt
│   ├── pytest.ini
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/          # Sidebar, ProtectedRoute
│   │   │   └── ui/              # Card, Input, Button, Alert, Spinner
│   │   ├── hooks/
│   │   │   └── useAuth.jsx      # Auth context, in-memory token, idle logoff
│   │   ├── pages/               # Login, Dashboard, History, Settings, Admin
│   │   ├── services/
│   │   │   └── api.js           # Axios + auto-refresh interceptor
│   │   └── tests/
│   │       ├── unit/            # Vitest component tests
│   │       └── e2e/             # Playwright auth + coding flows
│   ├── playwright.config.js
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Azure Deployment

1. **Azure Database for PostgreSQL** — Flexible Server with encryption at rest (default) and `require_secure_transport=on`; set `DATABASE_URL` in App Service config; enable automated backups and point-in-time restore
2. **Azure App Service (Linux, Python 3.11)** — deploy backend; store `SECRET_KEY`, `REFRESH_SECRET_KEY`, `ENCRYPTION_KEY` and `ANTHROPIC_API_KEY` in **Azure Key Vault**
3. **Azure Static Web App** — deploy `frontend/dist`; set API proxy to App Service URL (same origin, so the refresh cookie works)
4. **App Service Config** — set `APP_ENV=production`, `ENFORCE_HTTPS=true`, `DATABASE_SSL=true`, `REQUIRE_MFA=true`, `ALLOWED_ORIGINS=https://your-domain`, and `TRUSTED_PROXIES` to the front-end proxy range
5. **Multiple workers** — set `RATE_LIMIT_STORAGE_URI=redis://...` (Azure Cache for Redis) so rate limits are shared

### HIPAA items outside the code

The code covers the technical safeguards it can. These also need to be in place before handling real PHI:

- [x] BAA with Anthropic (zero data retention)
- [ ] BAA with Microsoft Azure (covers Postgres, App Service, Key Vault, Redis)
- [ ] Audit log retention of at least 6 years: keep `audit_logs` in backups or export to immutable storage (for example, Azure Storage with an immutability policy)
- [ ] Ship application logs to a monitored sink (Azure Monitor / Log Analytics) with alerting on `account_locked` and `refresh_token_reuse`
- [ ] Restrict the production database role: the app role shouldn't own `audit_logs` or be able to drop triggers
- [ ] Written risk analysis, security policies, workforce training and a breach-notification procedure
- [ ] Periodic access review of user accounts (Admin page) and audit log review

---

## Roadmap

- [ ] Facility management in the admin panel (users can already be assigned a facility via the API)
- [ ] PointClickCare EHR integration
- [ ] Fine-tuned post-acute coding model (Phase II SBIR)
- [ ] Azure Health Data Services FHIR integration
- [ ] Export to CSV / billing system format
- [ ] Email-based password reset / invite flow
