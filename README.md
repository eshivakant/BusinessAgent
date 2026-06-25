# BusinessAgent Scaffold

Production-ready scaffold for a Dockerized multi-agent business assistant with:

- Telegram-facing main agent (webhook mode)
- Orchestrator + worker/subagent task queue
- Qdrant-backed long-term memory
- Document ingestion (`txt`, `pdf`, `docx`) with summary + chunk storage
- Read-only SQL data access layer (parameterized, SELECT-only, allowlisted tables)
- Date-aware memory retrieval (`from` / `to` filtering)
- Lightweight conversational continuity for Telegram (rolling summary + short recent-turn window)

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

Date filters are applied against `effective_date`.  
This makes behavior explicit when source documents do not include a natural event date.

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

## Local testing

Install dependencies and run tests:

```powershell
python -m pip install -r requirements-dev.lock
python -m pytest
```
