"""
Investment statement parser — supports Robinhood, Charles Schwab / ThinkOrSwim, Fidelity 401K.

Returns two lists:
  - holdings  : current portfolio snapshot rows
  - transactions : activity / trade rows

Broker detection is done by scanning the extracted PDF text for known header strings.
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class InvestmentTransaction:
    date: str
    transaction_type: str       # buy / sell / dividend / contribution / withdrawal / fee / transfer
    ticker: Optional[str]
    name: Optional[str]
    quantity: Optional[float]
    price_per_unit: Optional[float]
    total_value: float
    currency: str = "USD"
    account: str = ""
    broker: str = ""


@dataclass
class InvestmentHolding:
    as_of_date: str
    ticker: Optional[str]
    name: str
    quantity: Optional[float]
    price: Optional[float]
    total_value: float
    gain_loss: Optional[float]
    gain_loss_pct: Optional[float]
    account: str = ""
    broker: str = ""


@dataclass
class InvestmentParseResult:
    success: bool
    broker: str
    account: str
    file_hash: str
    transactions: list[InvestmentTransaction] = field(default_factory=list)
    holdings: list[InvestmentHolding] = field(default_factory=list)
    failure_reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_text(path: Path) -> str:
    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
    except Exception as exc:
        logger.warning("[InvParser] pdfplumber error: %s", exc)
    return "\n".join(pages)


def _parse_amount(raw: str) -> Optional[float]:
    """Parse dollar/quantity strings like $1,234.56 or (1,234.56) or -1234.56."""
    raw = raw.strip().replace("$", "").replace(",", "")
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    try:
        val = float(raw)
        return -val if negative else val
    except ValueError:
        return None


def _parse_date(raw: str) -> Optional[str]:
    """Try common US date formats and return ISO YYYY-MM-DD."""
    fmts = ["%m/%d/%Y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y",
            "%m/%d/%y", "%Y-%m-%d", "%d %b %Y"]
    raw = raw.strip()
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Broker detection
# ---------------------------------------------------------------------------

_BROKER_SIGNATURES = {
    "robinhood": [
        r"robinhood",
        r"robinhood\s+securities",
    ],
    "schwab": [
        r"charles\s+schwab",
        r"schwab\s+(one|bank|brokerage|account)",
        r"thinkorswim",
        r"td\s+ameritrade",
    ],
    "fidelity": [
        r"fidelity\s+investments",
        r"fidelity\s+brokerage",
        r"fidelity\s+net\s+benefits",
        r"netbenefits",
        r"fidelity\s+401",
    ],
}


def detect_broker(text: str) -> Optional[str]:
    lower = text[:3000].lower()
    for broker, patterns in _BROKER_SIGNATURES.items():
        for pat in patterns:
            if re.search(pat, lower):
                return broker
    return None


# ---------------------------------------------------------------------------
# Robinhood parser
# ---------------------------------------------------------------------------

# Transaction line (within ACCOUNT ACTIVITY section):
#   04/03/2026 NVDA - NVIDIA Corporation Buy 2.000000 $865.10 $1,730.20
_RH_TX_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"([A-Z]{1,5})\s*[-–]\s*"                                              # ticker
    r"([A-Za-z0-9 &,\.\-]+?)\s+"                                           # name (allow digits for ETFs)
    r"(Buy|Sell|Dividend|Transfer|Deposit|Withdrawal|Fee|ACH\s+\w+)\s+"
    r"([\d,\.]+)?\s*"
    r"\$?([\d,\.]+)?\s*"
    r"\$?([\d,\.]+)",
    re.IGNORECASE,
)

# Non-ticker deposits/withdrawals (no ticker - dash pattern):
#   04/28/2026 ACH Deposit Deposit 0 $0.00 $2,000.00
_RH_NOTX_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"(ACH\s+\w+|Wire\s+\w+|Deposit|Withdrawal|Fee)\s+"
    r"(Deposit|Withdrawal|Fee|Transfer)\s+"
    r"\d+\s+\$[\d,\.]+\s+"
    r"\$?([\d,\.]+)",
    re.IGNORECASE,
)

# Holdings line: AAPL Apple Inc. 10.000000 $172.50 $1,725.00 $215.00 14.24%
_RH_HOLD_RE = re.compile(
    r"^([A-Z]{1,5})\s+"                 # ticker — strict: uppercase letters only, line start
    r"([A-Za-z0-9 &,\.\-]+?)\s+"        # name
    r"(\d[\d,]*\.\d+)\s+"               # quantity (must have decimal)
    r"\$(\d[\d,]*\.\d+)\s+"             # price
    r"\$(\d[\d,]*\.\d+)"                # total value
    r"(?:\s+(-?\$?[\d,\.]+\(?\)?)?"     # gain/loss optional
    r"(?:\s+([-\d\.]+)%)?)?",           # gain/loss % optional
    re.IGNORECASE | re.MULTILINE,
)


def _split_sections(text: str) -> dict[str, str]:
    """Split statement into named sections for targeted parsing."""
    section_headers = re.compile(
        r"^(HOLDINGS|ACCOUNT ACTIVITY|PORTFOLIO SUMMARY|ACCOUNT VALUE|DIVIDENDS?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    sections: dict[str, str] = {"_preamble": ""}
    current = "_preamble"
    last_end = 0
    for m in section_headers.finditer(text):
        sections[current] = text[last_end:m.start()]
        current = m.group(1).upper().split()[0]  # ACCOUNT → from "ACCOUNT ACTIVITY"
        last_end = m.end()
    sections[current] = text[last_end:]
    return sections


def parse_robinhood(text: str, source_file: str) -> tuple[list[InvestmentTransaction], list[InvestmentHolding]]:
    transactions: list[InvestmentTransaction] = []
    holdings: list[InvestmentHolding] = []
    account = _extract_account_number(text, r"account\s*(?:number|#|no\.?)[:\s]+([A-Z0-9\-]+)", "Robinhood")
    as_of = _extract_as_of_date(text)

    sections = _split_sections(text)

    # ---- Parse transactions from ACCOUNT section only ----
    activity_text = sections.get("ACCOUNT", "") or sections.get("_preamble", "") or text
    for m in _RH_TX_RE.finditer(activity_text):
        date = _parse_date(m.group(1))
        if not date:
            continue
        tx_type = _normalise_tx_type(m.group(4))
        qty = _parse_amount(m.group(5)) if m.group(5) else None
        price = _parse_amount(m.group(6)) if m.group(6) else None
        amt = _parse_amount(m.group(7))
        if amt is None:
            continue
        transactions.append(InvestmentTransaction(
            date=date,
            transaction_type=tx_type,
            ticker=m.group(2).strip(),
            name=m.group(3).strip(),
            quantity=qty,
            price_per_unit=price,
            total_value=abs(amt),
            account=account,
            broker="robinhood",
        ))

    # Non-ticker deposits (ACH etc.)
    for m in _RH_NOTX_RE.finditer(activity_text):
        date = _parse_date(m.group(1))
        if not date:
            continue
        amt = _parse_amount(m.group(4))
        if amt is None:
            continue
        tx_type = _normalise_tx_type(m.group(3))
        transactions.append(InvestmentTransaction(
            date=date,
            transaction_type=tx_type,
            ticker=None,
            name=m.group(2).strip(),
            quantity=None,
            price_per_unit=None,
            total_value=abs(amt),
            account=account,
            broker="robinhood",
        ))

    # ---- Parse holdings from HOLDINGS section only ----
    holdings_text = sections.get("HOLDINGS", "")
    for m in _RH_HOLD_RE.finditer(holdings_text):
        qty = _parse_amount(m.group(3))
        price = _parse_amount(m.group(4))
        total = _parse_amount(m.group(5))
        if total is None:
            continue
        gl_raw = m.group(6)
        gl = _parse_amount(gl_raw.replace("$", "")) if gl_raw else None
        glp_raw = m.group(7)
        glp = float(glp_raw) if glp_raw else None
        holdings.append(InvestmentHolding(
            as_of_date=as_of,
            ticker=m.group(1).strip(),
            name=m.group(2).strip(),
            quantity=qty,
            price=price,
            total_value=total,
            gain_loss=gl,
            gain_loss_pct=glp,
            account=account,
            broker="robinhood",
        ))

    return transactions, holdings


# ---------------------------------------------------------------------------
# Schwab / ThinkOrSwim parser
# ---------------------------------------------------------------------------

# Schwab brokerage confirmation line:
#   01/15/2024   Bought   100   AAPL   @$185.20   $18,520.00
_SCHWAB_TX_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"(Bought|Sold|Dividend\s+Received|Interest\s+Credit|Wire\s+\w+|Funds\s+\w+|Transfer\s+\w+|Margin|Fee)\s+"
    r"([\d,\.]+)?\s*"
    r"([A-Z]{1,5})?\s*"
    r"(?:@\$?([\d,\.]+))?\s*"
    r"\$?([\d,\.]+)",
    re.IGNORECASE,
)

# Schwab holdings: AAPL   Apple Inc.   100   $185.20   $18,520.00   $520.00   2.89%
_SCHWAB_HOLD_RE = re.compile(
    r"([A-Z]{1,5})\s+"
    r"([A-Za-z &,\.\-]+?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+"
    r"\$?([\d,]+\.\d+)\s+"
    r"\$?([\d,]+\.\d+)\s+"
    r"(\(?\$?[\d,]+\.\d+\)?)?\s*"
    r"([\-\d\.]+%)?",
    re.IGNORECASE,
)


def parse_schwab(text: str, source_file: str) -> tuple[list[InvestmentTransaction], list[InvestmentHolding]]:
    transactions = []
    holdings = []
    account = _extract_account_number(text, r"account\s*(?:number|#|no\.?)[:\s]+([A-Z0-9\-]+)", "Schwab")
    as_of = _extract_as_of_date(text)

    for m in _SCHWAB_TX_RE.finditer(text):
        date = _parse_date(m.group(1))
        if not date:
            continue
        tx_type = _normalise_tx_type(m.group(2))
        qty = _parse_amount(m.group(3)) if m.group(3) else None
        ticker = m.group(4).strip() if m.group(4) else None
        price = _parse_amount(m.group(5)) if m.group(5) else None
        amt = _parse_amount(m.group(6))
        if amt is None:
            continue
        transactions.append(InvestmentTransaction(
            date=date,
            transaction_type=tx_type,
            ticker=ticker,
            name=None,
            quantity=qty,
            price_per_unit=price,
            total_value=abs(amt),
            account=account,
            broker="schwab",
        ))

    for m in _SCHWAB_HOLD_RE.finditer(text):
        qty = _parse_amount(m.group(3))
        price = _parse_amount(m.group(4))
        total = _parse_amount(m.group(5))
        if total is None:
            continue
        gl_raw = m.group(6)
        gl = _parse_amount(gl_raw) if gl_raw else None
        glp_raw = m.group(7)
        glp = float(glp_raw.replace("%", "")) if glp_raw else None
        holdings.append(InvestmentHolding(
            as_of_date=as_of,
            ticker=m.group(1).strip(),
            name=m.group(2).strip(),
            quantity=qty,
            price=price,
            total_value=total,
            gain_loss=gl,
            gain_loss_pct=glp,
            account=account,
            broker="schwab",
        ))

    return transactions, holdings


# ---------------------------------------------------------------------------
# Fidelity 401K / NetBenefits parser
# ---------------------------------------------------------------------------

# Fidelity transaction line (NetBenefits):
#   01/15/2024   Employee Contribution   FXAIX   Fidelity 500 Index   100.000   $148.72   $14,872.00
_FID_TX_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"(Employee\s+Contribution|Employer\s+Match|Rollover|Withdrawal|Dividend\s+Reinvested|Exchange|Transfer\s+\w+|Purchase|Redemption|Fee)\s+"
    r"([A-Z]{1,5})?\s*"
    r"([A-Za-z &,\.\-0-9]+?)\s+"
    r"([\d,\.]+)\s+"
    r"\$?([\d,\.]+)\s+"
    r"\$?([\d,\.]+)",
    re.IGNORECASE,
)

# Fidelity holdings line:
#   FXAIX   Fidelity 500 Index Fund   500.000   $148.72   $74,360.00   $4,360.00   6.23%
_FID_HOLD_RE = re.compile(
    r"([A-Z]{1,5})\s+"
    r"([A-Za-z &,\.\-0-9]+?)\s+"
    r"([\d,]+\.\d+)\s+"
    r"\$?([\d,]+\.\d+)\s+"
    r"\$?([\d,]+\.\d+)\s+"
    r"(\(?\$?[\d,]+\.\d+\)?)?\s*"
    r"([\-\d\.]+%)?",
    re.IGNORECASE,
)


def parse_fidelity(text: str, source_file: str) -> tuple[list[InvestmentTransaction], list[InvestmentHolding]]:
    transactions = []
    holdings = []
    account = _extract_account_number(text, r"account\s*(?:number|#|no\.?)[:\s]+([A-Z0-9\-]+)", "Fidelity 401K")
    as_of = _extract_as_of_date(text)

    for m in _FID_TX_RE.finditer(text):
        date = _parse_date(m.group(1))
        if not date:
            continue
        tx_type = _normalise_tx_type(m.group(2))
        ticker = m.group(3).strip() if m.group(3) else None
        name = m.group(4).strip() if m.group(4) else None
        qty = _parse_amount(m.group(5)) if m.group(5) else None
        price = _parse_amount(m.group(6)) if m.group(6) else None
        amt = _parse_amount(m.group(7))
        if amt is None:
            continue
        transactions.append(InvestmentTransaction(
            date=date,
            transaction_type=tx_type,
            ticker=ticker,
            name=name,
            quantity=qty,
            price_per_unit=price,
            total_value=abs(amt),
            account=account,
            broker="fidelity",
        ))

    for m in _FID_HOLD_RE.finditer(text):
        qty = _parse_amount(m.group(3))
        price = _parse_amount(m.group(4))
        total = _parse_amount(m.group(5))
        if total is None:
            continue
        gl_raw = m.group(6)
        gl = _parse_amount(gl_raw) if gl_raw else None
        glp_raw = m.group(7)
        glp = float(glp_raw.replace("%", "")) if glp_raw else None
        holdings.append(InvestmentHolding(
            as_of_date=as_of,
            ticker=m.group(1).strip(),
            name=m.group(2).strip(),
            quantity=qty,
            price=price,
            total_value=total,
            gain_loss=gl,
            gain_loss_pct=glp,
            account=account,
            broker="fidelity",
        ))

    return transactions, holdings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_account_number(text: str, pattern: str, default: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return default


def _extract_as_of_date(text: str) -> str:
    patterns = [
        r"as\s+of\s+(\w+\s+\d{1,2},?\s+\d{4})",
        r"statement\s+(?:period|date)[:\s]+(\d{2}/\d{2}/\d{4})",
        r"period\s+ending[:\s]+(\d{2}/\d{2}/\d{4})",
        r"(?:portfolio|account)\s+(?:value|summary)\s+as\s+of\s+(\w+\s+\d{1,2},?\s+\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            parsed = _parse_date(m.group(1))
            if parsed:
                return parsed
    return datetime.now().strftime("%Y-%m-%d")


_TX_TYPE_MAP = {
    "bought": "buy",
    "buy": "buy",
    "purchase": "buy",
    "sold": "sell",
    "sell": "sell",
    "redemption": "sell",
    "dividend": "dividend",
    "dividend received": "dividend",
    "dividend reinvested": "dividend",
    "interest credit": "dividend",
    "employee contribution": "contribution",
    "employer match": "contribution",
    "rollover": "transfer",
    "transfer": "transfer",
    "wire": "transfer",
    "exchange": "transfer",
    "deposit": "deposit",
    "ach deposit": "deposit",
    "withdrawal": "withdrawal",
    "funds received": "deposit",
    "margin": "fee",
    "fee": "fee",
}


def _normalise_tx_type(raw: str) -> str:
    key = raw.strip().lower()
    for k, v in _TX_TYPE_MAP.items():
        if key.startswith(k):
            return v
    return "other"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def is_investment_pdf(path: Path) -> bool:
    """Quick check: does this PDF look like an investment statement?"""
    try:
        text = _extract_text(path)
        return detect_broker(text) is not None
    except Exception:
        return False


def parse_investment_pdf(path: Path) -> InvestmentParseResult:
    file_hash = _file_hash(path)
    try:
        text = _extract_text(path)
    except Exception as exc:
        return InvestmentParseResult(
            success=False, broker="unknown", account="",
            file_hash=file_hash, failure_reason=str(exc),
        )

    broker = detect_broker(text)
    if not broker:
        return InvestmentParseResult(
            success=False, broker="unknown", account="",
            file_hash=file_hash,
            failure_reason="Could not identify broker from PDF content",
        )

    parsers = {
        "robinhood": parse_robinhood,
        "schwab": parse_schwab,
        "fidelity": parse_fidelity,
    }

    try:
        txs, holdings = parsers[broker](text, path.name)
    except Exception as exc:
        logger.warning("[InvParser] Parser error for %s: %s", broker, exc)
        return InvestmentParseResult(
            success=False, broker=broker, account="",
            file_hash=file_hash, failure_reason=str(exc),
        )

    account = txs[0].account if txs else (holdings[0].account if holdings else broker.title())

    logger.info("[InvParser] %s | broker=%s | txs=%d | holdings=%d",
                path.name, broker, len(txs), len(holdings))

    return InvestmentParseResult(
        success=True,
        broker=broker,
        account=account,
        file_hash=file_hash,
        transactions=txs,
        holdings=holdings,
    )
