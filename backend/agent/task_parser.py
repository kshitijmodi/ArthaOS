"""
Task parser — converts natural language finance commands into structured scheduled tasks.

Examples:
  "track my dining spend for 3 days"
  → {task_type: "track_category", params: {category: "Dining"}, duration_days: 3}

  "monitor investments for 1 hour, tell me biggest losers"
  → {task_type: "monitor_investments", params: {metric: "loss"}, duration_hours: 1}

  "alert me if I spend more than $100 on shopping today"
  → {task_type: "threshold_alert", params: {category: "Shopping", threshold: 100}, duration_days: 1}

  "summarize my spending every morning at 9am"
  → {task_type: "daily_summary", params: {time: "09:00"}, repeat_interval: "daily"}
"""
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_TASK_PARSE_PROMPT = """You are a financial task parser. The current date/time is: {current_datetime} (UTC).

Convert the user's natural language request into a structured JSON task.

Available task types:
- track_category: Track spending in a specific category over N days
- track_total: Track total spending (all categories) over N days
- monitor_investments: Check investment portfolio performance
- threshold_alert: Alert if spend in a category exceeds a dollar amount
- daily_summary: Send a daily spending summary
- balance_check: Check account balances at a scheduled time
- predict_savings: Predict how much the user will save by month end
- investment_advice: Analyze portfolio + spending and give investment recommendations
- expense_report: Generate a comprehensive spending report for a period
- custom: Any other financial monitoring or analysis task

Return ONLY valid JSON with these fields:
{{
  "task_type": "<type>",
  "description": "<human readable one-line description>",
  "params": {{
    "category": "<category name if applicable, else null>",
    "threshold": <dollar amount if applicable, else null>,
    "metric": "<what to measure: spend/loss/gain/balance>",
    "fire_at_time": "<HH:MM 24-hour if user says 'at X pm/am', else null>",
    "report_period": "<this month/last month/this week if mentioned, else null>",
    "summary_type": "<spending/investments/alerts/all>"
  }},
  "duration_hours": <hours until task fires if relative like 'in 3 hours', else null>,
  "duration_days": <days until task fires if relative like 'in 2 days'/'for next week', else null>,
  "repeat_interval": "<daily/weekly/hourly or null for one-shot>"
}}

Time rules (current time is {current_datetime} UTC):
- "at 9pm" or "at 21:00" → fire_at_time: "21:00", duration_hours: null
- "at 9am tomorrow" → fire_at_time: "09:00", duration_days: 1
- "in 2 hours" → duration_hours: 2
- "tomorrow morning" → fire_at_time: "09:00", duration_days: 1
- "every day at 9am" → fire_at_time: "09:00", repeat_interval: "daily"
- "for the next 7 days" → duration_days: 7
- "this week" or "next week" → duration_days: 7
- "by month end" or "end of month" → duration_days: days remaining in current month
- If no time given for one-shot tasks, default: duration_hours: 1

Category mapping: Groceries, Dining, Travel, Shopping, Utilities, Subscriptions, Insurance, EMIs, Rent, Healthcare, Education, Investments, Income, Miscellaneous

User request: {query}"""


def parse_task(query: str) -> dict | None:
    """
    Parse a natural language task request into a structured task dict.
    Returns None if the query doesn't look like a task request.
    """
    try:
        from backend.rag.llm import complete
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        prompt = _TASK_PARSE_PROMPT.replace("{current_datetime}", now_str).replace("{query}", query)
        raw = complete(
            prompt,
            max_tokens=400,
            system="You are a JSON-only response bot. Return only valid JSON, no explanation.",
        )
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        task = json.loads(raw)
        return task
    except Exception as exc:
        logger.warning("[TaskParser] Failed to parse task from %r: %s", query, exc)
        return None


