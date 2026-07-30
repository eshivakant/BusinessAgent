# BusinessAgent Scaffold

Production-ready scaffold for a Dockerized multi-agent business assistant with:

- Telegram-facing main agent (webhook mode)
- Orchestrator + worker/subagent task queue
- Qdrant-backed long-term memory
- Document ingestion (`txt`, `pdf`, `docx`) with summary + chunk storage
- Read-only SQL data access layer (parameterized, SELECT-only, allowlisted tables)
- Date-aware memory retrieval (`from` / `to` filtering)
- Lightweight conversational continuity for Telegram (rolling summary + short recent-turn window)
- Tenancy CRUD, tenant document ingestion, semantic tenant search, and agreement generation workflows

## Architecture

```text
Telegram -> FastAPI app (main agent) -> Orchestrator
                                       |-> Qdrant memory (query / retrieval)
                                       |-> Redis queue -> Worker subagent(s) -> Ingestion pipeline -> Qdrant
                                       |-> ReadOnly SQL access layer (allowlisted SELECTs only)
```

### Key behavior for date filtering

Each memory payload stores:

- `event_date` (optional)
- `ingested_at` (always present)
- `effective_date` (always present: `event_date` at 00:00 UTC, otherwise `ingested_at`)
- `source_type`
- `source_uri`
- `archived_file_path` (path to original document on disk, if archival enabled)

Date filters are applied against `effective_date`.  
This makes behavior explicit when source documents do not include a natural event date.

### Application persistence

Property and document registries can now use a dedicated application database via `APP_DATABASE_URL`.

- **Purpose:** persist property, mortgage, tenant, maintenance, contact, and document metadata
- **Recommended deployment:** a separate PostgreSQL database for BusinessAgent on the shared Docker network
- **Fallback:** if `APP_DATABASE_URL` is unset, the scaffold falls back to in-memory registries
- **Bootstrap:** run `docker compose --profile bootstrap up db-init` to create the database/schema when `APP_DATABASE_ADMIN_URL` is configured

### Document archival

When documents are ingested, original files are automatically archived to disk (if `INGESTION_ARCHIVE_ENABLED=true`):

- **Storage:** `${INGESTION_ARCHIVE_DIR}/{document_id}/original.{ext}` (organized by ingestion timestamp)
- **Metadata:** Each memory record links to archived path via `archived_file_path` payload field
- **Non-critical:** If archival fails (permission, storage, network), ingestion continues; archival is logged but does not block

This allows audit trails and re-processing of source documents without re-fetching or re-uploading.

### Telegram conversation continuity (bounded context)

For each chat, the orchestrator maintains:

- short-term recent messages in Redis (`CONVERSATION_WINDOW_MESSAGES`)
- a rolling compact summary (`CONVERSATION_SUMMARY_MAX_CHARS`)

When a user asks follow-up questions, retrieval query context is assembled from:

1. current message
2. rolling summary
3. recent turns

All bounded by `CONVERSATION_CONTEXT_MAX_CHARS`, so large history is not sent every turn.

## Project layout

```text
src/business_agent/
  api/             FastAPI routes (health, webhook, memory/query, ingest, sql/read)
  orchestrator/    Command parsing + routing for ask/ingest/data
  worker/          Redis/RQ queue + worker tasks (subagents)
  memory/          Memory models, filter builder, Qdrant store
  ingestion/       Document loader/parser/chunker/summarizer
  data/            ReadOnly SQL access layer
  telegram/        Telegram sendMessage client
```

## Quick start (Docker)

1. Copy env file and set values:

   ```powershell
   Copy-Item .env.example .env
   ```

2. If you do **not** have an external `app-network`, set this in `.env`:

   ```env
   APP_NETWORK_EXTERNAL=false
   ```

   If your VPS already has `app-network`, keep `APP_NETWORK_EXTERNAL=true`.

3. Start the stack:

   ```powershell
   docker compose up --build
   ```

Services started: `app`, `worker`, `qdrant`, `redis`.

### PostgreSQL persistence setup

To persist properties and document metadata in PostgreSQL instead of memory:

1. Set `APP_DATABASE_URL` to a dedicated BusinessAgent database on the shared Docker network.
2. Optionally set `APP_DATABASE_ADMIN_URL` with admin credentials that can create the database and app role.
3. Run the one-off bootstrap job:

   ```powershell
   docker compose --profile bootstrap up db-init
   ```

4. Start the app normally with `docker compose up --build`.

Example:

```env
APP_DATABASE_URL=postgresql+psycopg://business_agent:change-me@postgres:5432/business_agent
APP_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:supersecret@postgres:5432/postgres
```

## Telegram setup

Set these values in `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TRAEFIK_HOST` (or your public host)

After deployment, register webhook:

```powershell
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" `
  -H "Content-Type: application/json" `
  -d "{\"url\":\"https://<PUBLIC_HOST>/telegram/webhook\",\"secret_token\":\"<TELEGRAM_WEBHOOK_SECRET>\"}"
```

Telegram commands:

- `/help`
- `/ask from=2026-01-01 to=2026-01-31 revenue trend`
- `/ingest /data/docs/quarterly-report.pdf event_date=2026-01-15`
- `/data table=orders columns=id,total,created_at filters=status:paid limit=20`
- `/reset` (clear current chat context)

### Cleaner Telegram UX (implemented)

