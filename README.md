# ArthaOS

**ArthaOS** is a local-first, agentic AI personal finance system for US-based accounts. It automatically ingests financial data from connected bank and investment accounts via Plaid and Teller, structures it into a queryable SQLite database, and proactively monitors your finances — surfacing alerts and insights without waiting to be asked.

Query your finances in natural language via a modern web dashboard or WhatsApp. Runs at minimal to zero recurring cost using free API tiers.

---

## What It Does

**Reactive (you ask):**
- "How much did I spend on groceries last month?"
- "What's my Fidelity 401k balance?"
- "Show my highest expenses this quarter"
- "Am I spending more this month than last month?"

**Proactive (it tells you):**
- "Your dining spend is 40% above your monthly average"
- "Unusual transaction detected — $850 at an unrecognised merchant"
- "Possible duplicate charge — same merchant + amount within 3 days"
- "Expected recurring charge missing this month"

---

## Tech Stack

| Component | Tool |
|-----------|------|
| Bank/investment data | Plaid API (investments, CC, loans) + Teller API (checking, savings) |
| Storage | SQLite |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) + FAISS |
| LLM inference | Groq API / Gemini API — LLaMA 3 / Gemini Flash (free tier) |
| Scheduler | APScheduler (daily agent runs, 30-min sync polls) |
| Backend API | FastAPI |
| Frontend | Next.js 14 + Tailwind CSS + recharts |
| WhatsApp layer | REA Communication Agent (whatsapp-web.js) |
| Real-time alerts | FastAPI WebSocket |
| Process management | PM2 |

---

## Architecture

### Query Flow
```
Dashboard AI chat
    ↓
POST /query → pipeline.query()
    ↓
Base context always injected:
  - All account balances (Teller + Plaid)
  - This month + last month spend by category
  - Last 15 transactions
  - Recent alerts
    ↓
+ FAISS similarity search (supplementary)
    ↓
Context + Query + History → LLM (Groq / Gemini)
    ↓
Answer → Dashboard
```

```
WhatsApp message
    ↓
REA Communication Agent
    ↓
Starts with /finance?
  ├── Yes → POST /finance → handle_finance_command()
  │           ├── Structured sub-commands (balance, summary, alerts, etc.)
  │           └── Free-form → RAG pipeline
  └── No  → POST /whatsapp/query → handle_finance_command() [same engine]
                └── REA spawns Claude Code CLI for code/engineering tasks
```

### Agent Flow
```
Daily Schedule (13:30 ET) / Post-sync trigger
    ↓
run_agent() — 10 detection modules:
  - Overspend Detector       (>25% above 30-day rolling average per category)
  - Anomaly Detector         (>2x category average or unknown merchant ≥$2000)
  - Spend Pace Monitor       (projected monthly overspend)
  - Weekly Velocity Check    (week-over-week acceleration)
  - All-Time High Detector   (new personal spending records)
  - Recurring Charge Monitor (missing or changed subscriptions/EMIs)
  - Duplicate Detector       (same merchant + amount within 7 days)
  - Monthly Budget Monitor   (on track to exceed prior month by >20%)
  - High Credit Balance Alert
  - Card Due Date Monitor
    ↓
Write Alerts → SQLite Alerts Table
    ↓
Push to Dashboard (WebSocket) + WhatsApp digest
```

### Data Sync Flow
```
APScheduler (every 30 minutes)
    ↓
Plaid sync: transactions, account balances, investment holdings
Teller sync: account balances, transactions
    ↓
Categorize new transactions (keyword rules → learned rules → LLM fallback)
    ↓
Update SQLite → trigger agent run if new data
```

---

## Data Model

**Transactions:** `date`, `description`, `amount`, `currency`, `transaction_type`, `category`, `category_source`

**Alerts:** `alert_id`, `alert_type`, `severity`, `description`, `related_transactions`, `created_at`, `status`, `whatsapp_sent`, `snoozed_until`

**Teller Accounts:** `enrollment_id`, `institution`, `name`, `type`, `subtype`, `balance_ledger`, `last_synced_at`

**Plaid Accounts:** `institution`, `name`, `type`, `subtype`, `balance_current`, `last_synced_at`

**Plaid Holdings:** `broker`, `ticker`, `quantity`, `current_price`, `market_value`, `gain_loss`, `gain_loss_day`

**Scheduled Tasks:** `task_type`, `description`, `params`, `fire_at`, `repeat_interval`, `status`, `initiated_by`

---

## FastAPI Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | NL query → RAG answer (dashboard AI chat) |
| `/finance` | POST | Finance slash command handler |
| `/whatsapp/query` | POST | WhatsApp message entry point (via REA) |
| `/transactions` | GET | Paginated, filtered, sortable transaction list |
| `/transactions/{id}/category` | PATCH | Inline category correction |
| `/transactions/bulk-categorize` | POST | Bulk category update |
| `/categorizer/recategorize-misc` | POST | Re-run categorizer on Miscellaneous rows |
| `/alerts` | GET | All alerts with status filter |
| `/alerts/{id}/dismiss` | POST | Dismiss an alert |
| `/alerts/{id}/snooze` | POST | Snooze an alert N days |
| `/alerts/stats` | GET | Alert counts by status and severity |
| `/dashboard/summary` | GET | Spend summary card data |
| `/dashboard/accounts-summary` | GET | Net worth, balances, investment totals |
| `/analytics/monthly-trend` | GET | 12-month spend trend |
| `/analytics/category-breakdown` | GET | This month by category |
| `/analytics/month-comparison` | GET | This month vs last month per category |
| `/insights/affordability` | POST | Affordability check for a given amount |
| `/insights/optimisation` | GET | Category-level spend optimisation suggestions |
| `/insights/recommendations` | GET | Trend-based financial health recommendations |
| `/plaid/connect` | POST | Link a Plaid account |
| `/plaid/resync` | POST | Force re-sync all Plaid transactions |
| `/teller/enroll` | POST | Enroll a Teller account |
| `/teller/enrollments` | GET | List connected Teller institutions |
| `/investments/holdings` | GET | All investment holdings by broker |
| `/investments/reingest` | POST | Force re-parse investment data |
| `/agent/run` | POST | Manually trigger agent detection run |
| `/ws/alerts` | WebSocket | Real-time alert push to dashboard |

