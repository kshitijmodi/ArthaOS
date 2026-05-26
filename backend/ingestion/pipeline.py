"""
Ingestion pipeline — ties together parse → validate → categorize → store → embed.
Called by the watchdog and email fetcher after new files land in /data/statements/.
"""
import logging
from pathlib import Path

from backend.ingestion.parser import parse_pdf
from backend.ingestion.validator import validate
from backend.storage.database import db, is_duplicate_transaction

logger = logging.getLogger(__name__)


def _already_ingested(file_hash: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM ingested_files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return row is not None


def _record_ingestion(file_hash: str, filename: str, file_size: int,
                      status: str, failure_reason: str = "", tx_count: int = 0,
                      verified: bool = False):
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO ingested_files
               (file_hash, filename, file_size, status, failure_reason, transaction_count, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_hash, filename, file_size, status, failure_reason, tx_count, int(verified)),
        )


def _store_transactions(transactions, source_file: str, category_fn) -> int:
    stored = 0
    skipped = 0
    with db() as conn:
        for tx in transactions:
            category = category_fn(tx.description)
            try:
                # Cross-source dedup: skip if a matching transaction already exists
                # from any source (Teller, another PDF, etc.)
                if is_duplicate_transaction(conn, tx.date, tx.amount, tx.transaction_type, tx.description):
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (date, description, amount, currency, transaction_type,
                        category, source_file, raw_text, confidence_score)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tx.date, tx.description, tx.amount, tx.currency,
                     tx.transaction_type, category, source_file,
                     tx.raw_text, tx.confidence_score),
                )
                stored += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as exc:
                logger.warning("[Pipeline] Could not store transaction: %s", exc)
    if skipped:
        logger.info("[Pipeline] %s — skipped %d cross-source duplicate(s)", source_file, skipped)
    return stored


def ingest_file(path: Path, password: str = "") -> dict:
    """
    Parse, validate, categorize and store a single PDF.
    Routes investment PDFs to the investment pipeline automatically.
    Returns a summary dict describing what happened.
    """
    # Check if this is an investment statement — route separately
    try:
        from backend.investments.parser import is_investment_pdf
        if is_investment_pdf(path):
            from backend.investments.pipeline import ingest_investment_file
            return ingest_investment_file(path)
    except Exception as exc:
        logger.warning("[Pipeline] Investment detection failed for %s: %s", path.name, exc)

    # Lazy imports to avoid circular deps at module load time
    from backend.processing.categorizer import categorize
    from backend.embeddings.embedder import embed_and_store

    logger.info("[Pipeline] Ingesting: %s", path.name)
    file_size = path.stat().st_size

    parse_result = parse_pdf(path, password)

    if _already_ingested(parse_result.file_hash):
        logger.info("[Pipeline] Duplicate — skipping %s", path.name)
        return {"status": "skipped", "reason": "duplicate", "file": path.name}

    if not parse_result.success:
        _record_ingestion(
            parse_result.file_hash, path.name, file_size,
            "failed", parse_result.failure_reason,
        )
        return {"status": "failed", "reason": parse_result.failure_reason, "file": path.name}

    # Normalize before validation
    from backend.processing.normalizer import normalize
    parse_result.transactions = normalize(parse_result.transactions)

    validation = validate(parse_result)

    if validation.status == "fail":
        _record_ingestion(
            parse_result.file_hash, path.name, file_size,
            "failed", "; ".join(validation.errors),
        )
        return {"status": "failed", "reason": "; ".join(validation.errors), "file": path.name}

    stored = _store_transactions(parse_result.transactions, path.name, categorize)

    # Run charge analysis after normalization and storage
    try:
        from backend.processing.charge_analyzer import analyze_charges, save_charge_alerts
        alerts = analyze_charges(parse_result.transactions)
        if alerts:
            save_charge_alerts(alerts)
    except Exception as exc:
        logger.warning("[Pipeline] Charge analysis failed for %s: %s", path.name, exc)

    _record_ingestion(
        parse_result.file_hash, path.name, file_size,
        "warning" if validation.status == "warning" else "success",
        "; ".join(validation.warnings),
        tx_count=stored,
        verified=validation.status == "pass",
    )

    # Generate embeddings for the ingested document
    try:
        embed_and_store(parse_result.raw_text, {"source": path.name})
    except Exception as exc:
        logger.warning("[Pipeline] Embedding failed for %s: %s", path.name, exc)

    logger.info("[Pipeline] Done: %s | %d transactions stored | validation: %s",
                path.name, stored, validation.status)

    # Trigger agent post-ingestion (non-blocking)
    _trigger_agent_async()

    return {
        "status": validation.status,
        "file": path.name,
        "transactions_stored": stored,
        "warnings": validation.warnings,
    }


def _trigger_agent_async():
    """Fire-and-forget agent run after ingestion."""
    import threading
    def _run():
        try:
            from backend.agent.engine import run_agent
            alert_ids = run_agent()
            if alert_ids:
                import asyncio
                from backend.agent.notifier import push_new_alerts
                asyncio.run(push_new_alerts(alert_ids))
        except Exception as exc:
            logger.warning("[Pipeline] Agent trigger failed: %s", exc)
    threading.Thread(target=_run, daemon=True).start()


def ingest_directory(directory: Path | None = None) -> list[dict]:
    from backend.config import STATEMENTS_DIR
    target = directory or STATEMENTS_DIR
    results = []
    for pdf in sorted(target.glob("*.pdf")):
        results.append(ingest_file(pdf))
    return results
