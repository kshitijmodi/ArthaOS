"""
Task runner — executes pending scheduled_tasks whose fire_at has passed.
Called by the scheduler every 30 minutes.
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def run_due_tasks():
    """Find all pending tasks that are due and execute them."""
    from backend.storage.database import db

    with db() as conn:
        due = conn.execute(
            """SELECT * FROM scheduled_tasks
               WHERE status = 'pending'
                 AND fire_at <= datetime('now')
               ORDER BY fire_at ASC"""
        ).fetchall()

    if not due:
        return

    logger.info("[TaskRunner] %d task(s) due", len(due))

    for row in due:
        task = dict(row)
        _execute_task(task)


def _execute_task(task: dict):
    """Execute a single task and send results via WhatsApp."""
    from backend.storage.database import db

    task_id = task["id"]
    logger.info("[TaskRunner] Executing task #%d: %s", task_id, task["description"])

    # Mark as running
    with db() as conn:
        conn.execute(
            "UPDATE scheduled_tasks SET status='running' WHERE id=?", (task_id,)
        )

    try:
        result = _run_task_logic(task)
        result_json = json.dumps(result)

        with db() as conn:
            if task.get("repeat_interval"):
                # Reschedule for next firing
                next_fire = _next_fire(task["fire_at"], task["repeat_interval"])
                conn.execute(
                    """UPDATE scheduled_tasks
                       SET status='pending', fire_at=?, result=?, completed_at=datetime('now')
                       WHERE id=?""",
                    (next_fire, result_json, task_id),
                )
            else:
                conn.execute(
                    """UPDATE scheduled_tasks
                       SET status='completed', result=?, completed_at=datetime('now')
                       WHERE id=?""",
                    (result_json, task_id),
                )

        # Send WhatsApp notification
        _notify_whatsapp(task, result)

    except Exception as exc:
        logger.error("[TaskRunner] Task #%d failed: %s", task_id, exc)
        with db() as conn:
            conn.execute(
                "UPDATE scheduled_tasks SET status='failed', result=? WHERE id=?",
                (json.dumps({"error": str(exc)}), task_id),
            )


def _run_task_logic(task: dict) -> dict:
    """Execute the task and return a result dict."""
    task_type = task["task_type"]
    params = json.loads(task.get("params") or "{}")
    snapshot = json.loads(task.get("snapshot") or "{}")

    if task_type == "track_category":
        return _execute_track_category(params, snapshot)
    elif task_type == "track_total":
        return _execute_track_total(params, snapshot)
    elif task_type == "monitor_investments":
        return _execute_monitor_investments(params, snapshot)
    elif task_type == "threshold_alert":
        return _execute_threshold_alert(params, snapshot)
    elif task_type == "daily_summary":
        return _execute_daily_summary(params, snapshot)
    elif task_type == "balance_check":
        return _execute_balance_check(params, snapshot)
    elif task_type == "predict_savings":
        return _execute_predict_savings(params, snapshot)
    elif task_type == "investment_advice":
        return _execute_investment_advice(params, snapshot)
    elif task_type == "expense_report":
        return _execute_expense_report(params, snapshot)
    else:
        return _execute_custom(task, params, snapshot)


def _execute_track_category(params: dict, snapshot: dict) -> dict:
    """Compare current category spend vs snapshot."""
    from backend.storage.database import db
    category = params.get("category", "")

    with db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count
               FROM transactions
               WHERE transaction_type='debit'
                 AND category = ?
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')""",
            (category,),
        ).fetchone()

    current = row["total"]
    count = row["count"]
    prev = snapshot.get("category_mtd", 0)
    delta = current - prev

    if delta > 0:
        summary = f"You spent ${delta:,.2f} on {category} since tracking started (${current:,.2f} total this month, {count} transactions)."
    else:
        summary = f"No new {category} spending since tracking started. Total this month: ${current:,.2f}."

    return {"category": category, "current": current, "previous": prev, "delta": delta, "summary": summary}


