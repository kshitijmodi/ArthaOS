"""
Agent engine — proactive financial monitoring.
Runs post-ingestion and on a daily schedule.
Does not alert until at least AGENT_MIN_MONTHS of data is available.

Detection modules:
  1. Overspend Detector
  2. Anomaly Detector
  3. Recurring Charge Monitor
  4. Duplicate Detector
  5. Monthly Budget Monitor
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.config import (
    OVERSPEND_THRESHOLD,
    ANOMALY_MULTIPLIER,
    ANOMALY_UNKNOWN_MIN,
    DUPLICATE_WINDOW_DAYS,
    BUDGET_OVERSHOOT_THRESHOLD,
    AGENT_MIN_MONTHS,
)
from backend.storage.database import db

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    alert_type: str
    severity: str          # low / medium / high
    description: str
    related_transactions: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _months_of_data() -> int:
    with db() as conn:
        row = conn.execute(
            "SELECT MIN(date) as earliest, MAX(date) as latest FROM transactions"
        ).fetchone()
    if not row["earliest"] or not row["latest"]:
        return 0
    earliest = datetime.strptime(row["earliest"], "%Y-%m-%d")
    latest = datetime.strptime(row["latest"], "%Y-%m-%d")
    return max(0, (latest.year - earliest.year) * 12 + (latest.month - earliest.month))


def _save_alerts(alerts: list[Alert]) -> list[int]:
    """Persist alert objects, skip exact duplicates from last 7 days."""
    saved_ids = []
    with db() as conn:
        for alert in alerts:
            related_json = json.dumps(alert.related_transactions)
            existing = conn.execute(
                """SELECT 1 FROM alerts
                   WHERE alert_type=? AND description=?
                   AND created_at >= datetime('now','-7 days')""",
                (alert.alert_type, alert.description),
            ).fetchone()
            if existing:
                continue
            cur = conn.execute(
                """INSERT INTO alerts
                   (alert_type, severity, description, related_transactions)
                   VALUES (?, ?, ?, ?)""",
                (alert.alert_type, alert.severity, alert.description, related_json),
            )
            saved_ids.append(cur.lastrowid)
    return saved_ids


# ---------------------------------------------------------------------------
# 1. Overspend Detector
# ---------------------------------------------------------------------------

def detect_overspend() -> list[Alert]:
    """
    Computes rolling 30-day average spend per category.
    Alerts if current period exceeds average by OVERSPEND_THRESHOLD.
    """
    alerts = []
    with db() as conn:
        # Rolling 30-day average per category (excluding current period)
        avg_rows = conn.execute(
            """SELECT category, AVG(monthly_total) as avg_spend
               FROM (
                 SELECT category,
                        strftime('%Y-%m', date) as month,
                        SUM(amount) as monthly_total
                 FROM transactions
                 WHERE transaction_type='debit'
                   AND date < date('now','start of month')
                 GROUP BY category, month
               )
               GROUP BY category"""
        ).fetchall()

        # Current month spend per category
        curr_rows = conn.execute(
            """SELECT category, SUM(amount) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category"""
        ).fetchall()

    avg_map = {r["category"]: r["avg_spend"] for r in avg_rows}
    for row in curr_rows:
        cat = row["category"]
        curr = row["total"]
        avg = avg_map.get(cat)
        if avg and avg > 0 and curr > avg * (1 + OVERSPEND_THRESHOLD):
            pct = round((curr / avg - 1) * 100)
            alerts.append(Alert(
                alert_type="overspend",
                severity="medium",
                description=(
                    f"Your {cat} spend this month (₹{curr:,.0f}) is {pct}% above "
                    f"your monthly average (₹{avg:,.0f})."
                ),
            ))
    return alerts


# ---------------------------------------------------------------------------
# 2. Anomaly Detector
# ---------------------------------------------------------------------------

def detect_anomalies() -> list[Alert]:
    """
    Flags individual transactions that are >ANOMALY_MULTIPLIER× category average,
    or from unrecognised merchants above ANOMALY_UNKNOWN_MIN.
    Looks at transactions in the last 30 days.
    """
    alerts = []
    with db() as conn:
        # Category averages per transaction (not monthly)
        avg_rows = conn.execute(
            """SELECT category, AVG(amount) as avg_amount
               FROM transactions WHERE transaction_type='debit'
               GROUP BY category"""
        ).fetchall()
        avg_map = {r["category"]: r["avg_amount"] for r in avg_rows}

        # Recent transactions
        recent = conn.execute(
            """SELECT id, date, description, amount, category
               FROM transactions
               WHERE transaction_type='debit'
                 AND date >= date('now','-30 days')
               ORDER BY amount DESC"""
        ).fetchall()

    known_categories = set(avg_map.keys())

    for row in recent:
        cat = row["category"]
        amt = row["amount"]
        avg = avg_map.get(cat)

        # Anomaly: significantly above category average
        if avg and amt > avg * ANOMALY_MULTIPLIER:
            alerts.append(Alert(
                alert_type="anomaly",
                severity="high",
                description=(
                    f"Unusual transaction: ₹{amt:,.0f} at {row['description']} on {row['date']} "
                    f"is {round(amt/avg, 1)}× your typical {cat} spend."
                ),
                related_transactions=[row["id"]],
            ))
        # Unknown merchant above threshold
        elif cat == "Miscellaneous" and amt >= ANOMALY_UNKNOWN_MIN:
            alerts.append(Alert(
                alert_type="anomaly",
                severity="high",
                description=(
                    f"Unusual transaction detected — ₹{amt:,.0f} at unrecognised merchant "
                    f"'{row['description']}' on {row['date']}."
                ),
                related_transactions=[row["id"]],
            ))

    return alerts


# ---------------------------------------------------------------------------
# 3. Recurring Charge Monitor
# ---------------------------------------------------------------------------

def detect_recurring_issues() -> list[Alert]:
    """
    Tracks expected recurring charges (EMIs, subscriptions, insurance).
    Alerts if amount changed or charge is missing this month.
    """
    alerts = []
    current_month = datetime.now().strftime("%Y-%m")
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    with db() as conn:
        # Get recurring merchants from last month
        last_month_charges = conn.execute(
            """SELECT description, SUM(amount) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND category IN ('EMIs','Subscriptions','Insurance')
                 AND strftime('%Y-%m', date) = ?
               GROUP BY description""",
            (last_month,),
        ).fetchall()

        # Get this month's recurring charges
        this_month_charges = conn.execute(
            """SELECT description, SUM(amount) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND category IN ('EMIs','Subscriptions','Insurance')
                 AND strftime('%Y-%m', date) = ?
               GROUP BY description""",
            (current_month,),
        ).fetchall()

    this_month_map = {r["description"]: r["total"] for r in this_month_charges}

    for row in last_month_charges:
        desc = row["description"]
        last_amt = row["total"]

        if desc not in this_month_map:
            # Missing this month
            alerts.append(Alert(
                alert_type="missing_charge",
                severity="medium",
                description=f"Expected charge missing: '{desc}' (₹{last_amt:,.0f}) not seen this month.",
            ))
        else:
            this_amt = this_month_map[desc]
            change_pct = abs(this_amt - last_amt) / last_amt if last_amt else 0
            if change_pct > 0.05:  # > 5% change
                direction = "increased" if this_amt > last_amt else "decreased"
                alerts.append(Alert(
                    alert_type="recurring_change",
                    severity="medium",
                    description=(
                        f"Recurring charge changed: '{desc}' {direction} from "
                        f"₹{last_amt:,.0f} to ₹{this_amt:,.0f} this month."
                    ),
                ))

    return alerts


# ---------------------------------------------------------------------------
# 4. Duplicate Detector
# ---------------------------------------------------------------------------

def detect_duplicates() -> list[Alert]:
    """
    Detects same merchant + same amount within DUPLICATE_WINDOW_DAYS.
    """
    alerts = []
    with db() as conn:
        rows = conn.execute(
            """SELECT a.id as id1, b.id as id2,
                      a.description, a.amount, a.date as date1, b.date as date2
               FROM transactions a
               JOIN transactions b
                 ON a.description = b.description
                AND a.amount = b.amount
                AND a.id < b.id
                AND a.transaction_type = 'debit'
                AND b.transaction_type = 'debit'
                AND julianday(b.date) - julianday(a.date) <= ?
                AND julianday(b.date) - julianday(a.date) >= 0
               WHERE b.date >= date('now', '-60 days')""",
            (DUPLICATE_WINDOW_DAYS,),
        ).fetchall()

    seen = set()
    for row in rows:
        key = (row["description"], row["amount"], row["date1"])
        if key in seen:
            continue
        seen.add(key)
        alerts.append(Alert(
            alert_type="duplicate",
            severity="high",
            description=(
                f"Possible duplicate charge — ₹{row['amount']:,.0f} at '{row['description']}' "
                f"appears on {row['date1']} and {row['date2']} ({DUPLICATE_WINDOW_DAYS}-day window)."
            ),
            related_transactions=[row["id1"], row["id2"]],
        ))

    return alerts


# ---------------------------------------------------------------------------
# 5. Monthly Budget Monitor
# ---------------------------------------------------------------------------

def detect_budget_overrun() -> list[Alert]:
    """
    Compares month-to-date spend against prior month total.
    Alerts if on track to exceed by BUDGET_OVERSHOOT_THRESHOLD.
    """
    alerts = []
    today = datetime.now()
    days_in_month = 30  # approximation
    day_of_month = today.day

    with db() as conn:
        mtd = conn.execute(
            """SELECT COALESCE(SUM(amount),0) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()["total"]

        last_month_total = conn.execute(
            """SELECT COALESCE(SUM(amount),0) as total
               FROM transactions
               WHERE transaction_type='debit'
                 AND strftime('%Y-%m', date) = strftime('%Y-%m', date('now','-1 month'))"""
        ).fetchone()["total"]

    if last_month_total <= 0 or day_of_month == 0:
        return alerts

    # Project full-month spend at current daily rate
    daily_rate = mtd / day_of_month
    projected = daily_rate * days_in_month

    if projected > last_month_total * (1 + BUDGET_OVERSHOOT_THRESHOLD):
        overshoot_pct = round((projected / last_month_total - 1) * 100)
        alerts.append(Alert(
            alert_type="budget_overrun",
            severity="medium",
            description=(
                f"On track to overspend this month — projected ₹{projected:,.0f} vs "
                f"last month's ₹{last_month_total:,.0f} (+{overshoot_pct}%)."
            ),
        ))

    return alerts


# ---------------------------------------------------------------------------
# Main agent run
# ---------------------------------------------------------------------------

def run_agent() -> list[int]:
    """
    Run all detection modules and persist new alerts.
    Returns list of new alert IDs created.
    """
    months = _months_of_data()
    if months < AGENT_MIN_MONTHS:
        logger.info(
            "[Agent] Insufficient data (%d months). Need %d months before alerting.",
            months, AGENT_MIN_MONTHS,
        )
        return []

    logger.info("[Agent] Running detection modules (data span: %d months)...", months)

    all_alerts: list[Alert] = []
    all_alerts += detect_overspend()
    all_alerts += detect_anomalies()
    all_alerts += detect_recurring_issues()
    all_alerts += detect_duplicates()
    all_alerts += detect_budget_overrun()

    saved_ids = _save_alerts(all_alerts)
    logger.info("[Agent] %d new alerts saved (from %d detected)", len(saved_ids), len(all_alerts))
    return saved_ids