def build_scheduled_task(parsed: dict, initiated_by: str = "user") -> dict:
    """
    Convert parsed task dict into a scheduled_tasks DB row dict.
    Handles absolute times ("at 9pm" → fire_at_time) and relative durations.
    """
    now = datetime.utcnow()
    params = parsed.get("params", {})
    fire_at_time = params.get("fire_at_time")  # "HH:MM" in UTC (user said "at 9pm")

    if fire_at_time:
        try:
            h, m = map(int, fire_at_time.split(":"))
            fire_at = now.replace(hour=h, minute=m, second=0, microsecond=0)
            # If the time has already passed today, schedule for tomorrow
            extra_days = parsed.get("duration_days") or 0
            if fire_at <= now or extra_days > 0:
                fire_at += timedelta(days=max(1, extra_days))
        except Exception:
            fire_at = now + timedelta(hours=1)
    else:
        duration_hours = parsed.get("duration_hours") or 0
        duration_days = parsed.get("duration_days") or 0

        if duration_hours:
            fire_at = now + timedelta(hours=duration_hours)
        elif duration_days:
            fire_at = now + timedelta(days=duration_days)
        else:
            fire_at = now + timedelta(hours=1)  # default: in 1 hour

    # Capture snapshot of current state for comparison at fire time
    snapshot = _capture_snapshot(parsed)

    return {
        "task_type": parsed.get("task_type", "custom"),
        "description": parsed.get("description", "Custom task"),
        "params": json.dumps(parsed.get("params", {})),
        "fire_at": fire_at.strftime("%Y-%m-%d %H:%M:%S"),
        "repeat_interval": parsed.get("repeat_interval"),
        "status": "pending",
        "initiated_by": initiated_by,
        "snapshot": json.dumps(snapshot),
    }


def _capture_snapshot(parsed: dict) -> dict:
    """Capture current financial state relevant to the task for later comparison."""
    snapshot = {"captured_at": datetime.utcnow().isoformat()}
    try:
        from backend.storage.database import db
        params = parsed.get("params", {})
        category = params.get("category")
        task_type = parsed.get("task_type", "")

        with db() as conn:
            if category and task_type in ("track_category", "threshold_alert"):
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) as total
                       FROM transactions
                       WHERE transaction_type='debit'
                         AND category = ?
                         AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')""",
                    (category,),
                ).fetchone()
                snapshot["category_mtd"] = row["total"]
                snapshot["category"] = category

            if task_type in ("track_total", "daily_summary"):
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) as total
                       FROM transactions
                       WHERE transaction_type='debit'
                         AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
                ).fetchone()
                snapshot["total_mtd"] = row["total"]

            if task_type == "monitor_investments":
                holdings = conn.execute(
                    """SELECT ticker, name, total_value, gain_loss, gain_loss_pct
                       FROM investment_holdings h
                       WHERE as_of_date = (SELECT MAX(as_of_date) FROM investment_holdings)
                       ORDER BY gain_loss ASC"""
                ).fetchall()
                snapshot["holdings"] = [dict(r) for r in holdings]

            if task_type == "balance_check":
                accounts = conn.execute(
                    """SELECT ta.institution, ta.name, ta.balance_ledger
                       FROM teller_accounts ta
                       JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
                       WHERE te.status = 'active'"""
                ).fetchall()
                snapshot["balances"] = [dict(a) for a in accounts]

    except Exception as exc:
        logger.warning("[TaskParser] Snapshot capture failed: %s", exc)

    return snapshot


def save_task(task_row: dict) -> int:
    """Insert a scheduled task into the DB and return its ID."""
    from backend.storage.database import db
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_tasks
               (task_type, description, params, fire_at, repeat_interval,
                status, initiated_by, snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_row["task_type"],
                task_row["description"],
                task_row["params"],
                task_row["fire_at"],
                task_row.get("repeat_interval"),
                task_row["status"],
                task_row["initiated_by"],
                task_row.get("snapshot"),
            ),
        )
        return cur.lastrowid
