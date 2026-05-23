# ArthaOS

**ArthaOS** is a local-first, agentic AI personal finance system. It automatically ingests financial documents from your email and local folders, structures them into queryable data, and proactively monitors your finances — surfacing alerts and insights without waiting to be asked.

Query your finances in natural language via a modern web dashboard or WhatsApp. Runs at minimal to zero recurring cost using free API tiers.

---

## What It Does

**Reactive (you ask):**
- "How much did I spend on groceries last month?"
- "List all recurring EMIs"
- "Show my highest expenses this quarter"
- "Am I spending more this month than last month?"

**Proactive (it tells you):**
- "Your dining spend is 40% above your monthly average"
- "Unusual transaction detected — ₹8,500 at an unrecognised merchant"
- "Possible duplicate charge — Swiggy ₹450 appears twice within 3 days"
- "Expected Jio bill not seen this month"

---

## Tech Stack

| Component | Tool |
|-----------|------|
| PDF parsing | PyMuPDF, pdfplumber |
| Storage | SQLite |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector DB | FAISS |
| LLM inference | Groq API / Gemini API — LLaMA 3 8B / Gemini Flash (free tier) |
| Email ingestion | Gmail API (OAuth 2.0), Yahoo Mail (IMAP + app password) |
| Scheduler | APScheduler (daily agent runs) |
| File watcher | Python watchdog |
| Backend API | FastAPI |
| Frontend | Next.js 14 + Tailwind CSS + recharts |
| WhatsApp layer | REA Communication Agent (whatsapp-web.js) |
| Real-time alerts | FastAPI WebSocket |

---

## Architecture

### RAG Flow
```
User Query (Dashboard or WhatsApp)
    ↓
FastAPI receives query
    ↓
SQL context (spend totals, EMIs, subscriptions) extracted first
    ↓
FAISS similarity search for supplementary document context
    ↓
Context + Query → LLM (Groq / Gemini)
    ↓
Generated Answer → Dashboard or WhatsApp
```

### Agent Flow
```
Ingestion Complete / Daily Scheduled Trigger (07:30)
    ↓
Load Recent Transactions from SQLite
    ↓
Run Detection Modules:
  - Overspend Detector       (>25% above 30-day rolling average)
  - Anomaly Detector         (>2x category average or unknown merchant ≥₹2000)
  - Recurring Charge Monitor (missing or changed EMI/subscription)
  - Duplicate Detector       (same merchant + amount within 7 days)
  - Monthly Budget Monitor   (on track to exceed prior month by >20%)
    ↓
Write Alerts → SQLite Alerts Table
    ↓
Push to Dashboard (WebSocket) + WhatsApp (high severity only)
```

### Automated Ingestion Flow
```
Laptop startup → email fetcher catch-up
    ↓
Read system_state table → fetch all emails since last_fetched_at
Gmail (OAuth 2.0) + Yahoo (IMAP)
    ↓
Download PDF attachments from whitelisted senders → /data/statements/
    ↓
watchdog detects new files → ingestion pipeline
    ↓
Parse → Normalize → Validate → Categorize → Store → Embed
    ↓
Agent engine triggered (background thread)
    ↓
Update last_fetched_at in system_state
```

### WhatsApp Routing Flow (via REA)
```
User Personal WhatsApp
    ↓
REA Communication Agent (whatsapp-web.js)
    ↓
Message starts with /finance?
  ├── Yes → ArthaOS FastAPI backend → RAG pipeline → answer
  └── No  → REA Orchestration Agent (existing flow)
    ↓
REA Communication Agent → reply to user
```

---

## Data Model

**Transactions:** `date`, `description`, `amount`, `currency`, `transaction_type`, `category`, `source_file`, `raw_text`, `confidence_score`

**Alerts:** `alert_id`, `alert_type`, `severity`, `description`, `related_transactions`, `created_at`, `status`, `whatsapp_sent`, `snoozed_until`

**Email tracking:** `email_id`, `sender`, `subject`, `fetched_at`, `attachment_file`, `mailbox` (Gmail / Yahoo), `status`

**System state:** `mailbox`, `last_fetched_at`, `status` — used for startup catch-up fetch

**Ingested files:** `file_hash`, `filename`, `file_size`, `status`, `failure_reason`, `transaction_count`, `verified`, `ingested_at`

