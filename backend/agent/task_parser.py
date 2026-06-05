"""
Task parser — converts natural language scheduling requests into structured tasks.

Architecture: query_replay is the default task type.
Instead of classifying queries into predefined types and running hardcoded executors,
we strip the time phrase, store the original query, and replay it through
handle_finance_command() at fire time. This means any query that works in real-time
automatically works when scheduled — no type classification needed.

Special executors (threshold_alert, track_category, track_total) are kept only for
tasks that require snapshot comparison or threshold checking over time.
"""
import json
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Time extraction ──────────────────────────────────────────────────────────

def _et_utc_offset() -> int:
    """EDT (summer) = UTC-4, EST (winter) = UTC-5."""
    month = datetime.utcnow().month
    return -4 if 3 <= month <= 10 else -5


def _extract_local_time(query: str) -> str | None:
    """Extract clock time from query and return HH:MM (24h ET). E.g. 'at 4:18pm' → '16:18'."""
    m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", query, re.IGNORECASE)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2)) if m.group(2) else 0
    mer = m.group(3).lower()
    if mer == "pm" and hour != 12:
        hour += 12
    elif mer == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _detect_repeat_interval(query: str) -> str | None:
    q = query.lower()
    if re.search(r"\bevery\s+(?:day|daily|morning|night|evening)\b", q):
        return "daily"
    if re.search(r"\bevery\s+(?:week|weekly|monday|tuesday|wednesday|thursday|friday)\b", q):
        return "weekly"
    if re.search(r"\bevery\s+hour\b|\bhourly\b", q):
        return "hourly"
    return None


# Scheduling phrases to strip from the query before storing for replay
_TIME_STRIP_PATTERNS = [
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",        # "at 5pm", "at 12:27am"
    r"\btomorrow\b",
    r"\bin\s+\d+\s*(?:hour|minute|min|day|week)s?\b",   # "in 2 hours"
    r"\bfor\s+(?:the\s+)?next\s+\d+\s*(?:day|week|hour)s?\b",  # "for the next 7 days"
    r"\bevery\s+(?:day|morning|night|hour|week|monday|tuesday|wednesday|thursday|friday)\b",
    r"\bby\s+month\s*end\b",
    r"\bend\s+of\s+(?:the\s+)?month\b",
    r"\bschedule\s+(?:a|an|me\s+a?)?\b",                # "schedule a ..."
    r"\bsend\s+me\b",                                    # "send me balance" → "balance"
]