def _execute_track_total(params: dict, snapshot: dict) -> dict:
    """Compare total spend vs snapshot."""
    from backend.storage.database import db

    with db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()

        # Top categories in period
        cats = conn.execute(
            """SELECT category, SUM(amount) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category ORDER BY total DESC LIMIT 5"""
        ).fetchall()

    current = row["total"]
    prev = snapshot.get("total_mtd", 0)
    delta = current - prev

    top = ", ".join(f"{r['category']} (${r['total']:,.0f})" for r in cats)
    if delta > 0:
        spend_line = f"New spend since last check: ${delta:,.2f} ({row['count']} transactions)."
    else:
        spend_line = f"No new spend since last check ({row['count']} transactions this month total)."
    summary = (
        f"{spend_line}\n"
        f"Month-to-date total: ${current:,.2f}\n"
        f"Top categories: {top}"
    )

    return {"current": current, "previous": prev, "delta": delta, "summary": summary}


def _execute_monitor_investments(params: dict, snapshot: dict) -> dict:
    """Report investment totals by broker with grand total."""
    from backend.storage.database import db

    with db() as conn:
        brokers = conn.execute(
            """SELECT broker, account, SUM(total_value) as total
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               )
               GROUP BY broker, account
               ORDER BY total DESC"""
        ).fetchall()

    if not brokers:
        return {"summary": "No investment holdings data available yet."}

    lines = ["💼 *Investment Portfolio*\n"]
    grand_total = 0.0
    for r in brokers:
        val = r["total"] or 0.0
        grand_total += val
        lines.append(f"  {r['broker']} — {r['account']}: ${val:,.2f}")

    lines.append(f"\n*Total: ${grand_total:,.2f}*")

    return {"summary": "\n".join(lines), "total": grand_total}


def _execute_threshold_alert(params: dict, snapshot: dict) -> dict:
    """Check if spend in a category exceeded the threshold."""
    from backend.storage.database import db
    category = params.get("category", "")
    threshold = params.get("threshold", 0)

    with db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND category = ?
                 AND date >= date('now', 'start of day')""",
            (category,),
        ).fetchone()

    current = row["total"]
    exceeded = current >= threshold

    if exceeded:
        summary = f"🚨 Threshold exceeded! {category} spend today: ${current:,.2f} (limit: ${threshold:,.2f})"
    else:
        remaining = threshold - current
        summary = f"✅ {category} spend today: ${current:,.2f} / ${threshold:,.2f} limit. ${remaining:,.2f} remaining."

    return {"category": category, "current": current, "threshold": threshold,
            "exceeded": exceeded, "summary": summary}


def _execute_daily_summary(params: dict, snapshot: dict) -> dict:
    """Send a daily spending summary."""
    from backend.storage.database import db

    with db() as conn:
        mtd = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total
               FROM transactions WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()["total"]

        today_spend = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total
               FROM transactions WHERE transaction_type='debit'
                 AND date = date('now')"""
        ).fetchone()["total"]

        top_cats = conn.execute(
            """SELECT category, SUM(amount) as total
               FROM transactions WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category ORDER BY total DESC LIMIT 3"""
        ).fetchall()

        unread_alerts = conn.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE status='unread'"
        ).fetchone()["c"]

    top = ", ".join(f"{r['category']} (${r['total']:,.0f})" for r in top_cats)
    summary = (
        f"📊 Daily Summary\n\n"
        f"Today: ${today_spend:,.2f}\n"
        f"Month-to-date: ${mtd:,.2f}\n"
        f"Top categories: {top}\n"
        f"Unread alerts: {unread_alerts}"
    )

    return {"today": today_spend, "mtd": mtd, "summary": summary}


def _execute_balance_check(params: dict, snapshot: dict) -> dict:
    """Check current account balances — Teller (active) + Plaid."""
    from backend.storage.database import db

    with db() as conn:
        teller = conn.execute(
            """SELECT ta.institution, ta.name, ta.type,
                      COALESCE(ta.balance_available, ta.balance_ledger, 0) as balance
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
               ORDER BY ta.institution, ta.type"""
        ).fetchall()
        plaid = conn.execute(
            """SELECT institution, name, type,
                      COALESCE(balance_available, balance_current, 0) as balance
               FROM plaid_accounts
               WHERE lower(type) IN ('depository','checking','savings')
               ORDER BY institution, name"""
        ).fetchall()

    all_accounts = [dict(r) for r in teller] + [dict(r) for r in plaid]
    if not all_accounts:
        return {"summary": "No bank accounts found. Check your account connections."}

    lines = ["💰 *Account Balances:*"]
    bank_total = 0.0
    for a in all_accounts:
        if a["type"] in ("depository", "checking", "savings"):
            bank_total += a["balance"]
            lines.append(f"  {a['institution']} — {a['name']}: ${a['balance']:,.2f}")

    lines.append(f"\n*Total bank balance: ${bank_total:,.2f}*")
    return {"summary": "\n".join(lines), "total": bank_total}


