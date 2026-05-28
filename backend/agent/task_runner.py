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
    summary = (
        f"Spending update: ${delta:,.2f} new spend ({row['count']} transactions).\n"
        f"Month-to-date total: ${current:,.2f}\n"
        f"Top categories: {top}"
    )

    return {"current": current, "previous": prev, "delta": delta, "summary": summary}


def _execute_monitor_investments(params: dict, snapshot: dict) -> dict:
    """Report on current investment performance vs snapshot."""
    from backend.storage.database import db

    with db() as conn:
        holdings = conn.execute(
            """SELECT ticker, name, total_value, gain_loss, gain_loss_pct
               FROM investment_holdings h
               WHERE as_of_date = (SELECT MAX(as_of_date) FROM investment_holdings)
               ORDER BY gain_loss ASC"""
        ).fetchall()

    if not holdings:
        return {"summary": "No investment holdings data available yet."}

    losers = [r for r in holdings if (r["gain_loss"] or 0) < 0]
    gainers = [r for r in holdings if (r["gain_loss"] or 0) > 0]

    lines = ["Investment snapshot:"]
    if losers:
        lines.append("\n📉 Biggest losers:")
        for r in losers[:3]:
            pct = f"{r['gain_loss_pct']:.1f}%" if r["gain_loss_pct"] else "N/A"
            lines.append(f"  {r['ticker'] or r['name']}: ${r['gain_loss']:,.2f} ({pct})")
    if gainers:
        lines.append("\n📈 Biggest gainers:")
        for r in reversed(gainers[-3:]):
            pct = f"{r['gain_loss_pct']:.1f}%" if r["gain_loss_pct"] else "N/A"
            lines.append(f"  {r['ticker'] or r['name']}: +${r['gain_loss']:,.2f} ({pct})")

    total_value = sum(r["total_value"] for r in holdings)
    lines.append(f"\nTotal portfolio value: ${total_value:,.2f}")

    return {"summary": "\n".join(lines), "holdings_count": len(holdings)}


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
    """Check current account balances."""
    from backend.storage.database import db

    with db() as conn:
        accounts = conn.execute(
            """SELECT ta.institution, ta.name, ta.type, ta.balance_ledger, ta.last_synced_at
               FROM teller_accounts ta
               JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
               WHERE te.status = 'active'
               ORDER BY ta.institution, ta.type"""
        ).fetchall()

    if not accounts:
        return {"summary": "No connected accounts found."}

    lines = ["💰 Account Balances:"]
    total = 0.0
    for a in accounts:
        bal = a["balance_ledger"] or 0
        total += bal
        lines.append(f"  {a['institution']} {a['name']}: ${bal:,.2f}")
    lines.append(f"\nTotal: ${total:,.2f}")

    return {"summary": "\n".join(lines), "total": total}


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
