"""
ArthaOS FastAPI backend.
Serves all dashboard data, handles queries from dashboard and WhatsApp,
and pushes real-time alerts via WebSocket.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import STATEMENTS_DIR
from backend.storage.database import init_db, db
from backend.ingestion.watcher import start_watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

manager = ConnectionManager()


async def push_alert(alert: dict):
    await manager.broadcast({"type": "alert", "data": alert})


# ---------------------------------------------------------------------------
# App lifespan — init DB and start watcher
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Pre-warm embedding model in main thread — avoids torch deadlock on first thread-pool call
    try:
        from backend.embeddings.embedder import _get_model
        _get_model()
        logger.info("[ArthaOS] Embedding model warmed up")
    except Exception as exc:
        logger.warning("[ArthaOS] Embedding model warm-up failed: %s", exc)
    # Start file watcher in background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: start_watcher(block=True))
    # Re-apply static rules to auto-categorized transactions so any rule changes
    # (e.g. adding Investments before Transfer) take effect on existing data.
    try:
        from backend.processing.categorizer import recategorize_all
        updated = recategorize_all()
        if updated:
            logger.info("[ArthaOS] Startup recategorization updated %d transactions", updated)
    except Exception as exc:
        logger.warning("[ArthaOS] Startup recategorization failed: %s", exc)
    # Start daily scheduler
    from backend.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("[ArthaOS] Backend ready")
    yield
    stop_scheduler()


app = FastAPI(title="ArthaOS", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
        # Tailscale access
        "http://100.102.103.53:3000", "http://100.102.103.53:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    history: list[dict] = []

class CategoryUpdateRequest(BaseModel):
    category: str

class SnoozeRequest(BaseModel):
    days: int = 3


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/query")
def query_endpoint(req: QueryRequest):
    from backend.rag.pipeline import query
    result = query(req.query, history=req.history or [])
    return {
        "answer": result.answer,
        "low_confidence": result.low_confidence,
        "sources": [{"source": s.get("source"), "score": s.get("score")} for s in result.sources],
    }


@app.post("/finance")
def finance_command_endpoint(req: QueryRequest):
    query = req.query.strip()
    logger.debug("[Finance] Raw request body: query=%r (stripped_len=%d)", req.query, len(query))
    if not query:
        raise HTTPException(status_code=400, detail="Finance command query must not be empty")

    logger.info("[Finance] Received command: %r", query)

    try:
        from backend.agent.engine import handle_finance_command
        result = handle_finance_command(query, history=req.history or [])
    except ImportError as exc:
        logger.error("[Finance] Failed to import engine: %s", exc)
        raise HTTPException(status_code=500, detail="Finance command handler unavailable")
    except Exception as exc:
        logger.exception("[Finance] Unexpected error for command %r: %s", query, exc)
        raise HTTPException(status_code=500, detail="Internal error processing finance command")

    if not isinstance(result, dict):
        logger.error("[Finance] Engine returned unexpected type: %r", type(result))
        raise HTTPException(status_code=500, detail="Finance command returned an invalid response")

    answer = result.get("answer") or ""
    low_confidence = bool(result.get("low_confidence", False))
    sources = result.get("sources") if isinstance(result.get("sources"), list) else []

    logger.info("[Finance] Command %r completed (low_confidence=%s)", query, low_confidence)

    return {
        "answer": answer,
        "low_confidence": low_confidence,
        "sources": sources,
    }


@app.get("/transactions")
def get_transactions(
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    transaction_type: Optional[str] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    starred: Optional[bool] = None,
    charges_only: Optional[bool] = None,
    query: Optional[str] = None,
):
    allowed_sort = {"date", "amount", "category", "description"}
    if sort_by not in allowed_sort:
        sort_by = "date"
    sort_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"

    filters = ["1=1"]
    params: list = []
    if category:
        filters.append("category = ?")
        params.append(category)
    if transaction_type:
        filters.append("transaction_type = ?")
        params.append(transaction_type)
    if starred is True:
        filters.append("starred = 1")
    if charges_only is True:
        filters.append("category = 'Fees & Interest'")
    if query:
        filters.append("description LIKE ?")
        params.append(f"%{query}%")

    where = " AND ".join(filters)
    offset = (page - 1) * page_size

    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM transactions WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM transactions WHERE {where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "transactions": [dict(r) for r in rows],
    }


@app.patch("/transactions/{tx_id}/star")
def toggle_star(tx_id: int):
    with db() as conn:
        row = conn.execute("SELECT starred FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        new_val = 0 if row["starred"] else 1
        conn.execute("UPDATE transactions SET starred = ? WHERE id = ?", (new_val, tx_id))
    return {"starred": bool(new_val)}


@app.patch("/transactions/{tx_id}/category")
def update_category(tx_id: int, req: CategoryUpdateRequest):
    from backend.processing.categorizer import apply_correction
    ok = apply_correction(tx_id, req.category)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid transaction ID or category")
    return {"status": "updated"}


@app.get("/alerts")
def get_alerts(status: Optional[str] = None):
    filters = ["1=1"]
    params: list = []
    if status:
        filters.append("status = ?")
        params.append(status)
    # Re-activate snoozed alerts past their snooze time
    filters_str = " AND ".join(filters)
    with db() as conn:
        conn.execute(
            "UPDATE alerts SET status='unread' WHERE status='snoozed' AND snoozed_until <= datetime('now')"
        )
        rows = conn.execute(
            f"SELECT * FROM alerts WHERE {filters_str} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


@app.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: int):
    with db() as conn:
        conn.execute("UPDATE alerts SET status='dismissed' WHERE id=?", (alert_id,))
    return {"status": "dismissed"}


@app.post("/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: int, req: SnoozeRequest):
    with db() as conn:
        conn.execute(
            "UPDATE alerts SET status='snoozed', snoozed_until=datetime('now', ?) WHERE id=?",
            (f"+{req.days} days", alert_id),
        )
    return {"status": "snoozed", "days": req.days}


@app.get("/dashboard/summary")
def dashboard_summary():
    with db() as conn:
        this_month = conn.execute(
            """SELECT ROUND(SUM(amount),2) as total FROM transactions
               WHERE transaction_type='debit'
               AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()["total"] or 0

        last_month = conn.execute(
            """SELECT ROUND(SUM(amount),2) as total FROM transactions
               WHERE transaction_type='debit'
               AND strftime('%Y-%m', date) = strftime('%Y-%m', date('now','-1 month'))"""
        ).fetchone()["total"] or 0

        top_category = conn.execute(
            """SELECT category FROM transactions
               WHERE transaction_type='debit'
               AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1"""
        ).fetchone()

        tx_count = conn.execute(
            """SELECT COUNT(*) as c FROM transactions
               WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()["c"]

        upcoming = conn.execute(
            """SELECT description, amount FROM transactions
               WHERE category IN ('EMIs','Subscriptions','Insurance')
               AND transaction_type='debit'
               GROUP BY description ORDER BY MAX(date) DESC LIMIT 5"""
        ).fetchall()

        unread_alerts = conn.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE status='unread'"
        ).fetchone()["c"]

    delta = this_month - last_month
    delta_pct = round((delta / last_month * 100), 1) if last_month else 0

    return {
        "this_month_spend": this_month,
        "last_month_spend": last_month,
        "delta": delta,
        "delta_pct": delta_pct,
        "top_category": top_category["category"] if top_category else None,
        "transaction_count": tx_count,
        "upcoming_charges": [dict(r) for r in upcoming],
        "unread_alerts": unread_alerts,
    }


@app.get("/dashboard/accounts-summary")
def accounts_summary(as_of: Optional[str] = None):
    """
    Bank balance, CC balance (period-aware if as_of supplied), 401K, Stocks, net worth.
    as_of: ISO date string (YYYY-MM-DD). When supplied, uses the balance reading from
    teller_balance_history closest to (but not after) that date. Falls back to the
    current teller_accounts value when no history exists for that period.
    """
    with db() as conn:
        if as_of:
            # For each account, find the most recent history row on or before as_of
            # prefer_ledger=True for CC/loans where balance_available is the credit line, not what's owed
            def period_balance(account_type_filter: str, prefer_ledger: bool = False) -> float:
                if prefer_ledger:
                    hist_col = "COALESCE(h.balance_ledger, h.balance_available)"
                    curr_col = "COALESCE(a.balance_ledger, 0)"
                else:
                    hist_col = "COALESCE(h.balance_available, h.balance_ledger)"
                    curr_col = "COALESCE(a.balance_available, a.balance_ledger, 0)"
                rows = conn.execute(
                    f"""SELECT a.account_id, a.type,
                               COALESCE(
                                 (SELECT {hist_col}
                                  FROM teller_balance_history h
                                  WHERE h.account_id = a.account_id
                                    AND date(h.recorded_at) <= date(?)
                                  ORDER BY h.recorded_at DESC LIMIT 1),
                                 {curr_col}
                               ) as bal
                        FROM teller_accounts a
                        JOIN teller_enrollments te ON a.enrollment_id = te.enrollment_id
                        WHERE te.status = 'active' AND {account_type_filter}""",
                    (as_of,)
                ).fetchall()
                return sum(abs(r["bal"] or 0) for r in rows)

            bank_balance = round(period_balance("lower(a.type) IN ('depository','checking','savings')"), 2)
            cc_balance   = round(period_balance("lower(a.type) IN ('credit','credit_card')", prefer_ledger=True), 2)
            loan_balance = round(period_balance("lower(a.type) IN ('loan','auto_loan','mortgage','student_loan','personal_loan')", prefer_ledger=True), 2)

            # Plaid has no balance history — add current Plaid balances as best approximation.
            # Only CC (Bilt) matters here; no Plaid depository accounts exist for this user.
            p_bank_as_of = conn.execute(
                """SELECT COALESCE(SUM(COALESCE(balance_available, balance_current, 0)), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'depository'"""
            ).fetchone()
            p_cc_as_of = conn.execute(
                """SELECT COALESCE(SUM(MAX(0, COALESCE(balance_current, 0))), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'credit'"""
            ).fetchone()
            p_loan_as_of = conn.execute(
                """SELECT COALESCE(SUM(ABS(COALESCE(balance_current, 0))), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'loan'"""
            ).fetchone()
            bank_balance = round(bank_balance + (p_bank_as_of["total"] or 0), 2)
            cc_balance   = round(cc_balance   + (p_cc_as_of["total"]  or 0), 2)
            loan_balance = round(loan_balance  + (p_loan_as_of["total"] or 0), 2)
        else:
            # Teller depository (active enrollments only)
            t_bank = conn.execute(
                """SELECT COALESCE(SUM(COALESCE(a.balance_available, a.balance_ledger, 0)), 0) as total
                   FROM teller_accounts a
                   JOIN teller_enrollments te ON a.enrollment_id = te.enrollment_id
                   WHERE te.status = 'active'
                     AND lower(a.type) IN ('depository','checking','savings')"""
            ).fetchone()
            # Plaid depository
            p_bank = conn.execute(
                """SELECT COALESCE(SUM(COALESCE(balance_available, balance_current, 0)), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'depository'"""
            ).fetchone()
            bank_balance = round((t_bank["total"] or 0) + (p_bank["total"] or 0), 2)

            # Teller CC (active enrollments only)
            t_cc = conn.execute(
                """SELECT COALESCE(SUM(ABS(COALESCE(a.balance_ledger, 0))), 0) as total
                   FROM teller_accounts a
                   JOIN teller_enrollments te ON a.enrollment_id = te.enrollment_id
                   WHERE te.status = 'active'
                     AND lower(a.type) IN ('credit','credit_card')"""
            ).fetchone()
            # Plaid CC
            p_cc = conn.execute(
                """SELECT COALESCE(SUM(MAX(0, COALESCE(balance_current, 0))), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'credit'"""
            ).fetchone()
            cc_balance = round((t_cc["total"] or 0) + (p_cc["total"] or 0), 2)

            # Teller loans (active enrollments only)
            t_loan = conn.execute(
                """SELECT COALESCE(SUM(ABS(COALESCE(a.balance_ledger, a.balance_available, 0))), 0) as total
                   FROM teller_accounts a
                   JOIN teller_enrollments te ON a.enrollment_id = te.enrollment_id
                   WHERE te.status = 'active'
                     AND lower(a.type) IN ('loan','auto_loan','mortgage','student_loan','personal_loan')"""
            ).fetchone()
            # Plaid loans
            p_loan = conn.execute(
                """SELECT COALESCE(SUM(ABS(COALESCE(balance_current, 0))), 0) as total
                   FROM plaid_accounts WHERE lower(type) = 'loan'"""
            ).fetchone()
            loan_balance = round((t_loan["total"] or 0) + (p_loan["total"] or 0), 2)

        # 401K = Fidelity holdings (always latest snapshot)
        fidelity_row = conn.execute(
            """SELECT COALESCE(SUM(h.total_value), 0) as total
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               ) AND lower(h.broker) LIKE '%fidelity%'"""
        ).fetchone()
        portfolio_401k = round(fidelity_row["total"], 2)

        # Stocks = Robinhood + Schwab (always latest snapshot)
        stocks_row = conn.execute(
            """SELECT COALESCE(SUM(h.total_value), 0) as total
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               ) AND (lower(h.broker) LIKE '%robinhood%' OR lower(h.broker) LIKE '%schwab%')"""
        ).fetchone()
        portfolio_stocks = round(stocks_row["total"], 2)

    net_worth = round(bank_balance + portfolio_401k + portfolio_stocks - cc_balance - loan_balance, 2)

    return {
        "bank_balance": bank_balance,
        "cc_balance": cc_balance,
        "loan_balance": loan_balance,
        "portfolio_401k": portfolio_401k,
        "portfolio_stocks": portfolio_stocks,
        "net_worth": net_worth,
        "as_of": as_of,
    }


@app.get("/dashboard/accounts-detail")
def accounts_detail():
    """Per-account breakdown for KPI card drill-downs (bank, CC, loan, net worth)."""
    with db() as conn:
        teller_bank = conn.execute(
            """SELECT ta.institution, ta.name, ta.type, ta.subtype,
                      COALESCE(ta.balance_available, ta.balance_ledger, 0) as balance
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
                 AND lower(ta.type) IN ('depository','checking','savings')"""
        ).fetchall()
        plaid_bank = conn.execute(
            """SELECT institution, name, type, subtype,
                      COALESCE(balance_available, balance_current, 0) as balance
               FROM plaid_accounts WHERE lower(type) = 'depository'"""
        ).fetchall()
        teller_cc = conn.execute(
            """SELECT ta.institution, ta.name, ta.type, ta.subtype,
                      ABS(COALESCE(ta.balance_ledger, 0)) as balance
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
                 AND lower(ta.type) IN ('credit','credit_card')"""
        ).fetchall()
        plaid_cc = conn.execute(
            """SELECT institution, name, type, subtype,
                      MAX(0, COALESCE(balance_current, 0)) as balance
               FROM plaid_accounts WHERE lower(type) = 'credit'"""
        ).fetchall()
        teller_loan = conn.execute(
            """SELECT ta.institution, ta.name, ta.type, ta.subtype,
                      ABS(COALESCE(ta.balance_ledger, ta.balance_available, 0)) as balance
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
                 AND lower(ta.type) IN ('loan','auto_loan','mortgage','student_loan','personal_loan')"""
        ).fetchall()
        plaid_loan = conn.execute(
            """SELECT institution, name, type, subtype,
                      ABS(COALESCE(balance_current, 0)) as balance
               FROM plaid_accounts WHERE lower(type) = 'loan'"""
        ).fetchall()
        recent_txns = conn.execute(
            """SELECT date, description, amount, transaction_type, category, institution
               FROM transactions ORDER BY date DESC LIMIT 10"""
        ).fetchall()

    return {
        "bank_accounts":  [dict(r) for r in teller_bank] + [dict(r) for r in plaid_bank],
        "cc_accounts":    [dict(r) for r in teller_cc]   + [dict(r) for r in plaid_cc],
        "loan_accounts":  [dict(r) for r in teller_loan] + [dict(r) for r in plaid_loan],
        "recent_transactions": [dict(r) for r in recent_txns],
    }


@app.get("/ingestion/status")
def ingestion_status():
    with db() as conn:
        state = conn.execute("SELECT * FROM system_state").fetchall()
        recent = conn.execute(
            "SELECT * FROM ingested_files ORDER BY ingested_at DESC LIMIT 10"
        ).fetchall()
        failures = conn.execute(
            "SELECT * FROM ingested_files WHERE status='failed' ORDER BY ingested_at DESC LIMIT 5"
        ).fetchall()
    return {
        "mailbox_state": [dict(r) for r in state],
        "recent_files": [dict(r) for r in recent],
        "failures": [dict(r) for r in failures],
    }


@app.post("/ingest/upload")
async def upload_file(file: UploadFile = File(...)):
    """Manual file upload endpoint."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    dest = STATEMENTS_DIR / file.filename
    dest.write_bytes(await file.read())
    # Watcher will pick it up automatically; also trigger directly
    from backend.ingestion.pipeline import ingest_file
    result = ingest_file(dest)
    return result


@app.post("/ingest/fetch-email")
def trigger_email_fetch():
    """Manually trigger email fetch."""
    from backend.ingestion.email_fetcher import run_fetch
    from backend.ingestion.pipeline import ingest_file
    files = run_fetch()
    results = [ingest_file(f) for f in files]
    return {"fetched": len(files), "results": results}


@app.post("/agent/run")
async def trigger_agent():
    """Manually trigger the agent detection run."""
    from backend.agent.engine import run_agent
    from backend.agent.notifier import push_new_alerts
    alert_ids = run_agent()
    await push_new_alerts(alert_ids)
    return {"new_alerts": len(alert_ids), "alert_ids": alert_ids}


@app.get("/charge-alerts")
def get_charge_alerts(
    alert_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
):
    allowed_types = {"duplicate", "interest", "late_fee", "suspicious"}
    filters = ["1=1"]
    params: list = []
    if alert_type:
        if alert_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Invalid alert_type. Must be one of: {', '.join(sorted(allowed_types))}")
        filters.append("alert_type = ?")
        params.append(alert_type)
    if start_date:
        filters.append("date(created_at) >= date(?)")
        params.append(start_date)
    if end_date:
        filters.append("date(created_at) <= date(?)")
        params.append(end_date)
    if status:
        filters.append("status = ?")
        params.append(status)

    where = " AND ".join(filters)
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM charge_alerts WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return {"charge_alerts": [dict(r) for r in rows]}


@app.post("/charge-alerts/{alert_id}/dismiss")
def dismiss_charge_alert(alert_id: int):
    with db() as conn:
        result = conn.execute(
            "UPDATE charge_alerts SET status='dismissed' WHERE id=?", (alert_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Charge alert not found")
    return {"status": "dismissed"}


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

class GoalCreateRequest(BaseModel):
    name: str
    goal_type: str
    category: Optional[str] = None
    target_amount: float
    target_date: Optional[str] = None
    period: str = "monthly"
    notes: Optional[str] = None

class GoalUpdateRequest(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[str] = None
    period: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

@app.get("/goals")
def list_goals():
    from backend.agent.goals import compute_progress
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM goals WHERE status != 'abandoned' ORDER BY created_at DESC"
        ).fetchall()
    goals = [compute_progress(dict(r)) for r in rows]
    return {"goals": goals}

@app.post("/goals")
def create_goal(req: GoalCreateRequest):
    allowed_types = {"spend_limit", "savings", "investment", "custom"}
    if req.goal_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"goal_type must be one of: {', '.join(sorted(allowed_types))}")
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO goals (name, goal_type, category, target_amount, target_date, period, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (req.name, req.goal_type, req.category, req.target_amount,
             req.target_date, req.period, req.notes),
        )
        goal_id = cur.lastrowid
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    from backend.agent.goals import compute_progress
    return compute_progress(dict(row))

@app.patch("/goals/{goal_id}")
def update_goal(goal_id: int, req: GoalUpdateRequest):
    with db() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        fields, params = [], []
        if req.name is not None:
            fields.append("name = ?"); params.append(req.name)
        if req.target_amount is not None:
            fields.append("target_amount = ?"); params.append(req.target_amount)
        if req.target_date is not None:
            fields.append("target_date = ?"); params.append(req.target_date)
        if req.period is not None:
            fields.append("period = ?"); params.append(req.period)
        if req.status is not None:
            fields.append("status = ?"); params.append(req.status)
        if req.notes is not None:
            fields.append("notes = ?"); params.append(req.notes)
        if fields:
            fields.append("updated_at = datetime('now')")
            params.append(goal_id)
            conn.execute(f"UPDATE goals SET {', '.join(fields)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    from backend.agent.goals import compute_progress
    return compute_progress(dict(row))

@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: int):
    with db() as conn:
        result = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "deleted"}


@app.get("/alerts/stats")
def alert_stats():
    with db() as conn:
        row = conn.execute(
            """SELECT
                COUNT(*) FILTER (WHERE status='unread')    as unread,
                COUNT(*) FILTER (WHERE status='dismissed') as dismissed,
                COUNT(*) FILTER (WHERE status='snoozed')   as snoozed,
                COUNT(*) FILTER (WHERE severity='high')    as high,
                COUNT(*) FILTER (WHERE severity='medium')  as medium,
                COUNT(*) FILTER (WHERE severity='low')     as low
               FROM alerts"""
        ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# WebSocket — real-time alert push
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Decision-support endpoints
# ---------------------------------------------------------------------------

class AffordabilityRequest(BaseModel):
    amount: float

@app.post("/insights/affordability")
def affordability(req: AffordabilityRequest):
    from backend.agent.insights import estimate_affordability
    result = estimate_affordability(req.amount)
    return {
        "amount": result.amount,
        "affordable": result.affordable,
        "confidence": result.confidence,
        "remaining_budget": result.remaining_budget,
        "avg_monthly_spend": result.avg_monthly_spend,
        "avg_monthly_income": result.avg_monthly_income,
        "this_month_spend": result.this_month_spend,
        "explanation": result.explanation,
    }

@app.get("/insights/optimisation")
def optimisation():
    from backend.agent.insights import generate_optimisation_suggestions
    suggestions = generate_optimisation_suggestions()
    return {"suggestions": [
        {
            "category": s.category,
            "current_avg": s.current_avg,
            "benchmark_pct": s.benchmark_pct,
            "suggested_target": s.suggested_target,
            "potential_saving": s.potential_saving,
            "tip": s.tip,
        }
        for s in suggestions
    ]}

@app.get("/insights/recommendations")
def recommendations():
    from backend.agent.insights import generate_trend_recommendations
    recs = generate_trend_recommendations()
    return {"recommendations": [
        {"type": r.type, "title": r.title, "body": r.body, "severity": r.severity}
        for r in recs
    ]}

@app.post("/transactions/bulk-categorize")
def bulk_categorize(body: dict):
    from backend.processing.categorizer import apply_bulk_correction
    ids = body.get("transaction_ids", [])
    category = body.get("category", "")
    count = apply_bulk_correction(ids, category)
    return {"updated": count}

@app.post("/categorizer/recategorize-misc")
def recategorize_misc():
    from backend.processing.categorizer import recategorize_miscellaneous
    updated = recategorize_miscellaneous()
    return {"updated": updated}

@app.post("/categorizer/recategorize-all")
def recategorize_all_endpoint():
    from backend.processing.categorizer import recategorize_all
    updated = recategorize_all()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Category management endpoints
# ---------------------------------------------------------------------------

class CategoryCreateRequest(BaseModel):
    name: str
    keywords: str = ""

class CategoryUpdateRequest2(BaseModel):
    name: Optional[str] = None
    keywords: Optional[str] = None

@app.get("/categories")
def list_categories():
    with db() as conn:
        rows = conn.execute("SELECT * FROM categories ORDER BY is_system DESC, name ASC").fetchall()
    return {"categories": [dict(r) for r in rows]}

@app.post("/categories")
def create_category(req: CategoryCreateRequest):
    with db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO categories (name, keywords, is_system) VALUES (?, ?, 0)",
                (req.name.strip(), req.keywords.strip()),
            )
            return {"id": cur.lastrowid, "name": req.name}
        except Exception:
            raise HTTPException(status_code=400, detail="Category name already exists")

@app.patch("/categories/{cat_id}")
def update_category_entry(cat_id: int, req: CategoryUpdateRequest2):
    with db() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        new_name = req.name.strip() if req.name is not None else row["name"]
        new_keywords = req.keywords.strip() if req.keywords is not None else row["keywords"]
        conn.execute(
            "UPDATE categories SET name = ?, keywords = ? WHERE id = ?",
            (new_name, new_keywords, cat_id),
        )
    return {"status": "updated"}

@app.delete("/categories/{cat_id}")
def delete_category(cat_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    return {"status": "deleted"}


@app.get("/analytics/monthly-trend")
def monthly_trend():
    with db() as conn:
        rows = conn.execute(
            """SELECT strftime('%Y-%m', date) as month, ROUND(SUM(amount),2) as total
               FROM transactions
               WHERE transaction_type='debit'
               GROUP BY month ORDER BY month DESC LIMIT 12"""
        ).fetchall()
    return {"data": [dict(r) for r in reversed(rows)]}


@app.get("/analytics/category-breakdown")
def category_breakdown():
    with db() as conn:
        rows = conn.execute(
            """SELECT category, ROUND(SUM(amount),2) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category ORDER BY total DESC"""
        ).fetchall()
    return {"data": [dict(r) for r in rows]}


@app.get("/analytics/month-comparison")
def month_comparison():
    with db() as conn:
        rows = conn.execute(
            """SELECT category,
                 ROUND(SUM(CASE WHEN strftime('%Y-%m',date)=strftime('%Y-%m','now') THEN amount ELSE 0 END),2) as this_month,
                 ROUND(SUM(CASE WHEN strftime('%Y-%m',date)=strftime('%Y-%m',date('now','-1 month')) THEN amount ELSE 0 END),2) as last_month
               FROM transactions
               WHERE transaction_type='debit'
                 AND date >= date('now','start of month','-1 month')
               GROUP BY category ORDER BY this_month DESC"""
        ).fetchall()
    return {"data": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Investment endpoints
# ---------------------------------------------------------------------------

@app.get("/investments/summary")
def investments_summary():
    """Portfolio summary: total value by broker + overall."""
    with db() as conn:
        # Latest holdings snapshot per broker (most recent as_of_date per account)
        # Broker names are normalised to lowercase for consistent front-end matching
        portfolio = conn.execute(
            """SELECT lower(broker) as broker, account,
                      SUM(total_value) as total_value,
                      MAX(as_of_date) as as_of_date,
                      COUNT(*) as positions
               FROM investment_holdings h
               WHERE as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               )
               GROUP BY lower(broker), account"""
        ).fetchall()

        total_invested = conn.execute(
            """SELECT COALESCE(SUM(total_value), 0) as total
               FROM investment_transactions
               WHERE transaction_type IN ('buy', 'contribution', 'deposit')"""
        ).fetchone()["total"]

        total_dividends = conn.execute(
            """SELECT COALESCE(SUM(total_value), 0) as total
               FROM investment_transactions
               WHERE transaction_type = 'dividend'"""
        ).fetchone()["total"]

        recent_txs = conn.execute(
            """SELECT * FROM investment_transactions
               ORDER BY date DESC LIMIT 10"""
        ).fetchall()

    portfolio_value = sum(r["total_value"] for r in portfolio)

    with db() as conn:
        # Per-broker unrealized P/L (open) — SUM without COALESCE so null stays null
        # (null means no cost-basis data; 0 means data exists but no gain/loss yet)
        pl_rows = conn.execute(
            """SELECT lower(broker) as broker,
                      SUM(gain_loss)     as gain_loss,
                      SUM(gain_loss_day) as gain_loss_day
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               )
               GROUP BY lower(broker)"""
        ).fetchall()
    pl_map = {r["broker"]: {"gain_loss": r["gain_loss"], "gain_loss_day": r["gain_loss_day"]} for r in pl_rows}

    # Enrich accounts with per-broker P/L — preserve None so frontend can show "—"
    accounts_out = []
    for r in portfolio:
        d = dict(r)
        broker_pl = pl_map.get(r["broker"], {})
        gl  = broker_pl.get("gain_loss")
        gld = broker_pl.get("gain_loss_day")
        d["gain_loss"]     = round(gl, 2)  if gl  is not None else None
        d["gain_loss_day"] = round(gld, 2) if gld is not None else None
        accounts_out.append(d)

    return {
        "portfolio_value": round(portfolio_value, 2),
        "total_invested": round(total_invested, 2),
        "total_dividends": round(total_dividends, 2),
        "accounts": accounts_out,
        "recent_transactions": [dict(r) for r in recent_txs],
    }


@app.get("/investments/holdings")
def investments_holdings(broker: Optional[str] = None, account: Optional[str] = None):
    """Latest holdings per account."""
    filters = []
    params: list = []
    if broker:
        filters.append("h.broker = ?")
        params.append(broker)
    if account:
        filters.append("h.account = ?")
        params.append(account)

    where = ("AND " + " AND ".join(filters)) if filters else ""

    with db() as conn:
        rows = conn.execute(
            f"""SELECT h.*
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               )
               {where}
               ORDER BY h.total_value DESC""",
            params,
        ).fetchall()

    return {"holdings": [dict(r) for r in rows]}


@app.get("/investments/transactions")
def investments_transactions(
    page: int = 1,
    page_size: int = 50,
    broker: Optional[str] = None,
    transaction_type: Optional[str] = None,
):
    filters = ["1=1"]
    params: list = []
    if broker:
        filters.append("broker = ?")
        params.append(broker)
    if transaction_type:
        filters.append("transaction_type = ?")
        params.append(transaction_type)

    where = " AND ".join(filters)
    offset = (page - 1) * page_size

    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM investment_transactions WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM investment_transactions WHERE {where}
                ORDER BY date DESC LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "transactions": [dict(r) for r in rows],
    }


@app.post("/investments/upload")
async def upload_investment_file(file: UploadFile = File(...)):
    """Manual upload for investment statement PDFs. Always force-updates holdings."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    dest = STATEMENTS_DIR / file.filename
    dest.write_bytes(await file.read())
    from backend.investments.pipeline import ingest_investment_file
    result = ingest_investment_file(dest, force=True)
    return result


@app.post("/investments/reingest")
def reingest_investment_files():
    """Re-parse all investment PDFs in the statements dir and upsert holdings/transactions."""
    from backend.investments.pipeline import ingest_investment_file
    from backend.investments.parser import is_investment_pdf
    results = []
    for pdf in sorted(STATEMENTS_DIR.glob("*.pdf")):
        try:
            if is_investment_pdf(pdf):
                r = ingest_investment_file(pdf, force=True)
                results.append(r)
        except Exception as exc:
            results.append({"file": pdf.name, "status": "error", "reason": str(exc)})
    return {"reingested": len(results), "results": results}


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# WhatsApp webhook (REA Communication Agent posts here)
# ---------------------------------------------------------------------------

class WhatsAppQuery(BaseModel):
    query: str
    sender: Optional[str] = None
    history: Optional[list] = None

@app.post("/whatsapp/query")
def whatsapp_query(req: WhatsAppQuery):
    from backend.agent.engine import handle_finance_command
    result = handle_finance_command(req.query, history=req.history or [])
    return {"answer": result.get("answer", ""), "low_confidence": result.get("low_confidence", False)}


# ---------------------------------------------------------------------------
# Teller
# ---------------------------------------------------------------------------

class TellerEnrollmentRequest(BaseModel):
    enrollment_id: str
    access_token: str
    institution: str

@app.post("/teller/enroll")
def teller_enroll(req: TellerEnrollmentRequest):
    """Save a new Teller enrollment (called after Teller Link success)."""
    with db() as conn:
        conn.execute(
            """INSERT INTO teller_enrollments (enrollment_id, access_token, institution)
               VALUES (?, ?, ?)
               ON CONFLICT(enrollment_id) DO UPDATE SET
                 access_token = excluded.access_token,
                 status = 'active'""",
            (req.enrollment_id, req.access_token, req.institution),
        )
    # Kick off an immediate sync in the background
    from backend.teller.sync import sync_enrollment
    import threading
    threading.Thread(
        target=sync_enrollment,
        args=(req.enrollment_id, req.access_token, req.institution),
        daemon=True,
    ).start()
    return {"status": "enrolled", "enrollment_id": req.enrollment_id}


@app.get("/teller/enrollments")
def teller_enrollments():
    """List all connected Teller institutions with account counts and balances."""
    with db() as conn:
        enrollments = conn.execute(
            "SELECT * FROM teller_enrollments ORDER BY created_at DESC"
        ).fetchall()
        accounts = conn.execute(
            "SELECT * FROM teller_accounts ORDER BY institution, name"
        ).fetchall()

    acc_by_enrollment: dict = {}
    for a in accounts:
        acc_by_enrollment.setdefault(a["enrollment_id"], []).append(dict(a))

    return {
        "enrollments": [
            {**dict(e), "accounts": acc_by_enrollment.get(e["enrollment_id"], [])}
            for e in enrollments
        ]
    }


@app.delete("/teller/enrollments/{enrollment_id}")
def teller_disconnect(enrollment_id: str):
    """Mark an enrollment inactive (disconnect institution)."""
    with db() as conn:
        conn.execute(
            "UPDATE teller_enrollments SET status = 'inactive' WHERE enrollment_id = ?",
            (enrollment_id,),
        )
    return {"status": "disconnected"}


@app.post("/teller/sync")
def teller_sync_now():
    """Manually trigger a Teller sync for all active enrollments."""
    from backend.teller.sync import sync_all
    result = sync_all()
    return result


@app.post("/teller/resync")
def teller_resync():
    """Delete all Teller-sourced transactions and re-import from scratch."""
    try:
        from backend.storage.database import get_connection
        conn = get_connection()
        conn.execute("PRAGMA foreign_keys=OFF")
        deleted = conn.execute(
            "DELETE FROM transactions WHERE source_file LIKE 'teller:%'"
        ).rowcount
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()
        from backend.teller.sync import sync_all
        result = sync_all()
        result["deleted"] = deleted
        return result
    except Exception as exc:
        import logging, traceback
        logging.getLogger(__name__).error("[TellerResync] Failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Teller resync failed: {exc}")


# ---------------------------------------------------------------------------
# Plaid
# ---------------------------------------------------------------------------

class PlaidExchangeRequest(BaseModel):
    public_token:   str
    institution_id: str
    institution:    str


@app.get("/plaid/link-token")
def plaid_link_token():
    """Create and return a Plaid Link token for the frontend."""
    from backend.plaid.client import create_link_token
    try:
        token = create_link_token()
        return {"link_token": token}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/plaid/exchange")
def plaid_exchange(req: PlaidExchangeRequest):
    """Exchange a Plaid public_token for an access_token, store the item, kick off sync."""
    from backend.plaid.client import exchange_public_token
    try:
        result = exchange_public_token(req.public_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    item_id      = result["item_id"]
    access_token = result["access_token"]
    institution  = req.institution

    with db() as conn:
        conn.execute(
            """INSERT INTO plaid_items (item_id, access_token, institution_id, institution)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(item_id) DO UPDATE SET
                 access_token = excluded.access_token,
                 status = 'active'""",
            (item_id, access_token, req.institution_id, institution),
        )

    # Kick off immediate sync in background thread
    from backend.plaid.sync import sync_item
    import threading
    threading.Thread(
        target=sync_item,
        args=(item_id, access_token, institution),
        daemon=True,
    ).start()

    return {"status": "connected", "item_id": item_id}


@app.get("/plaid/items")
def plaid_items():
    """List all connected Plaid items with their accounts."""
    with db() as conn:
        items    = conn.execute("SELECT * FROM plaid_items ORDER BY created_at DESC").fetchall()
        accounts = conn.execute("SELECT * FROM plaid_accounts ORDER BY institution, name").fetchall()

    accts_by_item: dict = {}
    for a in accounts:
        accts_by_item.setdefault(a["item_id"], []).append(dict(a))

    return {
        "items": [
            {**dict(i), "accounts": accts_by_item.get(i["item_id"], [])}
            for i in items
        ]
    }


@app.delete("/plaid/items/{item_id}")
def plaid_disconnect(item_id: str):
    """Disconnect a Plaid item (revoke access token + mark inactive)."""
    with db() as conn:
        row = conn.execute(
            "SELECT access_token FROM plaid_items WHERE item_id = ?", (item_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        conn.execute(
            "UPDATE plaid_items SET status = 'inactive' WHERE item_id = ?", (item_id,)
        )
    try:
        from backend.plaid.client import remove_item
        remove_item(row["access_token"])
    except Exception as exc:
        logger.warning("[Plaid] remove_item failed (non-fatal): %s", exc)
    return {"status": "disconnected"}


@app.post("/plaid/sync")
def plaid_sync_now():
    """Manually trigger a Plaid sync for all active items."""
    from backend.plaid.sync import sync_all
    return sync_all()


@app.post("/plaid/resync")
def plaid_resync():
    """Delete all Plaid-sourced transactions and re-import from scratch."""
    try:
        from backend.storage.database import get_connection
        conn = get_connection()
        conn.execute("PRAGMA foreign_keys=OFF")
        deleted = conn.execute(
            "DELETE FROM transactions WHERE source_file LIKE 'plaid:%'"
        ).rowcount
        conn.execute("UPDATE plaid_items SET cursor = NULL WHERE status = 'active'")
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()
        from backend.plaid.sync import sync_all
        result = sync_all()
        result["deleted"] = deleted
        return result
    except Exception as exc:
        import logging, traceback
        logging.getLogger(__name__).error("[PlaidResync] Failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Plaid resync failed: {exc}")


@app.post("/categorizer/fix-invalid")
def fix_invalid_categories():
    """
    Find transactions whose category is not in the categories table and
    re-run categorization on them using current keyword + learned rules.
    """
    from backend.processing.categorizer import categorize
    with db() as conn:
        valid = {r["name"] for r in conn.execute("SELECT name FROM categories").fetchall()}
        rows = conn.execute(
            "SELECT id, description, category FROM transactions WHERE category_source = 'auto'"
        ).fetchall()
        updated = 0
        for row in rows:
            if row["category"] not in valid:
                new_cat = categorize(row["description"])
                conn.execute(
                    "UPDATE transactions SET category = ? WHERE id = ?",
                    (new_cat, row["id"]),
                )
                updated += 1
    return {"updated": updated}