def _execute_predict_savings(params: dict, snapshot: dict) -> dict:
    """Predict month-end savings based on current spend pace."""
    from backend.storage.database import db
    from backend.rag.llm import complete
    from datetime import date
    import calendar

    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = today.day
    days_remaining = days_in_month - days_elapsed

    with db() as conn:
        spend_rows = conn.execute(
            """SELECT category, ROUND(SUM(amount),2) as total
               FROM transactions WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category ORDER BY total DESC"""
        ).fetchall()
        income_this_month = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as total FROM transactions
               WHERE transaction_type='credit' AND category='Income'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()["total"]
        avg_income_3m = conn.execute(
            """SELECT COALESCE(AVG(m_total), 0) as avg
               FROM (SELECT strftime('%Y-%m', date) as m, SUM(amount) as m_total
                     FROM transactions WHERE transaction_type='credit' AND category='Income'
                       AND date >= date('now', '-90 days')
                     GROUP BY m)"""
        ).fetchone()["avg"]
        bank_balance = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(balance_available, balance_current, 0)), 0) as total
               FROM plaid_accounts WHERE lower(type) IN ('depository','checking','savings')"""
        ).fetchone()["total"]
        # Add active Teller bank balance
        teller_bank = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(ta.balance_available, ta.balance_ledger, 0)), 0) as total
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
                 AND lower(ta.type) IN ('depository','checking','savings')"""
        ).fetchone()["total"]
        bank_balance += teller_bank

    total_spend = sum(r["total"] for r in spend_rows)
    daily_burn = total_spend / max(days_elapsed, 1)
    projected_spend = daily_burn * days_in_month
    expected_income = income_this_month if income_this_month > 0 else avg_income_3m

    cat_lines = "\n".join(f"  {r['category']}: ${r['total']:,.2f}" for r in spend_rows[:8])
    prompt = f"""Predict month-end savings for a US-based user. Today is day {days_elapsed} of {days_in_month} ({days_remaining} days remaining this month).

Spending so far: ${total_spend:,.2f} (${daily_burn:,.2f}/day average)
Projected total monthly spend: ${projected_spend:,.2f}
Income this month: ${income_this_month:,.2f} (3-month avg: ${avg_income_3m:,.2f})
Current bank balance: ${bank_balance:,.2f}

Top spending categories:
{cat_lines}

Provide a concise savings forecast and 2-3 practical tips to improve it. Format as a WhatsApp message with dollar amounts."""

    response = complete(prompt, max_tokens=400)
    return {"summary": response}


def _execute_investment_advice(params: dict, snapshot: dict) -> dict:
    """Analyze portfolio + spending patterns and provide investment recommendations."""
    from backend.storage.database import db
    from backend.rag.llm import complete

    with db() as conn:
        holdings = conn.execute(
            """SELECT broker, ticker, name, total_value, gain_loss
               FROM investment_holdings h
               WHERE h.as_of_date = (
                   SELECT MAX(as_of_date) FROM investment_holdings h2
                   WHERE h2.broker = h.broker AND h2.account = h.account
               )
               ORDER BY broker, total_value DESC"""
        ).fetchall()
        spend = conn.execute(
            """SELECT category, ROUND(SUM(amount),2) as total
               FROM transactions WHERE transaction_type='debit'
                 AND date >= date('now', '-60 days')
               GROUP BY category ORDER BY total DESC LIMIT 8"""
        ).fetchall()
        bank = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(balance_available, balance_current, 0)), 0) as total
               FROM plaid_accounts WHERE lower(type) IN ('depository','checking','savings')"""
        ).fetchone()["total"]
        income = conn.execute(
            """SELECT COALESCE(AVG(m_total), 0) as avg
               FROM (SELECT strftime('%Y-%m', date) as m, SUM(amount) as m_total
                     FROM transactions WHERE transaction_type='credit' AND category='Income'
                       AND date >= date('now', '-90 days')
                     GROUP BY m)"""
        ).fetchone()["avg"]

    portfolio_total = sum(r["total_value"] or 0 for r in holdings)
    holdings_text = "\n".join(f"  {r['broker']} {r['ticker'] or r['name']}: ${(r['total_value'] or 0):,.2f}" for r in holdings[:10])
    spend_text = "\n".join(f"  {r['category']}: ${r['total']:,.2f}" for r in spend)

    prompt = f"""Provide investment advice for a US-based user based on their financial data:

