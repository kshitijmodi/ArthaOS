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
| Data structuring | pandas |
| Storage | SQLite |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector DB | FAISS |
| LLM inference | Groq API / Gemini API — LLaMA 3 8B / Gemini Flash (free tier) |
| Email ingestion | Gmail API (OAuth 2.0), Yahoo Mail (IMAP + app password) |
| Startup trigger | Windows startup task (catch-up fetch on boot) |
| Scheduler | APScheduler (daily agent runs) |
| File watcher | Python watchdog |
| Backend API | FastAPI |
| Frontend | Next.js + Tailwind CSS + shadcn/ui |
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
Embedding (all-MiniLM-L6-v2)
    ↓
FAISS Similarity Search
    ↓
Top-K Relevant Chunks Retrieved
    ↓
Context + Query → LLM (Groq / Gemini)
    ↓
Generated Answer → Dashboard or WhatsApp
```

### Agent Flow
```
Ingestion Complete / Daily Scheduled Trigger
    ↓
Load Recent Transactions from SQLite
    ↓
Run Detection Modules:
  - Overspend Detector       (>25% above 30-day rolling average)
  - Anomaly Detector         (>2x category average or unknown merchant)
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
Laptop startup → Windows startup task triggers email fetcher
    ↓
Read system_state table → fetch all emails since last_fetched_at
Gmail (OAuth 2.0) + Yahoo (IMAP)
    ↓
Download PDF attachments from whitelisted senders → /data/statements/
    ↓
watchdog detects new files → ingestion pipeline
    ↓
Parse → Validate → Structure → Store in SQLite → Generate FAISS embeddings
    ↓
Agent engine triggered
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

**Alerts:** `alert_id`, `alert_type`, `severity`, `description`, `related_transactions`, `created_at`, `status`, `whatsapp_sent`

**Email tracking:** `email_id`, `sender`, `subject`, `fetched_at`, `attachment_file`, `mailbox` (Gmail / Yahoo), `status`

**System state:** `mailbox`, `last_fetched_at`, `status` — used for startup catch-up fetch

---

## FastAPI Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Accept NL query, return RAG answer |
| `/transactions` | GET | Return paginated transaction list |
| `/alerts` | GET | Return all alerts with status |
| `/alerts/{id}/dismiss` | POST | Dismiss an alert |
| `/alerts/{id}/snooze` | POST | Snooze an alert |
| `/dashboard/summary` | GET | Spend summary cards data |
| `/ws/alerts` | WebSocket | Real-time alert push to dashboard |

---

## Dashboard (Next.js)

Dark mode finance aesthetic — data-dense, built with Tailwind CSS + shadcn/ui.

| Panel | Description |
|-------|-------------|
| **Alerts Panel** | Unread alerts with severity colour coding (red/amber). Dismiss, snooze, view linked transactions. Real-time sync via WebSocket. |
| **Spend Summary Cards** | Total spend this month vs last, top category, transaction count, upcoming EMIs/subscriptions. |
| **Query Interface** | Chat-style natural language input. Answers shown with source references. Same queries available via WhatsApp `/finance`. |
| **Transaction Table** | Full paginated list. Filterable, sortable. Inline category edit via dropdown. Confidence score indicator. |
| **Analytics Panel** | Monthly trend, category breakdown, month-over-month comparison *(Phase 2)*. |
| **Ingestion Status Panel** | Last fetch timestamps (Gmail + Yahoo), documents processed, parsing failures. |

---

## Expense Categories

Groceries · Rent · Utilities · Dining · Travel · Insurance · EMIs · Miscellaneous

Rule-based keyword mapping. Users can correct categories inline in the dashboard; corrections are stored and used to refine future rules.

---

## Getting Started

> Detailed setup instructions will be added as the project is built out.

**Prerequisites:**
- Python 3.10+
- Node.js 18+
- Groq API key or Gemini API key (free tier)
- Gmail API credentials (OAuth 2.0)
- Yahoo Mail app password (IMAP enabled)
- REA Communication Agent running (for WhatsApp integration)

---

## Roadmap

**Phase 1 — Core System** *(in progress)*
- [ ] Project scaffold + dependencies
- [ ] SQLite schema (all tables)
- [ ] Email fetcher — Gmail + Yahoo with startup catch-up
- [ ] PDF parsing + validation
- [ ] Categorization engine
- [ ] Embeddings + FAISS store
- [ ] FastAPI backend (core endpoints)
- [ ] RAG query pipeline
- [ ] Next.js dashboard (alerts panel, query interface, transaction table)
- [ ] Validation + testing framework

**Phase 2 — Agentic Layer**
- [ ] Agent engine (5 detection modules)
- [ ] WhatsApp integration via REA Communication Agent
- [ ] Real-time alert sync via WebSocket
- [ ] Daily agent schedule
- [ ] Category correction UI
- [ ] Analytics panel (charts)

**Phase 3 — Intelligence & Polish**
- [ ] Improved categorization logic
- [ ] Pipeline modularisation
- [ ] Affordability estimation
- [ ] Spend optimisation suggestions
- [ ] Trend-based recommendations
- [ ] Ingestion status panel refinements

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

## Success Metrics

| Metric | Target |
|--------|--------|
| Parsing accuracy | ≥ 90% correctly extracted transactions |
| Query accuracy | Evaluated against 10–15 predefined Q&A pairs |
| Response latency | < 5 seconds avg |
| Ingestion success rate | ≥ 95% of documents processed successfully |
| Alert precision | Alerts are genuinely actionable; no false positives on clean data |
| Email fetch reliability | ≥ 95% of statements successfully retrieved |
| Dashboard load time | < 2 seconds |

---

## License

ISC
