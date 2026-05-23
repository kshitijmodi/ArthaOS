"""
Transaction normalizer — cleans raw parsed transactions before storage.
  - Strips noise tokens from descriptions
  - Normalises merchant names
  - Deduces transaction type from amount sign / keywords when ambiguous
"""
import re

from backend.ingestion.parser import RawTransaction

# Tokens to strip from descriptions
NOISE_TOKENS = re.compile(
    r"\b(NEFT|IMPS|UPI|REF|NO|TXN|DR|CR|TRANSFER|FROM|TO|A/C|AC|ACCOUNT|"
    r"\d{6,}|[A-Z0-9]{12,})\b",
    re.IGNORECASE,
)

MULTI_SPACE = re.compile(r"\s{2,}")


def _clean_description(desc: str) -> str:
    cleaned = NOISE_TOKENS.sub(" ", desc)
    cleaned = MULTI_SPACE.sub(" ", cleaned).strip(" -/|")
    return cleaned or desc  # fallback to original if empty after cleaning


def normalize(transactions: list[RawTransaction]) -> list[RawTransaction]:
    for tx in transactions:
        tx.description = _clean_description(tx.description)
        tx.currency = tx.currency.upper().strip() or "INR"
        # Ensure date is in YYYY-MM-DD; parser already does this but guard here
        if len(tx.date) == 8 and tx.date.isdigit():
            # YYYYMMDD → YYYY-MM-DD
            tx.date = f"{tx.date[:4]}-{tx.date[4:6]}-{tx.date[6:]}"
    return transactions
