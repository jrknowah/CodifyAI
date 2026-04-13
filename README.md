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
| AI Engine | Anthropic Claude (server-side) | Note never persisted — hash only |
| Auth | JWT (access + refresh) + blacklist | Account lockout after 5 failed attempts |
| Rate Limiting | SlowAPI | 10 analyze/min, 30 general/min |
| Security | HIPAA-aligned headers, audit log | Append-only AuditLog table |
| Testing | pytest + Vitest + Playwright | Unit, integration, E2E |
| Containers | Docker + Docker Compose | PostgreSQL service included |

---

## Security Features

- **No PHI stored** — clinical notes are hashed (SHA-256) before persistence. Raw note text never touches the database.
- **Immutable audit log** — every login, logout, and analyze action is logged with user ID, IP address, user agent, and timestamp.
- **Account lockout** — 5 failed login attempts locks the account for 15 minutes.
- **Token blacklist** — logout invalidates the JWT immediately (hash stored, not the token).
- **Refresh tokens** in `sessionStorage` (cleared on tab close). Access tokens in memory only.
- **Security headers** on every response: `X-Frame-Options: DENY`, `Cache-Control: no-store`, CSP, HSTS (production).
- **API docs disabled in production** — Swagger/ReDoc not exposed.
- **Password policy** — 12+ chars, uppercase, number, special character enforced at both frontend and backend.
- **User enumeration prevention** — login always returns the same error regardless of whether email exists.

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

### 3. Run database migrations

```bash
cd backend
alembic upgrade head
```

---

## Running Without Docker

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
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
│   │   │       ├── auth.py      # Login, logout, register, refresh
│   │   │       └── coding.py    # Analyze, history
│   │   ├── core/
│   │   │   ├── config.py        # Settings with validation
│   │   │   └── security.py      # JWT, hashing, blacklist
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
│   │   │   └── user_service.py  # Auth, lockout, password
│   │   ├── tests/
│   │   │   ├── conftest.py      # Fixtures, isolated test DB
│   │   │   ├── unit/            # Security, validation tests
│   │   │   └── integration/     # Auth endpoint tests
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
│   │   │   └── useAuth.jsx      # Auth context + in-memory token
│   │   ├── pages/               # Login, Register, Dashboard, History, Settings
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

1. **Azure Database for PostgreSQL** — Flexible Server, set `DATABASE_URL` in App Service config
2. **Azure App Service (Linux, Python 3.11)** — deploy backend; store secrets in **Azure Key Vault**
3. **Azure Static Web App** — deploy `frontend/dist`; set API proxy to App Service URL
4. **App Service Config** — set `ENFORCE_HTTPS=true`, `APP_ENV=production`

---

## Roadmap

- [ ] Redis token blacklist (replace in-memory)
- [ ] Multi-facility admin panel
- [ ] PointClickCare EHR integration
- [ ] Fine-tuned post-acute coding model (Phase II SBIR)
- [ ] Azure Health Data Services FHIR integration
- [ ] Export to CSV / billing system format
- [ ] Email verification flow
