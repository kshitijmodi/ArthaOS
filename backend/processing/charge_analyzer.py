"""
Charge analyzer — detects duplicate charges, interest fees, late fees,
and suspicious transaction patterns from ingested transactions.

Detection modules:
  1. Duplicate Charges     — same amount + similar merchant within configurable window
  2. Interest Fees         — transactions matching interest / finance charge patterns
  3. Late Fees             — transactions matching late fee / penalty patterns
  4. Suspicious Charges    — keyword-flagged or significantly above category baseline
"""
import json
import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from backend.config import (
    ANOMALY_MULTIPLIER,
    ANOMALY_UNKNOWN_MIN,
    DUPLICATE_WINDOW_DAYS,
)
from backend.ingestion.parser import RawTransaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable thresholds (supplement backend/config.py values)
# ---------------------------------------------------------------------------

# Minimum description similarity ratio to flag as duplicate (0–1)
DUPLICATE_SIMILARITY_THRESHOLD = 0.80

# Minimum debit amount to raise a late-fee alert at "high" severity
LATE_FEE_HIGH_SEVERITY_AMOUNT = 500.0

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

INTEREST_PATTERNS = re.compile(
    r"\b(interest\s*charge|finance\s*charge|interest\s*fee|accrued\s*interest|"
    r"revolving\s*interest|purchase\s*interest|cash\s*advance\s*fee|"
    r"apr\s*charge|interest\s*debit|interest)\b",
    re.IGNORECASE,
)

LATE_FEE_PATTERNS = re.compile(
    r"\b(late\s*fee|late\s*payment|overdue\s*fee|penalty\s*charge|"
    r"payment\s*penalty|delay\s*charge|late\s*charges|"
    r"overlimit\s*fee|over.?limit|past\s*due\s*fee|returned\s*payment)\b",
    re.IGNORECASE,
)

