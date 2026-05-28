"""
Teller sync — pulls accounts + transactions for all enrolled institutions
and upserts them into the ArthaOS transactions table.
"""
import logging
from datetime import datetime, timezone

from backend.storage.database import db, is_duplicate_transaction
from backend.teller.client import get_accounts, get_transactions, get_account_balances
from backend.processing.categorizer import categorize

logger = logging.getLogger(__name__)

TELLER_TX_TYPE_MAP = {
    "debit":  "debit",
    "credit": "credit",
}


def _upsert_transaction(conn, tx: dict, institution: str, account_name: str = ""):
    """
    Insert a Teller transaction.
    Skips if already stored by Teller ID (same-source dedup)
    OR if a cross-source duplicate exists (same date+amount+type+similar description).
    """
    amount = abs(float(tx.get("amount", 0)))
    tx_type = TELLER_TX_TYPE_MAP.get(tx.get("type", "debit"), "debit")
    description = tx.get("description", "") or tx.get("details", {}).get("counterparty", {}).get("name", "")
    category = tx.get("details", {}).get("category", "") or categorize(description)
    date = tx.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    source_file = f"teller:{tx['id']}"

    # Same-source dedup (exact Teller ID match)
    if conn.execute("SELECT 1 FROM transactions WHERE source_file = ?", (source_file,)).fetchone():
        return False

    # Cross-source dedup (PDF or other source already has this transaction)
    if is_duplicate_transaction(conn, date, amount, tx_type, description):
        logger.debug("[TellerSync] Cross-source duplicate skipped: %s %s $%.2f", date, description, amount)
        return False

    conn.execute(
        """INSERT INTO transactions
           (date, description, amount, currency, transaction_type, category,
            category_source, source_file, confidence_score, institution, account_name)
           VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, 0.85, ?, ?)""",
        (date, description, amount, "USD", tx_type, category, source_file, institution, account_name),
    )
    return True


def sync_enrollment(enrollment_id: str, access_token: str, institution_name: str) -> dict:
    """
    Pull all accounts + transactions for one Teller enrollment.
    Returns counts of new transactions and accounts synced.
    """
    new_txns = 0
    accounts_synced = 0

    try:
        accounts = get_accounts(access_token)
    except Exception as exc:
        logger.error("[TellerSync] Failed to fetch accounts for %s: %s", institution_name, exc)
        return {"new_transactions": 0, "accounts": 0, "error": str(exc)}

    with db() as conn:
        for account in accounts:
            account_id = account["id"]
            accounts_synced += 1

            # Update balance snapshot and store history
            try:
                balances = get_account_balances(access_token, account_id)
                bal_available = balances.get("available")
                bal_ledger    = balances.get("ledger")
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
                        enrollment_id,
                        account_id,
                        institution_name,
                        account.get("name", ""),
                        account.get("type", ""),
                        account.get("subtype", ""),
                        account.get("currency", "USD"),
                        bal_available,
                        bal_ledger,
                    ),
                )
                # Store a timestamped snapshot for historical period lookups
                conn.execute(
                    """INSERT INTO teller_balance_history
                       (account_id, balance_available, balance_ledger)
                       VALUES (?, ?, ?)""",
                    (account_id, bal_available, bal_ledger),
                )
            except Exception as exc:
                logger.warning("[TellerSync] Balance fetch failed for %s: %s", account_id, exc)

            # Pull transactions
            try:
                txns = get_transactions(access_token, account_id)
                acc_display = account.get("name", "")
                for tx in txns:
                    if _upsert_transaction(conn, tx, institution_name, acc_display):
                        new_txns += 1
            except Exception as exc:
                logger.warning("[TellerSync] Transaction fetch failed for %s: %s", account_id, exc)

        # Update last_synced_at on enrollment
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