---

## Dashboard

Dark mode finance aesthetic — data-dense, built with Next.js 14 + Tailwind CSS.

| Panel | Description |
|-------|-------------|
| **KPI Cards** | Net worth, income, spend, investments — month-aware |
| **Alerts Panel** | Unread alerts with severity colour coding. Dismiss, snooze. Real-time via WebSocket. |
| **AI Chat** | Natural language queries with conversation history. Always has full financial context. |
| **Analytics Panel** | Monthly trend chart, category donut, month-over-month comparison (recharts) |
| **Investments Panel** | Broker tabs, holdings table, P/L where available |
| **Transaction Table** | Full paginated list with inline category editing |
| **Insights Panel** | Affordability check, optimisation suggestions, trend recommendations |
| **Ingestion Status** | Connected accounts, sync status, Plaid Reset button |

---

## Expense Categories

Rent · Groceries · Dining · Travel · Utilities · Subscriptions · Insurance · EMIs · Shopping · Healthcare · Education · Investments · Income · Transfer · Fees & Interest · Miscellaneous

Categorization priority: user correction → learned rules (from past corrections) → keyword rules → LLM fallback.

Key US merchant mappings:
- **Bilt Rewards / Bilt Housing** → Rent
- **TST\* / SQ\*** (Square/Toast POS) → Dining
- **Hotel chains, airlines, Turo, SpotHero** → Travel
- **AT&T, Comcast, Honest Networks** → Utilities
- **Claude.ai, Netflix, Spotify** → Subscriptions
- **Seven Corners** → Insurance

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- Groq API key **or** Gemini API key (free tier)
- Plaid API credentials (client_id + secret)
- Teller API credentials (optional — for Teller-connected banks)
- REA Communication Agent — only needed for WhatsApp integration

### 1. Clone and configure

```bash
git clone https://github.com/kshitijmodi/ArthaOS.git
cd ArthaOS
cp .env.example .env
```

Edit `.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here

PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_secret
PLAID_ENV=production

TELLER_APP_ID=your_teller_app_id      # optional
TELLER_CERT_PATH=/path/to/cert.pem    # optional
TELLER_KEY_PATH=/path/to/key.pem      # optional
```

### 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend && npm install && cd ..
```

### 4. Start the backend

```bash
source .venv/bin/activate
python start.py
```

FastAPI starts at `http://localhost:8000`.

### 5. Start the frontend

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000`.

### 6. Connect your accounts

Go to the dashboard → Settings → Connected Accounts:
- **Plaid Link** — connect checking, savings, credit cards, investments, loans
- **Teller Link** — connect supported US banks

### 7. Manually trigger the agent (optional)

```bash
curl -X POST http://localhost:8000/agent/run
```

The agent runs automatically after each sync and daily at 13:30 ET.

### 8. WhatsApp integration (optional)

Requires the REA Communication Agent. Set in `.env`:

```env
REA_WEBHOOK_URL=http://localhost:3001/rea/incoming
```

Once connected, send `/finance <question>` on WhatsApp to query ArthaOS.
Plain messages (no `/finance`) are handled by Claude Code CLI for engineering tasks.

---

## Directory Structure

```
ArthaOS/
├── backend/
│   ├── agent/          # Detection engine, insights, notifier, task scheduler
│   ├── embeddings/     # FAISS vector store
│   ├── plaid/          # Plaid API client + sync
│   ├── teller/         # Teller API client + sync
│   ├── processing/     # Categorizer (US merchant rules), normalizer
│   ├── rag/            # Query pipeline, LLM client (Groq + Gemini)
│   ├── storage/        # SQLite schema and connection manager
│   ├── config.py
│   ├── main.py         # FastAPI app + all endpoints
│   └── scheduler.py
├── frontend/
│   ├── app/            # Next.js app router
│   ├── components/     # Dashboard panels
│   ├── hooks/          # useWebSocket
│   └── lib/            # API client, utils, types
├── deploy/
│   ├── sync.ps1        # Windows → GCP sync script
│   └── ecosystem.linux.config.js
├── data/
│   └── statements/     # Drop PDFs here (if ever needed)
├── eval/               # Evaluation dataset + runner
├── start.py            # One-command startup
├── requirements.txt
└── .env.example
```

---

## Known Limitations

- **P/L Open always shows "—"** — Plaid does not return `cost_basis` for Robinhood, Schwab, or Fidelity accounts. Unrealized gain/loss cannot be calculated without it.
- **No PDF ingestion** — This deployment uses only Plaid and Teller live connections. PDF parsing infrastructure exists in the codebase but is unused.
- **Income may show $0** — If BofA (payroll account) Teller enrollment is broken, re-connect it in Settings → Connected Accounts.

---

## Privacy & Security

- All financial data stored in SQLite on your own server — never sent to external services
- LLM receives only structured context excerpts, never raw account credentials
- Plaid and Teller access tokens stored locally in SQLite
- WhatsApp routing uses REA's existing session — no separate WhatsApp session required

---

## License

ISC
