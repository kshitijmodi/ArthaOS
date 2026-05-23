"""
Parsing validation — runs automatically after every document ingestion.
Checks: sum vs stated total, required fields, date validity, currency consistency.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from backend.ingestion.parser import ParseResult, RawTransaction

logger = logging.getLogger(__name__)

VALID_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ValidationResult:
    status: str   # "pass", "warning", "fail"
    checks: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _check_required_fields(transactions: list[RawTransaction]) -> tuple[bool, list[str]]:
    issues = []
    for i, tx in enumerate(transactions):
        if not tx.date:
            issues.append(f"Row {i}: missing date")
        if not tx.description:
            issues.append(f"Row {i}: missing description")
        if tx.amount is None or tx.amount <= 0:
            issues.append(f"Row {i}: invalid amount {tx.amount}")
    return len(issues) == 0, issues


def _check_dates(transactions: list[RawTransaction]) -> tuple[bool, list[str]]:
    issues = []
    today = datetime.today()
    for i, tx in enumerate(transactions):
        if not VALID_DATE_RE.match(tx.date):
            issues.append(f"Row {i}: date '{tx.date}' not in YYYY-MM-DD format")
            continue
        try:
            dt = datetime.strptime(tx.date, "%Y-%m-%d")
            if dt > today:
                issues.append(f"Row {i}: future date '{tx.date}'")
            if dt.year < 2000:
                issues.append(f"Row {i}: suspiciously old date '{tx.date}'")
        except ValueError:
            issues.append(f"Row {i}: unparseable date '{tx.date}'")
    return len(issues) == 0, issues


def _check_currency(transactions: list[RawTransaction]) -> tuple[bool, list[str]]:
    currencies = {tx.currency for tx in transactions}
    if len(currencies) > 1:
        return False, [f"Multiple currencies detected: {currencies}"]
    return True, []


def _check_sum_vs_total(
    transactions: list[RawTransaction], stated_total: float | None
) -> tuple[bool, list[str]]:
    if stated_total is None:
        return True, []
    debit_sum = sum(tx.amount for tx in transactions if tx.transaction_type == "debit")
    tolerance = stated_total * 0.02  # 2% tolerance for rounding
    if abs(debit_sum - stated_total) > tolerance:
        return False, [
            f"Extracted debit sum {debit_sum:.2f} differs from stated total "
            f"{stated_total:.2f} by {abs(debit_sum - stated_total):.2f}"
        ]
    return True, []


def validate(parse_result: ParseResult) -> ValidationResult:
    result = ValidationResult(status="pass")

    if not parse_result.success:
        result.status = "fail"
        result.errors.append(parse_result.failure_reason)
        return result

    if not parse_result.transactions:
        result.status = "warning"
        result.warnings.append("No transactions found in document.")
        return result

    txns = parse_result.transactions

    fields_ok, field_issues = _check_required_fields(txns)
    result.checks["required_fields"] = fields_ok
    result.warnings.extend(field_issues)

    dates_ok, date_issues = _check_dates(txns)
    result.checks["date_validity"] = dates_ok
    result.warnings.extend(date_issues)

    currency_ok, currency_issues = _check_currency(txns)
    result.checks["currency_consistency"] = currency_ok
    result.warnings.extend(currency_issues)

    sum_ok, sum_issues = _check_sum_vs_total(txns, parse_result.stated_total)
    result.checks["sum_vs_stated_total"] = sum_ok
    if not sum_ok:
        result.warnings.extend(sum_issues)

    # Escalate to warning if any check failed (but not all)
    failed = [k for k, v in result.checks.items() if not v]
    if failed:
        result.status = "warning"

    logger.info(
        "[Validator] %s → %s | checks: %s",
        parse_result.file_path.name,
        result.status,
        result.checks,
    )
    return result
