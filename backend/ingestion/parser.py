"""
PDF parser — extracts raw text and structured transactions from bank statements.
Uses PyMuPDF as primary extractor with pdfplumber as fallback.
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RawTransaction:
    date: str
    description: str
    amount: float
    transaction_type: str          # "debit" or "credit"
    currency: str = "INR"
    raw_text: str = ""
    confidence_score: float = 1.0


@dataclass
class ParseResult:
    file_path: Path
    file_hash: str
    raw_text: str
    transactions: list[RawTransaction] = field(default_factory=list)
    stated_total: Optional[float] = None   # total from statement header if found
    parse_warnings: list[str] = field(default_factory=list)
    success: bool = True
    failure_reason: str = ""


# ---------------------------------------------------------------------------
# Date patterns — handles common Indian bank statement formats
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"),   # DD/MM/YYYY
    re.compile(r"\b(\d{2}-\d{2}-\d{4})\b"),   # DD-MM-YYYY
    re.compile(r"\b(\d{2}\s+\w{3}\s+\d{4})\b"),  # DD Mon YYYY
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),   # YYYY-MM-DD
    re.compile(r"\b(\d{2}/\d{2}/\d{2})\b"),   # DD/MM/YY
]

AMOUNT_PATTERN = re.compile(
    r"(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:Dr|Cr)?",
    re.IGNORECASE,
)

DR_CR_PATTERN = re.compile(r"\b(Dr|CR|Debit|Credit)\b", re.IGNORECASE)

# Lines that look like transaction rows (date + text + amount)
TRANSACTION_LINE = re.compile(
    r"(\d{2}[/\-]\d{2}[/\-]\d{2,4})"   # date
    r"\s+(.+?)\s+"                       # description
    r"([\d,]+\.\d{2})"                   # amount
    r"(?:\s+([\d,]+\.\d{2}))?",          # optional balance
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_amount(raw: str) -> float:
    return float(raw.replace(",", "").strip())


def _normalise_date(raw: str) -> str:
    """Try to normalise a raw date string to YYYY-MM-DD."""
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%Y-%m-%d", "%d %b %Y", "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw.strip()


def _infer_type(line: str) -> str:
    """Infer debit/credit from line content."""
    line_lower = line.lower()
    if any(w in line_lower for w in ["cr", "credit", "salary", "refund", "cashback", "reversal"]):
        return "credit"
    return "debit"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text_pymupdf(path: Path, password: str = "") -> str:
    doc = fitz.open(str(path))
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            raise ValueError("Password required or incorrect for this PDF.")
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def _extract_text_pdfplumber(path: Path, password: str = "") -> str:
    kwargs = {"password": password} if password else {}
    pages = []
    with pdfplumber.open(str(path), **kwargs) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def extract_text(path: Path, password: str = "") -> str:
    """Extract text, falling back to pdfplumber if PyMuPDF returns little."""
    try:
        text = _extract_text_pymupdf(path, password)
        if len(text.strip()) > 100:
            return text
    except Exception as exc:
        logger.warning("[Parser] PyMuPDF failed for %s: %s", path.name, exc)

    try:
        return _extract_text_pdfplumber(path, password)
    except Exception as exc:
        raise RuntimeError(f"Both parsers failed for {path.name}: {exc}") from exc


# ---------------------------------------------------------------------------
# Transaction extraction
# ---------------------------------------------------------------------------

def _parse_transactions(text: str) -> list[RawTransaction]:
    transactions: list[RawTransaction] = []

    for line in text.splitlines():
        line = line.strip()
        if len(line) < 10:
            continue

        m = TRANSACTION_LINE.search(line)
        if not m:
            continue

        raw_date, desc, amount_str = m.group(1), m.group(2).strip(), m.group(3)

        try:
            amount = _clean_amount(amount_str)
        except ValueError:
            continue

        if amount <= 0:
            continue

        date = _normalise_date(raw_date)
        tx_type = _infer_type(line)

        # Confidence: lower if description is very short or date looks odd
        confidence = 1.0
        if len(desc) < 4:
            confidence -= 0.3
        if date == raw_date:  # normalisation failed
            confidence -= 0.2

        transactions.append(RawTransaction(
            date=date,
            description=desc,
            amount=amount,
            transaction_type=tx_type,
            raw_text=line,
            confidence_score=round(max(confidence, 0.1), 2),
        ))

    return transactions


def _extract_stated_total(text: str) -> Optional[float]:
    """Try to pull a 'Total Debit' or 'Total Amount' figure from the statement."""
    patterns = [
        re.compile(r"total\s+debit[s]?\s*[:\-]?\s*([\d,]+\.\d{2})", re.IGNORECASE),
        re.compile(r"total\s+amount[s]?\s*[:\-]?\s*([\d,]+\.\d{2})", re.IGNORECASE),
        re.compile(r"statement\s+total\s*[:\-]?\s*([\d,]+\.\d{2})", re.IGNORECASE),
    ]
    for p in patterns:
        m = p.search(text)
        if m:
            try:
                return _clean_amount(m.group(1))
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_pdf(path: Path, password: str = "") -> ParseResult:
    file_hash = _file_hash(path)
    result = ParseResult(file_path=path, file_hash=file_hash, raw_text="")

    try:
        raw_text = extract_text(path, password)
    except ValueError as exc:
        result.success = False
        result.failure_reason = str(exc)
        return result
    except RuntimeError as exc:
        result.success = False
        result.failure_reason = str(exc)
        return result

    result.raw_text = raw_text
    result.transactions = _parse_transactions(raw_text)
    result.stated_total = _extract_stated_total(raw_text)

    if not result.transactions:
        result.parse_warnings.append("No transactions extracted — statement format may be unsupported.")

    logger.info(
        "[Parser] %s → %d transactions extracted (stated total: %s)",
        path.name,
        len(result.transactions),
        result.stated_total,
    )
    return result