**Category corrections:** `description_hash`, `description`, `category`, `corrected_at` — drives learned categorization rules

---

## FastAPI Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | NL query → RAG answer |
| `/transactions` | GET | Paginated, filtered, sortable transaction list |
| `/transactions/{id}/category` | PATCH | Inline category correction |
| `/transactions/bulk-categorize` | POST | Bulk category update |
| `/categorizer/recategorize-misc` | POST | Re-run categorizer on Miscellaneous rows |
| `/alerts` | GET | All alerts with status filter |
| `/alerts/{id}/dismiss` | POST | Dismiss an alert |
| `/alerts/{id}/snooze` | POST | Snooze an alert N days |
| `/alerts/stats` | GET | Alert counts by status and severity |
| `/dashboard/summary` | GET | Spend summary card data |
| `/analytics/monthly-trend` | GET | 12-month spend trend |
| `/analytics/category-breakdown` | GET | This month by category |
| `/analytics/month-comparison` | GET | This month vs last month per category |
| `/insights/affordability` | POST | Affordability check for a given amount |
| `/insights/optimisation` | GET | Category-level spend optimisation suggestions |
| `/insights/recommendations` | GET | Trend-based financial health recommendations |
| `/ingestion/status` | GET | Mailbox state + recent/failed ingestions |
| `/ingest/upload` | POST | Manual PDF upload |
| `/ingest/fetch-email` | POST | Manually trigger email fetch |
| `/agent/run` | POST | Manually trigger agent detection run |
| `/ws/alerts` | WebSocket | Real-time alert push to dashboard |
| `/whatsapp/query` | POST | WhatsApp query entry point (via REA) |

---

## Dashboard

Dark mode finance aesthetic — data-dense, built with Next.js 14 + Tailwind CSS.

| Panel | Tab | Description |
|-------|-----|-------------|
| **Alerts Panel** | Always visible | Unread alerts with severity colour coding. Dismiss, snooze. Real-time sync via WebSocket. |
| **Spend Summary Cards** | Overview | Total spend this month vs last, delta %, top category, transaction count, upcoming EMIs. |
| **Query Interface** | Overview | Chat-style natural language input with suggested prompts. Source references shown. |
| **Ingestion Status** | Overview | Last fetch timestamps (Gmail + Yahoo), documents processed, parsing failures. |
| **Analytics Panel** | Analytics | Monthly trend area chart, category donut, month-over-month bar chart (recharts). |
| **Transaction Table** | Transactions | Full paginated list. Filter by category/type, sort, inline category edit dropdown. |
| **Insights Panel** | Insights | Financial health cards, affordability check tool, optimisation opportunities with progress bars. |

---

## Expense Categories

Groceries · Rent · Utilities · Dining · Travel · Insurance · EMIs · Subscriptions · Entertainment · Shopping · Miscellaneous

Categorization priority: user correction → learned rules (derived from past corrections) → keyword rules → LLM fallback. Corrections stored in SQLite and used to auto-refine future classifications.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- Groq API key **or** Gemini API key (free tier)
- Gmail API credentials (OAuth 2.0) — optional if using Yahoo only
- Yahoo Mail app password (IMAP enabled) — optional if using Gmail only
- REA Communication Agent running — only needed for WhatsApp integration

---

### 1. Clone and configure

```bash
git clone https://github.com/kshitijmodi/ArthaOS.git
cd ArthaOS
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here        # get free key at console.groq.com
```

For email ingestion, also add your Yahoo or Gmail credentials (see sections below).

---

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, PyMuPDF, pdfplumber, sentence-transformers, FAISS, Groq SDK, APScheduler, watchdog, and Google API clients. First run will download the `all-MiniLM-L6-v2` embedding model (~90 MB).

---

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

### 4. Set up Gmail (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project
2. Enable the **Gmail API**
3. Create OAuth 2.0 credentials → Desktop app → download as `gmail_credentials.json`
4. Place `gmail_credentials.json` in the project root
5. On first run, a browser window will open to authorise access. The token is saved as `gmail_token.json` and auto-refreshed thereafter.

---

### 5. Set up Yahoo Mail (optional)

1. In your Yahoo account → Security → Generate app password
2. Add to `.env`:
   ```env
   YAHOO_EMAIL=your_email@yahoo.com
   YAHOO_APP_PASSWORD=your_app_password
   ```

---

### 6. Start the backend

```bash
python start.py
```