Portfolio (${portfolio_total:,.2f} total):
{holdings_text or 'No holdings data available'}

Recent spending (last 60 days):
{spend_text}

Bank balance: ${bank:,.2f}
Average monthly income: ${income:,.2f}

Give specific, actionable investment insights. Cover: diversification, cash deployment, spending optimization for investing. 3-4 bullet points. Format as WhatsApp message with $ amounts."""

    response = complete(prompt, max_tokens=500)
    return {"summary": response}


def _execute_expense_report(params: dict, snapshot: dict) -> dict:
    """Generate a comprehensive spending report."""
    from backend.storage.database import db

    period = params.get("report_period", "this month")
    if "last month" in period:
        period_sql = "strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))"
        period_label = "Last month"
    elif "this week" in period:
        period_sql = "date >= date('now', '-7 days')"
        period_label = "This week"
    else:
        period_sql = "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
        period_label = "This month"

    with db() as conn:
        cats = conn.execute(
            f"""SELECT category, ROUND(SUM(amount),2) as total, COUNT(*) as cnt
                FROM transactions WHERE transaction_type='debit' AND {period_sql}
                GROUP BY category ORDER BY total DESC"""
        ).fetchall()
        top5 = conn.execute(
            f"""SELECT date, description, amount, category
                FROM transactions WHERE transaction_type='debit' AND {period_sql}
                ORDER BY amount DESC LIMIT 5"""
        ).fetchall()

    if not cats:
        return {"summary": f"No expense data for {period_label.lower()}."}

    total = sum(r["total"] for r in cats)
    cat_lines = "\n".join(f"  {r['category']}: ${r['total']:,.2f} ({r['cnt']} txns)" for r in cats)
    top_lines = "\n".join(f"  ${r['amount']:,.2f} — {r['description'][:35]} [{r['category']}]" for r in top5)

    summary = (
        f"📊 *Expense Report — {period_label}*\n\n"
        f"*Total: ${total:,.2f}*\n\n"
        f"*By Category:*\n{cat_lines}\n\n"
        f"*Top 5 Charges:*\n{top_lines}"
    )
    return {"summary": summary}


def _execute_custom(task: dict, params: dict, snapshot: dict) -> dict:
    """For custom tasks, use the LLM to generate a summary."""
    try:
        from backend.rag.pipeline import query as rag_query
        result = rag_query(task["description"])
        return {"summary": result.answer}
    except Exception:
        return {"summary": f"Task completed: {task['description']}"}


def _next_fire(current_fire: str, interval: str) -> str:
    """Compute next fire time for repeating tasks."""
    from datetime import timedelta
    try:
        dt = datetime.strptime(current_fire, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        dt = datetime.utcnow()

    if interval == "hourly":
        dt += timedelta(hours=1)
    elif interval == "30min":
        dt += timedelta(minutes=30)
    elif interval == "daily":
        dt += timedelta(days=1)
    elif interval == "weekly":
        dt += timedelta(weeks=1)
    else:
        dt += timedelta(days=1)

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _notify_whatsapp(task: dict, result: dict):
    """Send task result to WhatsApp via REA."""
    import os
    import asyncio
    rea_url = os.getenv("REA_WEBHOOK_URL", "")
    if not rea_url:
        return

    summary = result.get("summary", "Task completed.")
    message = f"⏰ *Task Report* — {task['description']}\n\n{summary}"

    async def _send():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(rea_url, json={
                    "type": "arthaos_alert",
                    "message": message,
                })
            logger.info("[TaskRunner] Result sent to WhatsApp for task #%d", task["id"])
        except Exception as exc:
            logger.warning("[TaskRunner] WhatsApp notify failed: %s", exc)

    try:
        asyncio.run(_send())
    except RuntimeError:
        # Already in an event loop
        import threading
        threading.Thread(target=lambda: asyncio.run(_send()), daemon=True).start()
