# BusinessAgent user guide

BusinessAgent is a Telegram-driven multi-agent assistant for property operations. It combines a main bot, worker tasks, long-term memory, and read-only SQL access to help you work with documents, properties, tenancies, conveyancing, and maintenance.

## 1. Getting started

1. Copy `.env.example` to `.env` and fill in the required values.
2. Start the local stack:
   - `docker compose up --build`
3. Register your Telegram bot token and webhook secret in the environment.
4. Open a chat with the bot and send `/help`.

## 2. Core conversation flows

### Ask questions
Use `/ask` for natural-language questions over your stored memories and data.

Examples:
- `/ask show me the latest lease notes for Oak Ave`
- `/ask from=2026-01-01 to=2026-01-31 summarize the documents about the purchase`

The assistant uses date-aware memory retrieval. If the source document has no explicit event date, the system falls back to ingestion time.

### Ingest documents
Send a document to the bot or use `/ingest <path>` in the app environment.

Supported formats include:
- TXT
- PDF
- DOCX
- images for scans when practical

The system parses the document, stores a summary, chunked memory records, and links them back to the source document path.

### Query structured data
Use `/data` to run read-only SQL queries over allowlisted tables.

Example:
- `/data table=properties columns=id,address,status limit=10`

## 3. Property and portfolio workflows

### Properties
- `/property list`
- `/property show <property_id>`
- `/property add`

### Mortgages
- `/mortgage expiring`
- `/mortgage expiring 6`

## 4. Tenancy and agreement workflows

### Tenancies
- `/tenant add <property_id>`
- `/tenant list <property_id>`
- `/tenant show <tenancy_id>`
- `/tenant search <query> [tenancy_id=<id>]`

You can also upload tenant documents through the API or by forwarding a file to the bot with `/tenant doc <tenancy_id>`.

### Agreements
- `/agreement generate <tenancy_id>`
- `/agreement pdf <agreement_id>`

The workflow will ask you to pick a template, fill missing placeholders, and then render a DOCX agreement to disk.

## 5. Conveyancing assistant

### Commands
- `/conveyancing list`
- `/conveyancing show <transaction_id>`
- `/conveyancing new purchase <property_id>`
- `/conveyancing advance <transaction_id> <stage>`
- `/conveyancing doc <transaction_id>`
- `/conveyancing compare mortgages <transaction_id>`
- `/conveyancing chase <transaction_id>`
- `/conveyancing overdue`

## 6. Property maintenance and compliance

### Commands
- `/maintenance list <property_id>`
- `/maintenance show <job_id>`
- `/maintenance new <property_id>`
- `/maintenance advance <job_id> <stage>`
- `/maintenance doc <job_id>`
- `/maintenance compare quotes <job_id>`
- `/maintenance spend <property_id> [year=YYYY]`
- `/compliance list <property_id>`
- `/compliance add <property_id>`
- `/compliance overdue`

## 7. API usage

Most endpoints are token-protected. When `INTERNAL_API_TOKEN` is set, send `X-API-Token` with your requests.

Useful examples:
- `POST /api/properties`
- `POST /api/tenancies`
- `POST /api/tenancies/{tenancy_id}/documents`
- `POST /api/agreements/generate`
- `POST /api/conveyancing`
- `POST /api/maintenance`

## 8. Notes and best practices

- Keep SQL access read-only; the scaffold blocks arbitrary execution.
- Date filters are applied against `effective_date`, which uses the source event date when present and falls back to ingestion time otherwise.
- For shared VPS deployments, keep the app attached to the external `app-network` and use Traefik labels only when the reverse proxy is already present.