This will:
- Initialise the SQLite database at `data/arthaos.db`
- Run a catch-up email fetch (all statements since last run)
- Ingest any PDFs already in `data/statements/`
- Start the FastAPI server at `http://localhost:8000`
- Start the file watcher and daily scheduler

---

### 7. Start the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

### 8. Upload your first bank statement

**Option A — drop a PDF:**
Copy any bank statement PDF into `data/statements/`. The watchdog will detect it and ingest automatically within a few seconds.

**Option B — dashboard upload:**
Go to the Overview tab → Ingestion Status panel → upload button.

**Option C — API:**
```bash
curl -X POST http://localhost:8000/ingest/upload \
  -F "file=@/path/to/statement.pdf"
```

---

### 9. Manually trigger the agent (optional)

The agent runs automatically after each ingestion and daily at 07:30. To run it manually:

```bash
curl -X POST http://localhost:8000/agent/run
```

---

### 10. WhatsApp integration (optional)

Requires the REA Communication Agent running on port 3001. Set in `.env`:

```env
REA_WEBHOOK_URL=http://localhost:3001/rea/incoming
```

Once connected, send `/finance <your question>` on WhatsApp to query ArthaOS.

---

### Directory structure

```
ArthaOS/
├── backend/
│   ├── agent/          # Detection engine, insights, notifier
│   ├── embeddings/     # FAISS vector store
│   ├── ingestion/      # Email fetcher, PDF parser, validator, pipeline, watcher
│   ├── processing/     # Categorizer, normalizer
│   ├── rag/            # Query pipeline, LLM client
│   ├── storage/        # SQLite schema and connection manager
│   ├── config.py
│   ├── main.py         # FastAPI app
│   └── scheduler.py
├── frontend/
│   ├── app/            # Next.js app router
│   ├── components/     # Dashboard panels
│   ├── hooks/          # useWebSocket
│   └── lib/            # API client, utils, types
├── data/
│   └── statements/     # Drop PDFs here for manual ingestion
├── eval/               # Evaluation dataset + runner
├── start.py            # One-command startup
├── requirements.txt
└── .env.example
```

---

## Evaluation

Run the built-in eval suite against a seeded database:

```bash
python eval/run_eval.py
```

Tests 8 Q&A pairs covering SQL aggregation, RAG retrieval, categorization, date parsing, and multi-period comparison. Must-pass set: `spend_jan`, `dining_category`, `emi_query`, `top_spend`, `subscriptions`.

---

## Performance Targets

| Component | Target |
|-----------|--------|
| Structured SQL queries | < 1 second |
| RAG retrieval + LLM response | < 5 seconds |
| Email fetch + ingestion cycle | < 2 minutes |
| Agent evaluation run | < 30 seconds |
| Dashboard load | < 2 seconds |
| Alert WebSocket push | < 1 second |

---

## Privacy & Security

- All financial data stored locally in SQLite — never sent to external services
- LLM receives only sanitised context chunks, not raw statements or account details
- Gmail OAuth 2.0 with automatic token refresh; Yahoo via IMAP app password
- Per-mailbox email tracking in SQLite to prevent duplicate ingestion
- WhatsApp routing shares REA's existing session — no separate WhatsApp session required

---

## Roadmap

**Phase 1 — Core System** ✅
- [x] Project scaffold + dependencies
- [x] SQLite schema (all tables)
- [x] Email fetcher — Gmail + Yahoo with startup catch-up
- [x] PDF parsing + validation
- [x] Categorization engine
- [x] Embeddings + FAISS store
- [x] FastAPI backend (core endpoints)
- [x] RAG query pipeline
- [x] Next.js dashboard (alerts panel, query interface, transaction table)
- [x] Validation + testing framework

**Phase 2 — Agentic Layer** ✅
- [x] Agent engine (5 detection modules)
- [x] WhatsApp integration via REA Communication Agent
- [x] Real-time alert sync via WebSocket
- [x] Daily agent schedule
- [x] Category correction UI
- [x] Analytics panel (charts)

**Phase 3 — Intelligence & Polish** ✅
- [x] Improved categorization — learned rules + bulk correction + recategorize-misc
- [x] Transaction normalizer (noise token stripping)
- [x] Affordability estimation
- [x] Spend optimisation suggestions
- [x] Trend-based recommendations
- [x] Insights dashboard panel

---

## License

ISC
