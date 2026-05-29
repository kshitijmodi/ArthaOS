"""
Teller sync — pulls accounts + transactions for all enrolled institutions
and upserts them into the ArthaOS transactions table.

Two-phase design to avoid SQLite "database is locked":
  Phase 1 — fetch from Teller API + categorize (all network I/O, NO DB connection held)
  Phase 2 — one fast batch write to DB (pure SQL, no network calls)
"""
import logging
from datetime import datetime, timezone

from backend.storage.database import db, is_duplicate_transaction
from backend.teller.client import get_accounts, get_transactions, get_account_balances
from backend.processing.categorizer import categorize, get_valid_categories

logger = logging.getLogger(__name__)


def _resolve_tx_type(tx: dict) -> tuple[str, float]:
    """
    Determine (tx_type, amount) from a raw Teller transaction dict.

    Teller uses two signals:
      - tx["type"]: "debit" | "credit"  (direction of cash flow)
      - tx["amount"]: positive for debits, NEGATIVE for credits on CC accounts

    The sign of the amount is the ground truth.  Teller sometimes returns
    type="debit" even for CC credits (payments / refunds), so we treat a
    negative amount as authoritative and override the type field when they
    contradict each other.
    """
    raw = float(tx.get("amount", 0))
    teller_type = (tx.get("type", "") or "").lower()
    if raw < 0 or teller_type == "credit":
        return "credit", abs(raw)
    return "debit", abs(raw)


def _prepare_tx(tx: dict, acc_display: str) -> dict:
    """
    Pre-process one Teller transaction dict into a flat dict ready for DB insert.
    Categorization happens here (outside any DB lock) using keyword_only=True
    to avoid Groq rate-limiting stalling an open write transaction.
    """
    tx_type, amount = _resolve_tx_type(tx)
    description = (
        tx.get("description", "")
        or (tx.get("details", {}) or {}).get("counterparty", {}).get("name", "")
    )
    teller_cat = ((tx.get("details", {}) or {}).get("category", "") or "").strip()
    valid_cats = get_valid_categories()
    category = teller_cat if teller_cat in valid_cats else categorize(description, keyword_only=True)
    date = tx.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    return {
        "source_file": f"teller:{tx['id']}",
        "date": date,
        "description": description,
        "amount": amount,
        "tx_type": tx_type,
        "category": category,
        "acc_display": acc_display,
    }


def _insert_prepared_tx(conn, row: dict, institution: str) -> bool:
    """Insert a pre-categorized transaction. Returns True if a new row was inserted."""
    if conn.execute(
        "SELECT 1 FROM transactions WHERE source_file = ?", (row["source_file"],)
    ).fetchone():
        return False

    if is_duplicate_transaction(conn, row["date"], row["amount"], row["tx_type"], row["description"]):
        logger.debug(
            "[TellerSync] Cross-source duplicate skipped: %s %s $%.2f",
            row["date"], row["description"], row["amount"],
        )
        return False

    conn.execute(
        """INSERT INTO transactions
           (date, description, amount, currency, transaction_type, category,
            category_source, source_file, confidence_score, institution, account_name)
           VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, 0.85, ?, ?)""",
        (
            row["date"], row["description"], row["amount"], "USD",
            row["tx_type"], row["category"], row["source_file"],
            institution, row["acc_display"],
        ),
    )
    return True


def sync_enrollment(enrollment_id: str, access_token: str, institution_name: str) -> dict:
    """
    Pull all accounts + transactions for one Teller enrollment.
    Returns counts of new transactions and accounts synced.
    """
    # ------------------------------------------------------------------ #
    # Phase 1: fetch everything from Teller + pre-categorize              #
    #          No DB connection is held during this phase.                #
    # ------------------------------------------------------------------ #
    try:
        accounts = get_accounts(access_token)
    except Exception as exc:
        logger.error("[TellerSync] Failed to fetch accounts for %s: %s", institution_name, exc)
        return {"new_transactions": 0, "accounts": 0, "error": str(exc)}

    account_payloads = []  # [(account_dict, balances_dict, [prepared_tx, ...])]

    for account in accounts:
        account_id = account["id"]
        acc_display = account.get("name", "")

        balances: dict = {}
        try:
            balances = get_account_balances(access_token, account_id)
        except Exception as exc:
            logger.warning("[TellerSync] Balance fetch failed for %s: %s", account_id, exc)

        prepared_txns: list[dict] = []
        try:
            txns = get_transactions(access_token, account_id)
            for tx in txns:
                prepared_txns.append(_prepare_tx(tx, acc_display))
        except Exception as exc:
            logger.warning("[TellerSync] Transaction fetch failed for %s: %s", account_id, exc)

        account_payloads.append((account, balances, prepared_txns))

    # ------------------------------------------------------------------ #
    # Phase 2: write everything to DB in a single short-lived connection  #
    #          Pure SQL — no network calls, no Groq retries.              #
    # ------------------------------------------------------------------ #
    new_txns = 0
    accounts_synced = len(account_payloads)

    with db() as conn:
        for account, balances, prepared_txns in account_payloads:
            account_id = account["id"]

            if balances:
                bal_available = balances.get("available")
                bal_ledger = balances.get("ledger")
                try:
                    conn.execute(
                        """INSERT INTO teller_accounts
                           (enrollment_id, account_id, institution, name, type, subtype,
                            currency, balance_available, balance_ledger, last_synced_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(account_id) DO UPDATE SET
                             balance_available = excluded.balance_available,
                             balance_ledger    = excluded.balance_ledger,
                             last_synced_at    = CURRENT_TIMESTAMP""",
                        (
                            enrollment_id, account_id, institution_name,
                            account.get("name", ""), account.get("type", ""),
                            account.get("subtype", ""), account.get("currency", "USD"),
                            bal_available, bal_ledger,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO teller_balance_history
                           (account_id, balance_available, balance_ledger)
                           VALUES (?, ?, ?)""",
                        (account_id, bal_available, bal_ledger),
                    )
                except Exception as exc:
                    logger.warning("[TellerSync] Balance write failed for %s: %s", account_id, exc)

            for row in prepared_txns:
                if _insert_prepared_tx(conn, row, institution_name):
                    new_txns += 1

        conn.execute(
            "UPDATE teller_enrollments SET last_synced_at = CURRENT_TIMESTAMP WHERE enrollment_id = ?",
            (enrollment_id,),
        )

    logger.info(
        "[TellerSync] %s — %d accounts, %d new transactions",
        institution_name, accounts_synced, new_txns,
    )
    return {"new_transactions": new_txns, "accounts": accounts_synced}


def sync_all() -> dict:
    """Sync all active Teller enrollments. Called by the scheduler."""
    with db() as conn:
        enrollments = conn.execute(
            "SELECT enrollment_id, access_token, institution FROM teller_enrollments WHERE status = 'active'"
        ).fetchall()

    if not enrollments:
        logger.info("[TellerSync] No active enrollments to sync")
        return {"enrollments": 0, "new_transactions": 0}

    total_txns = 0
    for row in enrollments:
        result = sync_enrollment(row["enrollment_id"], row["access_token"], row["institution"])
        total_txns += result.get("new_transactions", 0)

    logger.info("[TellerSync] Sync complete — %d total new transactions", total_txns)
    return {"enrollments": len(enrollments), "new_transactions": total_txns}
