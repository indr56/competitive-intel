# Competitive Moves Intelligence

Track competitor website changes, classify them with AI, and generate actionable insights.

## Architecture

```
Frontend (Next.js) → API (FastAPI) → PostgreSQL
                         ↓
                    Celery Workers → Playwright (capture)
                         ↓              ↓
                    Redis (queue)    S3/R2 (screenshots)
                         ↓
                    LLM (OpenAI / Anthropic) → classify + insights
```

## Project Structure

```
competitive-intel/
├── backend/
│   ├── app/
│   │   ├── api/                # FastAPI route modules
│   │   │   ├── workspaces.py
│   │   │   ├── competitors.py
│   │   │   ├── pages.py
│   │   │   ├── snapshots.py
│   │   │   ├── changes.py
│   │   │   └── digests.py
│   │   ├── core/               # Config, DB, storage, LLM client
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── storage.py
│   │   │   └── llm_client.py
│   │   ├── models/             # SQLAlchemy models
│   │   │   └── models.py
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   │   └── schemas.py
│   │   ├── services/           # Business logic
│   │   │   ├── capture.py      # Playwright page capture
│   │   │   ├── differ.py       # Text diff engine
│   │   │   ├── noise_filter.py # Suppress cookie banners, timestamps, etc.
│   │   │   ├── classifier.py   # Rule-based + LLM classification
│   │   │   ├── digest.py       # Weekly digest builder
│   │   │   └── email.py        # Resend email service
│   │   ├── tasks/              # Celery tasks
│   │   │   ├── celery_app.py   # Celery config + beat schedule
│   │   │   ├── capture_tasks.py
│   │   │   ├── pipeline_tasks.py
│   │   │   └── digest_tasks.py
│   │   └── main.py             # FastAPI app entrypoint
│   ├── alembic/                # DB migrations
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        # Dashboard
│   │   │   ├── globals.css
│   │   │   ├── competitors/page.tsx
│   │   │   ├── changes/page.tsx
│   │   │   └── digests/page.tsx
│   │   └── lib/
│   │       └── api.ts          # Typed API client
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Pipeline Flow

```
Celery Beat (hourly)
  → check_due_pages()
    → for each due page:
      1. capture(url)         → Playwright screenshot + text extraction
      2. if text_hash == prev → STOP (no change)
      3. diff(prev, new)      → unified diff + noise suppression
      4. if not meaningful     → STOP (below threshold)
      5. classify(diff)       → rule-based categories + LLM insights
      6. store change_event

Celery Beat (weekly Monday 9am UTC)
  → send_all_weekly_digests()
    → for each workspace:
      → aggregate change_events → build email HTML → send via Resend
```

## Quick Start

### Option A: Docker Compose (recommended)

```bash
# 1. Clone and configure
cd competitive-intel
cp .env.example .env
# Edit .env with your API keys (at minimum: OPENAI_API_KEY or ANTHROPIC_API_KEY)

# 2. Start everything
docker compose up --build

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. Install Playwright browsers (inside container)
docker compose exec celery-worker playwright install chromium
```

- **API**: http://localhost:8000
- **Swagger docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000

### Option B: Local Development

#### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 16
- Redis 7

#### Backend

```bash
cd backend

# Create virtualenv
python -m venv .venv
source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Set env vars
cp ../.env.example ../.env
# Edit ../.env

# Run migrations
export DATABASE_URL=postgresql://compintel:compintel@localhost:5432/compintel
alembic upgrade head

# Start API
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Start Celery beat (separate terminal)
celery -A app.tasks.celery_app beat --loglevel=info
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Key Design Decisions

- **Multi-tenant**: Account → Workspace → Competitor → TrackedPage hierarchy
- **LLM-agnostic**: `LLMClient` interface with OpenAI/Anthropic backends, swappable via `LLM_PROVIDER` env var
- **LLM gating**: LLM is only called when `text_hash` changes AND diff passes the meaningful threshold
- **Vanilla Playwright**: No stealth plugins; throttling + retries built in
- **Rule-first classification**: Keyword rules run before LLM to reduce cost; LLM adds rich insights
- **Noise suppression**: Regex-based filters for dates, timestamps, copyright, cookie banners, vanity metrics

## API Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workspaces` | Create workspace |
| GET | `/api/workspaces` | List workspaces |
| POST | `/api/workspaces/{wid}/competitors` | Add competitor |
| GET | `/api/workspaces/{wid}/competitors` | List competitors |
| PATCH | `/api/competitors/{id}` | Update competitor |
| DELETE | `/api/competitors/{id}` | Remove competitor |
| POST | `/api/competitors/{cid}/pages` | Add tracked page |
| GET | `/api/competitors/{cid}/pages` | List tracked pages |
| POST | `/api/pages/{id}/capture-now` | Manual capture trigger |
| GET | `/api/pages/{id}/snapshots` | List snapshots |
| GET | `/api/changes` | List all changes (filterable) |
| GET | `/api/changes/{id}` | Change detail with AI insights |
| GET | `/api/workspaces/{wid}/digests` | List digests |
| POST | `/api/digests/{id}/resend` | Resend digest email |
| GET | `/api/digest-view/{token}` | Public digest web view |

## Environment Variables

See `.env.example` for the full list. Critical ones:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `LLM_PROVIDER` | Yes | `openai` or `anthropic` |
| `OPENAI_API_KEY` | If using OpenAI | API key |
| `ANTHROPIC_API_KEY` | If using Anthropic | API key |
| `LLM_MODEL` | No | Model name (default: `gpt-4o`) |
| `S3_ENDPOINT_URL` | No | R2/S3 endpoint for screenshots |
| `RESEND_API_KEY` | No | Email sending (skipped if empty) |
