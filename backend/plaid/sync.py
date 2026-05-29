"""
Plaid sync — pulls accounts, transactions, investment holdings for all items.

Sign convention (consistent across ALL Plaid account types):
  positive amount → money OUT  (debit / expense)
  negative amount → money IN   (credit / deposit / refund)

Two-phase design (same as Teller sync):
  Phase 1 — all Plaid API calls (network I/O, no DB lock held)
  Phase 2 — single fast batch write to DB
"""
import logging
from datetime import date as dt_date

from backend.storage.database import db, is_duplicate_transaction
from backend.plaid.client import get_accounts, sync_transactions, get_investments
from backend.processing.categorizer import categorize_static

logger = logging.getLogger(__name__)

# Plaid personal_finance_category.primary → our categories
_PFC_MAP = {
    "FOOD_AND_DRINK":           "Dining",
    "GENERAL_MERCHANDISE":      "Shopping",
    "GENERAL_SERVICES":         "Miscellaneous",
    "TRANSPORTATION":           "Travel",
    "TRAVEL":                   "Travel",
    "MEDICAL":                  "Healthcare",
    "EDUCATION":                "Education",
    "UTILITIES_AND_PHONE":      "Utilities",
    "RENT_AND_UTILITIES":       "Utilities",
    "RENT":                     "Rent",
    "LOAN_PAYMENTS":            "EMIs",
    "ENTERTAINMENT":            "Miscellaneous",
    "PERSONAL_CARE":            "Healthcare",
    "HOME_IMPROVEMENT":         "Shopping",
    "GOVERNMENT_AND_NON_PROFIT":"Miscellaneous",
    "BANK_FEES":                "Fees & Interest",
    "TRANSFER_IN":              "Transfer",
    "TRANSFER_OUT":             "Transfer",
    "INCOME":                   "Income",
    "PAYROLL":                  "Income",
    "INVESTMENTS":              "Investments",
    "SUBSCRIPTIONS":            "Subscriptions",
    "INSURANCE":                "Insurance",
}


def _categorize_tx(tx: dict) -> str:
    """
    Determine category for a Plaid transaction.
    Priority: personal_finance_category map → static keyword rules.
    """
    pfc = (tx.get("personal_finance_category") or {}).get("primary", "")
    if pfc and pfc in _PFC_MAP:
        return _PFC_MAP[pfc]
    description = tx.get("name", "") or tx.get("merchant_name", "")
    return categorize_static(description)


def _prepare_tx(tx: dict, acct_map: dict) -> dict:
    """Convert a raw Plaid transaction dict to a flat insert-ready dict."""
    raw = float(tx.get("amount", 0))
    tx_type = "debit" if raw >= 0 else "credit"
    amount  = abs(raw)
    description = tx.get("name", "") or tx.get("merchant_name", "") or ""
    acct = acct_map.get(tx.get("account_id", ""), {})
    return {
        "source_file": f"plaid:{tx['transaction_id']}",
        "date":        tx.get("date", dt_date.today().isoformat()),
        "description": description,
        "amount":      amount,
        "tx_type":     tx_type,
        "category":    _categorize_tx(tx),
        "acc_display": acct.get("name", ""),
    }


