"""
Investment ingestion pipeline.
Stores parsed investment transactions and holdings into SQLite.
"""
import logging
from pathlib import Path

from backend.investments.parser import parse_investment_pdf, InvestmentTransaction, InvestmentHolding
from backend.storage.database import db

logger = logging.getLogger(__name__)


def _already_ingested(file_hash: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM ingested_files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return row is not None


def _record_ingestion(file_hash: str, filename: str, file_size: int,
                      status: str, failure_reason: str = "", tx_count: int = 0):
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO ingested_files
               (file_hash, filename, file_size, status, failure_reason, transaction_count, verified)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (file_hash, filename, file_size, status, failure_reason, tx_count),
        )


def _store_transactions(txs: list[InvestmentTransaction], source_file: str) -> int:
    stored = 0
    with db() as conn:
        for tx in txs:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO investment_transactions
                       (date, ticker, name, transaction_type, quantity, price_per_unit,
                        total_value, currency, account, broker, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tx.date, tx.ticker, tx.name, tx.transaction_type, tx.quantity,
                     tx.price_per_unit, tx.total_value, tx.currency,
                     tx.account, tx.broker, source_file),
                )
                stored += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as exc:
                logger.warning("[InvPipeline] tx store error: %s", exc)
    return stored


def _store_holdings(holdings: list[InvestmentHolding], source_file: str) -> int:
    stored = 0
    with db() as conn:
        for h in holdings:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO investment_holdings
                       (as_of_date, ticker, name, quantity, price, total_value,
                        gain_loss, gain_loss_pct, account, broker, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (h.as_of_date, h.ticker, h.name, h.quantity, h.price,
                     h.total_value, h.gain_loss, h.gain_loss_pct,
                     h.account, h.broker, source_file),
                )
                stored += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as exc:
                logger.warning("[InvPipeline] holding store error: %s", exc)
    return stored


def ingest_investment_file(path: Path) -> dict:
    """Parse and persist an investment statement PDF."""
    logger.info("[InvPipeline] Ingesting: %s", path.name)
    file_size = path.stat().st_size
    result = parse_investment_pdf(path)

    if _already_ingested(result.file_hash):
        logger.info("[InvPipeline] Duplicate — skipping %s", path.name)
        return {"status": "skipped", "reason": "duplicate", "file": path.name}

    if not result.success:
        _record_ingestion(result.file_hash, path.name, file_size, "failed", result.failure_reason)
        return {"status": "failed", "reason": result.failure_reason, "file": path.name}

    tx_count = _store_transactions(result.transactions, path.name)
    holding_count = _store_holdings(result.holdings, path.name)

    _record_ingestion(result.file_hash, path.name, file_size, "success",
                      tx_count=tx_count + holding_count)

    logger.info("[InvPipeline] Done: %s | broker=%s | txs=%d | holdings=%d",
                path.name, result.broker, tx_count, holding_count)

    return {
        "status": "success",
        "file": path.name,
        "broker": result.broker,
        "account": result.account,
        "transactions_stored": tx_count,
        "holdings_stored": holding_count,
    }
