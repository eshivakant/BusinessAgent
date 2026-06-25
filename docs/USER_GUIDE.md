# BusinessAgent User Guide

*A buy-to-let property management assistant you talk to via Telegram*

---

## Table of Contents

- [What BusinessAgent Does](#what-businessagent-does)
- [Getting Started](#getting-started)
- [Commands Reference](#commands-reference)
  - [/help — See All Commands](#help)
  - [/ask — Search Your Knowledge Base](#ask)
  - [/ingest — Add a Document](#ingest)
  - [/list — Browse Your Documents](#list)
  - [/property — Manage Your Properties](#property)
  - [/mortgage — Manage Mortgage Offers](#mortgage)
  - [/data — Query Your Database](#data)
  - [/reset — Clear Context](#reset)
- [Sending Media](#sending-media)
  - [Documents (PDF, DOCX, TXT)](#documents)
  - [Photos & Images](#photos)
  - [Voice Notes](#voice-notes)
  - [Text Messages](#text-messages)
- [Natural Language Questions](#natural-language-questions)
- [Understanding Memory & Retrieval](#understanding-memory-retrieval)
- [Tips for Best Results](#tips-for-best-results)

---

## What BusinessAgent Does

BusinessAgent is your AI-powered assistant for running a buy-to-let property business. You interact with it entirely through Telegram — just like texting a colleague.

It can:

- **Remember everything** — documents, voice notes, messages, data you share
- **Find anything later** — search by keyword, date range, document type, or property
- **Manage properties** — track your portfolio, mortgages, tenancies, and maintenance
- **Compare mortgage offers** — send new offers and ask it to compare against previous ones
- **Answer natural questions** — "When does the EPC expire for 133 Bowland Drive?"
- **Extract information automatically** — send a document and it figures out the type, address, amount, and dates
- **Match transactions to invoices** — "Do we have an invoice for this £180 payment?"
- **Transcribe voice notes** — dictate on the go and it stores the transcript
- **Provide document links** — ask for original copies of anything stored

---

## Getting Started

Your technical team will have set up BusinessAgent on your VPS. Once it's running, you only need:

1. **Open Telegram** on your phone or desktop
2. **Find your bot** — search for the bot username your team provides (e.g., `@YourBusinessAgentBot`)
3. **Start chatting** — send `/help` to see what's available

There's nothing to install on your side. You use Telegram as normal.

> **Tip:** Pin the bot chat to the top of Telegram for quick access.

---

## Commands Reference

All commands start with a forward slash (`/`). You can type them in any case — `/help`, `/Help`, and `/HELP` all work.

### /help

Shows every available command with examples. This is your quick reference card.

```
/help
```

---

### /ask

Search everything you've stored in BusinessAgent — documents, messages, voice notes, data extracts.

**Basic search:**
```
/ask how much was the mortgage valuation for Bowland Drive
```

**With date range:**
```
/ask from=2026-01-01 to=2026-06-30 rental income summary
```

**Date-only (everything from a given date):**
```
/ask from=2026-01-01 solicitor correspondence
```

**Date-only (everything up to a given date):**
```
/ask to=2025-12-31 completion statements
```

The agent returns the most relevant results with source references so you know where the information came from.

---

### /ingest

Manually add a document to your knowledge base by providing a file path or URL.

```
/ingest /data/docs/invoice-12345.pdf
```

With an event date:
```
/ingest /data/docs/epc-certificate.pdf event_date=2026-06-15
```

The system automatically:
- Extracts text from the document
- Uses AI to identify document type, property address, amounts, and dates
- Chunks and stores the content for future retrieval
- Archives the original file for reference

---

### /list

Browse documents you've ingested, with optional filters.

**Everything:**
```
/list
```

**By document type:**
```
/list type=invoice
/list type=tenancy_agreement
/list type=completion
```

**By vendor/source:**
```
/list vendor=Jones_Solicitors
```

**By date range:**
```
/list date_from=2026-01-01 date_to=2026-06-30
```

**Combined filters:**
```
/list type=mortgage_offer vendor=HSBC date_from=2026-01-01 limit=10
```

---

### /property

Manage your property portfolio.

**List all properties:**
```
/property list
```

**Filter by status:**
```
/property list status=owned
/property list status=under_offer
/property list status=sold
```

**View a property's details:**
```
/property show P001
```

The details include address, status, purchase price, number of tenants, and linked mortgage offers.

**Add a new property (interactive):**
```
/property add
```

The agent will guide you step-by-step through entering the address, purchase price, status, and other details. You can type `/cancel` at any time to abandon the process.

---

### /mortgage

Manage mortgage offers across your properties.

**Add a mortgage offer (interactive):**
```
/mortgage add P001
```

The agent will walk you through entering the principal amount, interest rate, term, monthly payment, product type, and dates. Say `/cancel` to exit.

**Check expiring mortgages:**
```
/mortgage expiring
```

This shows mortgages expiring within 6 months (default).

**Custom expiry window:**
```
/mortgage expiring months=3
/mortgage expiring months=12
```

---

### /data

Query your company's SQL database (read-only). You need to know the table name and columns.

```
/data table=properties columns=id,address,status,purchase_price limit=20
```

With filters:
```
/data table=transactions columns=id,date,amount,description filters=status:completed limit=50
```

> **Security note:** Only SELECT queries are allowed. Table names must be pre-approved. You cannot modify data through this command.

---

### /reset

Clears your current conversation context. Use this when changing topics or if the agent seems to be referencing old messages incorrectly.

```
/reset
```

---

## Sending Media

You don't need commands for media — just send it through Telegram.

### Documents

**Supported formats:** PDF, DOCX, TXT

When you send a document, BusinessAgent:
1. Extracts all text content
2. Uses AI to determine the document type (invoice, tenancy agreement, EPC certificate, mortgage offer, completion statement, etc.)
3. Identifies the property address, monetary amounts, and dates
4. Stores everything in memory for later retrieval
5. Archives the original file

**Example:**
> You send a PDF of a mortgage offer from HSBC → The agent replies confirming ingestion, showing extracted metadata (type: mortgage_offer, address: 133 Bowland Drive, amount: £180,000, rate: 4.5%)

### Photos & Images

If you send a photo or image, BusinessAgent uses AI-powered OCR to extract any text. This is useful for snapping a picture of a paper invoice, letter, or certificate.

Large images in PDFs are automatically compressed to save storage.

### Voice Notes

Dictate a voice note and BusinessAgent transcribes it using AI, then stores both the transcript and audio reference in memory.

**Use cases:**
- "Remind me to chase Jones Solicitors about 133 Bowland Drive completion"
- "Mortgage broker called — offer from Barclays is 4.2% fixed 5 years, £750 fee"
- "Met the tenant at 45 Oak Road — bathroom needs retiling"

Everything you say becomes searchable later.

### Text Messages

Any plain text you send (that isn't a command) is automatically memorized. Think of it as a running notebook.

> "Just spoke to the estate agent — 22 Maple Street valuation came back at £320k"

This is searchable and retrievable forever, with the date and time you sent it.

---

## Natural Language Questions

You don't always need commands. Just ask questions in plain English.

| What you can ask | Example |
|---|---|
| **Compare mortgage offers** | "Compare mortgage offers for 133 Bowland Drive within last 2 months" |
| **Check certificate expiry** | "When is the EPC certificate expiring for 133 Bowland Drive?" |
| **View mortgage statements** | "Show me mortgage statements for 133 Bowland Drive for past 2 years" |
| **Check tenancy clauses** | "Does the tenancy agreement for 133 Bowland Drive have a 'no pet' clause?" |
| **Get document links** | "Give me links for all completion statements within last year" |
| **Match transactions** | "I see a transaction of £180 on 12 June 2026, do we have a corresponding invoice?" |
| **General knowledge** | "What did the solicitor say about the boundary dispute last month?" |

The agent understands time expressions like "last 2 months", "within last year", "past 2 years", and converts them to date ranges automatically.

---

## Understanding Memory & Retrieval

Everything you share with BusinessAgent is stored in a vector database (Qdrant), which means:

- **Semantic search** — It finds results based on meaning, not just exact keywords. "Rental income" will match "rent received" and "monthly rent"
- **Date filtering** — Every piece of information has an `effective_date`. If the source document has a date, that's used. Otherwise, the date you ingested it is used
- **Source tracking** — Every result tells you where it came from (document path, voice note date, text message timestamp)
- **Original documents** — You can always ask for the original file link

---

## Tips for Best Results

1. **Be specific with property addresses** — Use full addresses ("133 Bowland Drive") not "the flat" — the agent matches on address text
2. **Use consistent naming** — If you call it "133 Bowland Drive" in one document and "133 Bowland Dr" in another, searches may not catch both. Pick a convention and stick to it
3. **Send everything** — The more you feed it, the more useful it becomes. Bank statements, solicitor letters, estate agent emails, voice notes — it all builds your knowledge base
4. **Use voice notes on the go** — Quick thoughts while driving or walking between properties become searchable records
5. **Check `/mortgage expiring` regularly** — Missing a mortgage renewal deadline is expensive
6. **Ingest with event dates** — When adding documents, include `event_date=` if you know the actual document date. This makes time-based searches more accurate
7. **Review auto-extracted metadata** — The AI is good but not perfect. If the agent extracts wrong metadata from a document, you can correct it by sending a follow-up text message with the correct information

---

## Quick Reference Card

| Action | How |
|---|---|
| See commands | `/help` |
| Search knowledge | `/ask from=... to=... question` |
| Add document | Send file or `/ingest path event_date=...` |
| List documents | `/list type=... date_from=...` |
| Add property | `/property add` (interactive) |
| See properties | `/property list` |
| Add mortgage | `/mortgage add PROP-ID` (interactive) |
| Check expiries | `/mortgage expiring months=6` |
| Query database | `/data table=... columns=...` |
| Clear context | `/reset` |
| Send voice note | Telegram microphone button |
| Ask naturally | Just type your question |
| Cancel anything | Type `/cancel` |

---

*For technical setup and deployment instructions, see the README.md file provided to your team.*