def sync_item(item_id: str, access_token: str, institution: str) -> dict:
    """
    Sync one Plaid item: transactions (incremental) + investment holdings.
    Returns {"new_transactions": int, "removed": int, "holdings": int}.
    """
    # ── Phase 1: fetch from Plaid (no DB lock) ──────────────────────────── #

    # Read stored cursor
    with db() as conn:
        row = conn.execute(
            "SELECT cursor FROM plaid_items WHERE item_id = ?", (item_id,)
        ).fetchone()
    cursor = (row["cursor"] if row and row["cursor"] else None)

    accounts_raw = []
    try:
        accounts_raw = get_accounts(access_token)
    except Exception as exc:
        logger.warning("[PlaidSync] Accounts fetch failed for %s: %s", institution, exc)

    acct_map = {a["account_id"]: a for a in accounts_raw}

    tx_result = {"added": [], "modified": [], "removed": [], "next_cursor": cursor or ""}
    try:
        tx_result = sync_transactions(access_token, cursor)
    except Exception as exc:
        logger.warning("[PlaidSync] Transaction sync failed for %s: %s", institution, exc)

    investments = {"holdings": [], "securities": []}
    try:
        investments = get_investments(access_token)
    except Exception as exc:
        logger.debug("[PlaidSync] Investments unavailable for %s: %s", institution, exc)

    # Pre-process transactions
    prepared_added = [_prepare_tx(tx, acct_map) for tx in tx_result["added"]]
    removed_source_files = [f"plaid:{r['transaction_id']}" for r in tx_result.get("removed", [])]

    # Pre-process investment holdings
    securities = {s["security_id"]: s for s in investments.get("securities", [])}
    today = dt_date.today().isoformat()
    prepared_holdings = []
    for h in investments.get("holdings", []):
        sec = securities.get(h.get("security_id", ""), {})
        ticker = sec.get("ticker_symbol") or sec.get("name", "Unknown")
        name   = sec.get("name") or ticker
        qty    = h.get("quantity")
        price  = h.get("institution_price") or sec.get("close_price")
        value  = h.get("institution_value") or ((qty or 0) * (price or 0))
        acct   = acct_map.get(h.get("account_id", ""), {})
        prepared_holdings.append({
            "ticker":     ticker,
            "name":       name,
            "quantity":   qty,
            "price":      price,
            "total_value":value,
            "acc_name":   acct.get("name", ""),
            "source_file":f"plaid:{item_id}:{h.get('account_id','')}:{ticker}",
        })

    # ── Phase 2: write to DB ─────────────────────────────────────────────── #

    new_txns = 0
    next_cursor = tx_result["next_cursor"]

    with db() as conn:
        # Upsert account balances
        for acct in accounts_raw:
            bal = acct.get("balances", {})
            conn.execute(
                """INSERT INTO plaid_accounts
                   (account_id, item_id, institution, name, official_name,
                    type, subtype, currency,
                    balance_available, balance_current, balance_limit, last_synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(account_id) DO UPDATE SET
                     balance_available = excluded.balance_available,
                     balance_current   = excluded.balance_current,
                     balance_limit     = excluded.balance_limit,
                     last_synced_at    = CURRENT_TIMESTAMP""",
                (
                    acct["account_id"], item_id, institution,
                    acct.get("name", ""), acct.get("official_name"),
                    acct.get("type", ""), acct.get("subtype", ""),
                    (bal.get("iso_currency_code") or "USD"),
                    bal.get("available"), bal.get("current"), bal.get("limit"),
                ),
            )

        # Insert new transactions
        for row in prepared_added:
            if conn.execute(
                "SELECT 1 FROM transactions WHERE source_file = ?", (row["source_file"],)
            ).fetchone():
                continue
            if is_duplicate_transaction(
                conn, row["date"], row["amount"], row["tx_type"], row["description"]
            ):
                logger.debug("[PlaidSync] Dup skipped: %s %s $%.2f",
                             row["date"], row["description"], row["amount"])
                continue
            conn.execute(
                """INSERT INTO transactions
                   (date, description, amount, currency, transaction_type, category,
                    category_source, source_file, confidence_score, institution, account_name)
                   VALUES (?,?,?,?,?,?,'auto',?,0.90,?,?)""",
                (row["date"], row["description"], row["amount"], "USD",
                 row["tx_type"], row["category"], row["source_file"],
                 institution, row["acc_display"]),
            )
            new_txns += 1

        # Remove transactions Plaid has reversed/removed
        for sf in removed_source_files:
            conn.execute("DELETE FROM transactions WHERE source_file = ?", (sf,))

        # Upsert investment holdings (today's snapshot)
        for h in prepared_holdings:
            conn.execute(
                """INSERT INTO investment_holdings
                   (as_of_date, ticker, name, quantity, price, total_value,
                    account, broker, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(as_of_date, ticker, account, source_file)
                   DO UPDATE SET
                     quantity    = excluded.quantity,
                     price       = excluded.price,
                     total_value = excluded.total_value""",
                (today, h["ticker"], h["name"], h["quantity"], h["price"],
                 h["total_value"], h["acc_name"], institution, h["source_file"]),
            )

        # Persist cursor and last_synced_at
        conn.execute(
            """UPDATE plaid_items
               SET cursor = ?, last_synced_at = CURRENT_TIMESTAMP
               WHERE item_id = ?""",
            (next_cursor, item_id),
        )

    logger.info(
        "[PlaidSync] %s — %d new txns, %d removed, %d holdings",
        institution, new_txns, len(removed_source_files), len(prepared_holdings),
    )
    return {
        "new_transactions": new_txns,
        "removed":          len(removed_source_files),
        "holdings":         len(prepared_holdings),
    }


def sync_all() -> dict:
    """Sync all active Plaid items. Called by the scheduler."""
    with db() as conn:
        items = conn.execute(
            "SELECT item_id, access_token, institution FROM plaid_items WHERE status = 'active'"
        ).fetchall()

    if not items:
        return {"items": 0, "new_transactions": 0}

    total_txns = 0
    for row in items:
        result = sync_item(row["item_id"], row["access_token"], row["institution"])
        total_txns += result.get("new_transactions", 0)

    logger.info("[PlaidSync] Sync complete — %d items, %d new txns", len(items), total_txns)
    return {"items": len(items), "new_transactions": total_txns}