- Inline menu buttons in replies: `Ask question`, `Upload document`, `Query data`, `Reset context`
- Answer action buttons: `Refine`, `Date filter`, `Show sources`, `More details`, `Follow-up`
- Compact answer-first format with up to 3 evidence bullets by default
- Callback actions for showing detailed view/source list without retyping commands
- Actionable error and guidance responses for malformed commands
- `/reset` (clear chat conversation context for current Telegram chat)

## API endpoints

- `GET /health`
- `POST /telegram/webhook`
- `POST /api/memory/query`
- `POST /api/documents/ingest`
- `POST /api/sql/read`
- `POST /api/tenancies`
- `GET /api/tenancies`
- `GET /api/tenancies/{tenancy_id}`
- `PATCH /api/tenancies/{tenancy_id}`
- `POST /api/tenancies/{tenancy_id}/documents`
- `GET /api/tenancies/{tenancy_id}/documents`
- `POST /api/agreements/generate`

If `INTERNAL_API_TOKEN` is set, send `X-API-Token` for `/api/*` endpoints.

Example memory query:

```powershell
curl -X POST "http://localhost:8080/api/memory/query" `
  -H "Content-Type: application/json" `
  -H "X-API-Token: <INTERNAL_API_TOKEN>" `
  -d "{\"query\":\"pipeline risk\",\"date_from\":\"2026-01-01\",\"date_to\":\"2026-01-31\",\"top_k\":5}"
```

## SQL safety model

Read-only SQL access is intentionally constrained:

- No arbitrary SQL text execution
- Only generated `SELECT` statements
- Parameterized filters only
- Table name must be in `SQL_ALLOWED_TABLES`
- Identifier validation blocks unsafe table/column names

Use a dedicated DB principal with read-only privileges.

## VPS / Traefik integration notes

`docker-compose.yml` is prepared for your existing stack:

- Joins external Docker network: `app-network` (configurable by `EXTERNAL_DOCKER_NETWORK`)
- Traefik labels included for `websecure` + `letsencrypt`
- Traefik routing controlled by `TRAEFIK_ENABLE=true|false`

## GitHub Actions deployment (VPS)

Workflow file: `.github/workflows/deploy.yml`

Behavior:

1. Runs unit tests in GitHub Actions.
2. If tests pass, deploys to your VPS over SSH.
3. On VPS, ensures external Docker network exists, updates code, and runs:
   `docker compose up -d --build --remove-orphans`

Required repository secrets:

- `VPS_HOST` (server IP/domain)
- `VPS_USER` (SSH user)
- `VPS_SSH_KEY` (private key contents)
- `VPS_PORT` (SSH port, usually `22`)
- `VPS_DEPLOY_PATH` (absolute path of this repo on VPS, e.g. `/opt/business-agent`)
- `EXTERNAL_DOCKER_NETWORK` (optional, defaults to `app-network`)

Important:

- Keep copying `.env` manually to `${VPS_DEPLOY_PATH}/.env` as you planned.
- Deployment fails early if `.env` is missing on the VPS.

## End-to-end testing strategy

BusinessAgent now ships with two test tiers:

- Unit tests: fast, deterministic checks for modules and helpers.
- Fast E2E tests: in-process FastAPI app plus deterministic fakes for Telegram, memory, queueing, SQL access, and property state. These are the default CI path.
- Stack E2E: optional docker-compose-backed smoke coverage for postgres/redis/qdrant. Run it explicitly with `BUSINESS_AGENT_RUN_STACK_E2E=1`.

Commands:

```powershell
python -m pip install -r requirements-dev.lock
python -m pytest -q -m "not e2e_stack"
```

Optional stack run:

```powershell
$env:BUSINESS_AGENT_RUN_STACK_E2E = "1"
python -m pytest -q -m "e2e_stack"
```

## Local testing

Install dependencies and run tests:

```powershell
python -m pip install -e .[dev]
python -m pytest
python -m pytest -m e2e
```

Tenancy-specific coverage is included in `tests/test_tenancy_features.py` for unit and fast E2E flows.

## Configuration reference

Key environment variables (see `.env.example` for all options):

**Telegram:**
- `TELEGRAM_BOT_TOKEN` (required) – Bot token from BotFather
- `TELEGRAM_WEBHOOK_SECRET` (optional) – Secret for webhook signature validation

**Memory & retrieval:**
- `QDRANT_URL` (default: `http://qdrant:6333`)
- `QDRANT_COLLECTION` (default: `business_agent_memory`)
- `CONVERSATION_ENABLED` (default: `true`)
- `CONVERSATION_WINDOW_MESSAGES` (default: `8`) – Recent turns to keep in chat context

**Document ingestion:**
- `INGESTION_ALLOWED_LOCAL_DIR` (default: `/data/docs`) – Base directory for local file uploads
- `INGESTION_ARCHIVE_DIR` (default: `/data/archive`) – Where to archive original documents
- `INGESTION_ARCHIVE_ENABLED` (default: `true`) – Enable original document archival
- `INGESTION_CHUNK_SIZE` (default: `1200`) – Characters per chunk
- `INGESTION_CHUNK_OVERLAP` (default: `200`) – Overlap between chunks
- `INGESTION_MAX_DOCUMENT_CHARS` (default: `200000`) – Max document size to ingest

**SQL (optional, read-only only):**
- `SQL_DATABASE_URL` – Connection string (e.g., `postgresql://user:pass@host/dbname`)
- `SQL_ALLOWED_TABLES` – Comma-separated list of safe tables
- `SQL_QUERY_LIMIT_DEFAULT` (default: `100`)
- `SQL_QUERY_LIMIT_MAX` (default: `1000`)