SUSPICIOUS_KEYWORDS = re.compile(
    r"\b(casino|gambling|bet\b|lottery|foreign\s*transaction|fx\s*fee|"
    r"wire\s*transfer\s*fee|atm\s*surcharge|returned\s*item|nsf\s*fee|"
    r"insufficient\s*funds|chargeback|reversal\s*fee|cash\s*advance)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _description_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------

def detect_duplicates(transactions: list[RawTransaction]) -> list[dict]:
    """
    Flag transactions with the same amount and highly similar description
    occurring within DUPLICATE_WINDOW_DAYS of each other.
    Checks both within the incoming batch and against recent DB history.
    """
    alerts: list[dict] = []
    window = timedelta(days=DUPLICATE_WINDOW_DAYS)
    debits = [t for t in transactions if t.transaction_type == "debit"]

    # --- Intra-batch duplicates ---
    seen_pairs: set[frozenset] = set()
    for i, tx_a in enumerate(debits):
        try:
            date_a = datetime.strptime(tx_a.date, "%Y-%m-%d")
        except ValueError:
            continue
        for j, tx_b in enumerate(debits[i + 1:], start=i + 1):
            pair = frozenset((i, j))
            if pair in seen_pairs:
                continue
            try:
                date_b = datetime.strptime(tx_b.date, "%Y-%m-%d")
            except ValueError:
                continue
            if abs((date_a - date_b).days) > DUPLICATE_WINDOW_DAYS:
                continue
            if abs(tx_a.amount - tx_b.amount) > 0.01:
                continue
            sim = _description_similarity(tx_a.description, tx_b.description)
            if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                seen_pairs.add(pair)
                alerts.append({
                    "alert_type": "duplicate_charge",
                    "severity": "high",
                    "description": (
                        f"Possible duplicate charge of {tx_a.currency} {tx_a.amount:.2f} "
                        f"for '{tx_a.description}' on {tx_a.date} and {tx_b.date} "
                        f"(similarity {sim:.0%})"
                    ),
                    "related_transactions": [],
                    "confidence_score": round(sim, 2),
                })

    # --- Cross-batch: compare each incoming debit against DB history ---
    try:
        from backend.storage.database import db
        for tx in debits:
            try:
                date_tx = datetime.strptime(tx.date, "%Y-%m-%d")
            except ValueError:
                continue
            cutoff = (date_tx - window).strftime("%Y-%m-%d")
            upper = (date_tx + window).strftime("%Y-%m-%d")
            with db() as conn:
                rows = conn.execute(
                    """SELECT id, date, description, amount FROM transactions
                       WHERE transaction_type = 'debit'
                         AND ABS(amount - ?) < 0.01
                         AND date BETWEEN ? AND ?""",
                    (tx.amount, cutoff, upper),
                ).fetchall()
            for row in rows:
                sim = _description_similarity(tx.description, row["description"])
                if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                    alerts.append({
                        "alert_type": "duplicate_charge",
                        "severity": "high",
                        "description": (
                            f"Incoming charge of {tx.currency} {tx.amount:.2f} "
                            f"for '{tx.description}' on {tx.date} may duplicate "
                            f"existing transaction #{row['id']} on {row['date']} "
                            f"(similarity {sim:.0%})"
                        ),
                        "related_transactions": [row["id"]],
                        "confidence_score": round(sim, 2),
                    })
    except Exception as exc:
        logger.debug("[ChargeAnalyzer] DB duplicate cross-check skipped: %s", exc)

    return alerts


def detect_interest_fees(transactions: list[RawTransaction]) -> list[dict]:
    """Flag transactions that match known interest / finance charge patterns."""
    alerts: list[dict] = []
    for tx in transactions:
        if tx.transaction_type != "debit":
            continue
        if INTEREST_PATTERNS.search(tx.description):
            alerts.append({
                "alert_type": "interest_fee",
                "severity": "medium",
                "description": (
                    f"Interest or finance charge detected: '{tx.description}' "
                    f"of {tx.currency} {tx.amount:.2f} on {tx.date}"
                ),
                "related_transactions": [],
                "confidence_score": 0.90,
            })
    return alerts


def detect_late_fees(transactions: list[RawTransaction]) -> list[dict]:
    """Flag transactions that match late fee / penalty patterns."""
    alerts: list[dict] = []
    for tx in transactions:
        if tx.transaction_type != "debit":
            continue
        if LATE_FEE_PATTERNS.search(tx.description):
            severity = "high" if tx.amount >= LATE_FEE_HIGH_SEVERITY_AMOUNT else "medium"
            alerts.append({
                "alert_type": "late_fee",
                "severity": severity,
                "description": (
                    f"Late fee or penalty detected: '{tx.description}' "
                    f"of {tx.currency} {tx.amount:.2f} on {tx.date}"
                ),
                "related_transactions": [],
                "confidence_score": 0.90,
            })
    return alerts


def detect_suspicious_charges(transactions: list[RawTransaction]) -> list[dict]:
    """
    Flag transactions that are either keyword-suspicious or significantly
    above the historical average for their category (ANOMALY_MULTIPLIER).
    """
    alerts: list[dict] = []

    # Fetch per-category average debit from DB for baseline comparison
    category_avgs: dict[str, float] = {}
    try:
        from backend.storage.database import db
        with db() as conn:
            rows = conn.execute(
                """SELECT category, AVG(amount) AS avg_amount
                   FROM transactions
                   WHERE transaction_type = 'debit'
                   GROUP BY category"""
            ).fetchall()
        category_avgs = {r["category"]: r["avg_amount"] for r in rows if r["avg_amount"]}
    except Exception as exc:
        logger.debug("[ChargeAnalyzer] Category avg fetch skipped: %s", exc)

    for tx in transactions:
        if tx.transaction_type != "debit":
            continue

        # Keyword-based suspicious pattern
        if SUSPICIOUS_KEYWORDS.search(tx.description):
            alerts.append({
                "alert_type": "suspicious_charge",
                "severity": "high",
                "description": (
                    f"Suspicious charge keyword detected: '{tx.description}' "
                    f"of {tx.currency} {tx.amount:.2f} on {tx.date}"
                ),
                "related_transactions": [],
                "confidence_score": 0.85,
            })
            continue

        # Amount anomaly: significantly above category historical average
        try:
            from backend.processing.categorizer import _rule_match
            category = _rule_match(tx.description) or "Miscellaneous"
        except Exception:
            category = "Miscellaneous"

        avg = category_avgs.get(category)
        threshold = ANOMALY_UNKNOWN_MIN if avg is None else avg * ANOMALY_MULTIPLIER
        if tx.amount >= threshold:
            confidence = min(0.95, tx.amount / (threshold * 2)) if threshold > 0 else 0.70
            alerts.append({
                "alert_type": "suspicious_charge",
                "severity": "medium",
                "description": (
                    f"Unusually large {category} charge: '{tx.description}' "
                    f"of {tx.currency} {tx.amount:.2f} on {tx.date}"
                    + (f" (category avg {tx.currency} {avg:.2f})" if avg else "")
                ),
                "related_transactions": [],
                "confidence_score": round(confidence, 2),
            })

    return alerts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_charges(transactions: list[RawTransaction]) -> list[dict]:
    """
    Run all charge detectors on a batch of normalized transactions.
    Returns a combined list of alert dicts ready for persistence.
    """
    if not transactions:
        return []

    alerts: list[dict] = []
    alerts.extend(detect_duplicates(transactions))
    alerts.extend(detect_interest_fees(transactions))
    alerts.extend(detect_late_fees(transactions))
    alerts.extend(detect_suspicious_charges(transactions))

    logger.info(
        "[ChargeAnalyzer] Detected %d alert(s) from %d transaction(s)",
        len(alerts), len(transactions),
    )
    return alerts


def save_charge_alerts(alerts: list[dict]) -> list[int]:
    """
    Persist charge alerts to the alerts table.
    Skips exact duplicates seen within the last 7 days.
    Returns list of newly inserted alert IDs.
    """
    from backend.storage.database import db

    saved_ids: list[int] = []
    with db() as conn:
        for alert in alerts:
            related_json = json.dumps(alert.get("related_transactions", []))
            existing = conn.execute(
                """SELECT 1 FROM alerts
                   WHERE alert_type = ? AND description = ?
                   AND created_at >= datetime('now', '-7 days')""",
                (alert["alert_type"], alert["description"]),
            ).fetchone()
            if existing:
                continue
            cur = conn.execute(
                """INSERT INTO alerts (alert_type, severity, description, related_transactions)
                   VALUES (?, ?, ?, ?)""",
                (alert["alert_type"], alert["severity"], alert["description"], related_json),
            )
            saved_ids.append(cur.lastrowid)

    if saved_ids:
        logger.info("[ChargeAnalyzer] Saved %d new charge alert(s)", len(saved_ids))
    return saved_ids