def _strip_scheduling_phrases(query: str) -> str:
    """Remove time/scheduling phrases, leaving the core financial question."""
    q = query
    for pat in _TIME_STRIP_PATTERNS:
        q = re.sub(pat, " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip().strip(",.:;")
    return q or query  # fallback to original if everything stripped


# ── Threshold/tracking intent detection ─────────────────────────────────────

_THRESHOLD_PAT = re.compile(
    r"\b(?:alert|notify|warn|tell)\s+me\s+if\b.*?\$[\d,]+|\b(?:exceeds?|over|above|more\s+than)\b.*?\$[\d,]+",
    re.IGNORECASE,
)
_TRACK_PAT = re.compile(
    r"\btrack\s+(?:my\s+)?(\w+)\s+(?:spend|spending|expenses?)\s+for\s+(\d+)\s+days?\b",
    re.IGNORECASE,
)

# LLM prompt — used only for threshold_alert and track tasks that need structured params
_LLM_PROMPT = """You are a financial task parser. Current time: {current_et} ET.

Return ONLY valid JSON:
{{
  "task_type": "threshold_alert or track_category or track_total",
  "description": "<one line>",
  "params": {{
    "category": "<Groceries/Dining/Travel/Shopping/etc or null>",
    "threshold": <number or null>,
    "fire_at_local": "<HH:MM if user said 'at X pm', else null>"
  }},
  "duration_hours": <number or null>,
  "duration_days": <number or null>,
  "repeat_interval": "<daily/weekly/hourly or null>"
}}

User request: {query}"""


def _parse_with_llm(query: str) -> dict | None:
    """Use LLM only for threshold_alert / tracking tasks that need structured params."""
    try:
        from backend.rag.llm import complete
        offset = _et_utc_offset()
        now_et = datetime.utcnow() + timedelta(hours=offset)
        prompt = (_LLM_PROMPT
                  .replace("{current_et}", now_et.strftime("%Y-%m-%d %H:%M"))
                  .replace("{query}", query))
        raw = complete(prompt, max_tokens=300,
                       system="Return only valid JSON, no explanation.")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as exc:
        logger.warning("[TaskParser] LLM parse failed: %s", exc)
        return None


def parse_task(query: str) -> dict | None:
    """
    Parse a scheduling request. Returns a task dict or None.

    For most queries: uses query_replay (stores the stripped query, replays it at fire time).
    For threshold alerts / multi-day tracking: uses LLM to extract structured params.
    """
    # ── Detect if this needs LLM (threshold / multi-day tracking) ──
    is_threshold = bool(_THRESHOLD_PAT.search(query))
    is_track     = bool(_TRACK_PAT.search(query))

    if is_threshold or is_track:
        task = _parse_with_llm(query)
        if task:
            local_time = _extract_local_time(query)
            if local_time:
                task.setdefault("params", {})["fire_at_local"] = local_time
            task["repeat_interval"] = _detect_repeat_interval(query) or task.get("repeat_interval")
            return task
        # Fall through to query_replay if LLM fails

    # ── Default: query_replay ──────────────────────────────────────
    local_time      = _extract_local_time(query)
    repeat_interval = _detect_repeat_interval(query)
    core_query      = _strip_scheduling_phrases(query)

    return {
        "task_type": "query_replay",
        "description": f"Scheduled: {core_query}",
        "params": {
            "query": core_query,
            "fire_at_local": local_time,
        },
        "duration_hours": None,
        "duration_days": None,
        "repeat_interval": repeat_interval,
    }


def build_scheduled_task(parsed: dict, initiated_by: str = "user") -> dict:
    """Convert parsed task dict into a scheduled_tasks DB row. Converts ET time to UTC."""
    now_utc = datetime.utcnow()
    offset  = _et_utc_offset()
    now_et  = now_utc + timedelta(hours=offset)

    params        = parsed.get("params", {})
    fire_at_local = params.get("fire_at_local")

    if fire_at_local:
        try:
            h, m = map(int, fire_at_local.split(":"))
            fire_et = now_et.replace(hour=h, minute=m, second=0, microsecond=0)
            extra_days = parsed.get("duration_days") or 0
            if fire_et <= now_et or extra_days > 0:
                fire_et += timedelta(days=max(1, extra_days))
            fire_at = fire_et - timedelta(hours=offset)
        except Exception:
            fire_at = now_utc + timedelta(hours=1)
    else:
        duration_hours = parsed.get("duration_hours") or 0
        duration_days  = parsed.get("duration_days")  or 0
        if duration_hours:
            fire_at = now_utc + timedelta(hours=duration_hours)
        elif duration_days:
            fire_at = now_utc + timedelta(days=duration_days)
        else:
            fire_at = now_utc + timedelta(hours=1)

    snapshot = _capture_snapshot(parsed)

    return {
        "task_type":       parsed.get("task_type", "query_replay"),
        "description":     parsed.get("description", "Scheduled task"),
        "params":          json.dumps(params),
        "fire_at":         fire_at.strftime("%Y-%m-%d %H:%M:%S"),
        "repeat_interval": parsed.get("repeat_interval"),
        "status":          "pending",
        "initiated_by":    initiated_by,
        "snapshot":        json.dumps(snapshot),
    }


def _capture_snapshot(parsed: dict) -> dict:
    """Capture current state for tasks that need before/after comparison."""
    snapshot = {"captured_at": datetime.utcnow().isoformat()}
    task_type = parsed.get("task_type", "")
    if task_type not in ("track_category", "track_total", "threshold_alert"):
        return snapshot  # query_replay tasks don't need a snapshot
    try:
        from backend.storage.database import db
        params   = parsed.get("params", {})
        category = params.get("category")
        with db() as conn:
            if category and task_type in ("track_category", "threshold_alert"):
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) as total FROM transactions
                       WHERE transaction_type='debit' AND category=?
                         AND strftime('%Y-%m', date)=strftime('%Y-%m','now')""",
                    (category,),
                ).fetchone()
                snapshot["category_mtd"] = row["total"]
                snapshot["category"]     = category
            if task_type == "track_total":
                row = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) as total FROM transactions
                       WHERE transaction_type='debit'
                         AND strftime('%Y-%m', date)=strftime('%Y-%m','now')"""
                ).fetchone()
                snapshot["total_mtd"] = row["total"]
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
