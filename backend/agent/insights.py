"""
Decision-support insights engine.

Three capabilities:
  1. Affordability estimation  — "Can I afford ₹X next month?"
  2. Spend optimisation        — where to cut and by how much
  3. Trend recommendations     — forward-looking personalised advice
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _avg_monthly_spend() -> float:
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            """SELECT AVG(monthly_total) as avg
               FROM (
                 SELECT strftime('%Y-%m', date) as m, SUM(amount) as monthly_total
                 FROM transactions WHERE transaction_type='debit'
                 GROUP BY m
               )"""
        ).fetchone()
    return row["avg"] or 0.0


def _avg_monthly_income() -> float:
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            """SELECT AVG(monthly_total) as avg
               FROM (
                 SELECT strftime('%Y-%m', date) as m, SUM(amount) as monthly_total
                 FROM transactions WHERE transaction_type='credit'
                 GROUP BY m
               )"""
        ).fetchone()
    return row["avg"] or 0.0


def _this_month_spend() -> float:
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount),0) as total FROM transactions
               WHERE transaction_type='debit'
               AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"""
        ).fetchone()
    return row["total"]


def _category_averages() -> dict[str, float]:
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            """SELECT category, AVG(monthly_total) as avg
               FROM (
                 SELECT category, strftime('%Y-%m', date) as m, SUM(amount) as monthly_total
                 FROM transactions WHERE transaction_type='debit'
                 GROUP BY category, m
               )
               GROUP BY category"""
        ).fetchall()
    return {r["category"]: r["avg"] for r in rows}


def _this_month_by_category() -> dict[str, float]:
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            """SELECT category, ROUND(SUM(amount),2) as total
               FROM transactions
               WHERE transaction_type='debit'
               AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
               GROUP BY category"""
        ).fetchall()
    return {r["category"]: r["total"] for r in rows}


def _monthly_trend(months: int = 6) -> list[dict]:
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            """SELECT strftime('%Y-%m', date) as month, ROUND(SUM(amount),2) as total
               FROM transactions WHERE transaction_type='debit'
               GROUP BY month ORDER BY month DESC LIMIT ?""",
            (months,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _recent_charge_alerts(days: int = 30) -> list[dict]:
    """Return charge alerts (duplicate, interest, late fee, suspicious) from the last N days."""
    try:
        from backend.storage.database import db
        with db() as conn:
            rows = conn.execute(
                """SELECT alert_type, severity, description, created_at
                   FROM alerts
                   WHERE alert_type IN ('duplicate_charge','interest_fee','late_fee','suspicious_charge')
                     AND created_at >= datetime('now', ?)
                   ORDER BY created_at DESC""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("[Insights] Could not fetch charge alerts: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 1. Affordability estimation
# ---------------------------------------------------------------------------

@dataclass
class AffordabilityResult:
    amount: float
    affordable: bool
    confidence: str          # "high" / "medium" / "low"
    avg_monthly_spend: float
    avg_monthly_income: float
    this_month_spend: float
    remaining_budget: float
    explanation: str


def estimate_affordability(amount: float) -> AffordabilityResult:
    avg_spend = _avg_monthly_spend()
    avg_income = _avg_monthly_income()
    this_month = _this_month_spend()

    avg_savings = avg_income - avg_spend if avg_income > 0 else 0
    remaining = avg_income - this_month if avg_income > 0 else avg_spend * 0.2

    affordable = amount <= remaining
    if avg_income == 0:
        confidence = "low"
    elif avg_income > 0 and len(_monthly_trend(3)) >= 3:
        confidence = "high"
    else:
        confidence = "medium"

    if affordable:
        explanation = (
            f"Based on your average monthly income (${avg_income:,.0f}) and spending "
            f"so far this month (${this_month:,.0f}), you have approximately "
            f"${remaining:,.0f} available. ${amount:,.0f} appears affordable."
        )
    else:
        shortfall = amount - remaining
        explanation = (
            f"This may be a stretch. You've spent ${this_month:,.0f} this month "
            f"against average income of ${avg_income:,.0f}. "
            f"${amount:,.0f} exceeds estimated remaining budget by ${shortfall:,.0f}. "
            f"Consider spreading across months or cutting ${shortfall/2:,.0f} from discretionary spend."
        )

    return AffordabilityResult(
        amount=amount,
        affordable=affordable,
        confidence=confidence,
        avg_monthly_spend=round(avg_spend, 2),
        avg_monthly_income=round(avg_income, 2),
        this_month_spend=round(this_month, 2),
        remaining_budget=round(remaining, 2),
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# 2. Spend optimisation suggestions
# ---------------------------------------------------------------------------

@dataclass
class OptimisationSuggestion:
    category: str
    current_avg: float
    benchmark_pct: float       # what % of income this category should be
    suggested_target: float
    potential_saving: float
    tip: str


CATEGORY_BENCHMARKS = {
    "Dining":        0.10,
    "Shopping":      0.08,
    "Travel":        0.10,
    "Subscriptions": 0.03,
    "Groceries":     0.12,
    "Utilities":     0.05,
    "Entertainment": 0.05,
}

CATEGORY_TIPS = {
    "Dining":        "Cook at home 2 extra days a week — saves ~30% on dining.",
    "Shopping":      "Try a 48-hour wait rule before non-essential purchases.",
    "Travel":        "Book travel 3–4 weeks early and use reward points.",
    "Subscriptions": "Audit active subscriptions — pause ones unused for 30+ days.",
    "Groceries":     "Plan weekly meals and shop with a list to cut impulse buys.",
    "Utilities":     "Check for bill consolidation or better-rate plans.",
}


def generate_optimisation_suggestions() -> list[OptimisationSuggestion]:
    avg_income = _avg_monthly_income()
    cat_avgs = _category_averages()
    suggestions = []

    for category, benchmark_pct in CATEGORY_BENCHMARKS.items():
        current = cat_avgs.get(category, 0)
        if current == 0:
            continue

        if avg_income > 0:
            target = avg_income * benchmark_pct
        else:
            # Fallback: suggest 20% reduction if no income data
            target = current * 0.80

        if current > target * 1.10:   # >10% above benchmark
            saving = round(current - target, 2)
            suggestions.append(OptimisationSuggestion(
                category=category,
                current_avg=round(current, 2),
                benchmark_pct=int(benchmark_pct * 100),
                suggested_target=round(target, 2),
                potential_saving=saving,
                tip=CATEGORY_TIPS.get(category, f"Review your {category} spend for quick wins."),
            ))

    suggestions.sort(key=lambda s: s.potential_saving, reverse=True)
    return suggestions


# ---------------------------------------------------------------------------
# 3. Trend-based recommendations
# ---------------------------------------------------------------------------

@dataclass
class TrendRecommendation:
    type: str
    title: str
    body: str
    severity: str   # "positive" / "neutral" / "warning"


def generate_anomaly_recommendations() -> list[TrendRecommendation]:
    """
    Generate TrendRecommendation entries for each type of charge anomaly
    detected in the last 30 days (duplicates, interest fees, late fees,
    and suspicious charges).
    """
    alerts = _recent_charge_alerts(days=30)
    if not alerts:
        return []

    # Group by alert_type and collect examples
    grouped: dict[str, list[dict]] = {}
    for alert in alerts:
        grouped.setdefault(alert["alert_type"], []).append(alert)

    recommendations: list[TrendRecommendation] = []

    if "duplicate_charge" in grouped:
        items = grouped["duplicate_charge"]
        count = len(items)
        example = items[0]["description"]
        recommendations.append(TrendRecommendation(
            type="duplicate_charge",
            title=f"{count} potential duplicate charge{'s' if count > 1 else ''} detected",
            body=(
                f"We found {count} possible duplicate transaction{'s' if count > 1 else ''} "
                f"in the last 30 days. Example: {example}. "
                "Review your statements and contact your bank or merchant to dispute any confirmed duplicates."
            ),
            severity="warning",
        ))

    if "interest_fee" in grouped:
        items = grouped["interest_fee"]
        count = len(items)
        recommendations.append(TrendRecommendation(
            type="interest_fee",
            title=f"{count} interest or finance charge{'s' if count > 1 else ''} detected",
            body=(
                f"{count} interest or finance charge{'s were' if count > 1 else ' was'} "
                "recorded in the last 30 days. Paying your full balance before the due date "
                "eliminates revolving interest. Consider setting up autopay for the statement balance."
            ),
            severity="warning",
        ))

    if "late_fee" in grouped:
        items = grouped["late_fee"]
        count = len(items)
        high_severity = sum(1 for a in items if a["severity"] == "high")
        body = (
            f"{count} late payment fee{'s' if count > 1 else ''} detected in the last 30 days"
            + (f", including {high_severity} high-severity penalt{'ies' if high_severity > 1 else 'y'}" if high_severity else "")
            + ". Set up automatic minimum payments to avoid future late fees, and call your lender — "
            "first-time late fees are often waived on request."
        )
        recommendations.append(TrendRecommendation(
            type="late_fee",
            title=f"{count} late fee{'s' if count > 1 else ''} detected",
            body=body,
            severity="warning",
        ))

    if "suspicious_charge" in grouped:
        items = grouped["suspicious_charge"]
        count = len(items)
        example = items[0]["description"]
        recommendations.append(TrendRecommendation(
            type="suspicious_charge",
            title=f"{count} suspicious charge{'s' if count > 1 else ''} flagged",
            body=(
                f"{count} transaction{'s' if count > 1 else ''} matched suspicious patterns "
                f"in the last 30 days. Example: {example}. "
                "Review each charge carefully and initiate a dispute with your card issuer "
                "for any you do not recognise."
            ),
            severity="warning",
        ))

    return recommendations


def generate_trend_recommendations() -> list[TrendRecommendation]:
    trend = _monthly_trend(6)
    cat_avgs = _category_averages()
    this_month = _this_month_by_category()
    avg_income = _avg_monthly_income()
    recommendations: list[TrendRecommendation] = []

    # --- Savings rate trend ---
    avg_spend = _avg_monthly_spend()
    if avg_income > 0:
        savings_rate = (avg_income - avg_spend) / avg_income
        if savings_rate >= 0.20:
            recommendations.append(TrendRecommendation(
                type="savings_rate",
                title="Strong savings rate",
                body=f"You're saving ~{savings_rate:.0%} of income on average. Consider moving surplus to a liquid mutual fund or FD to earn returns.",
                severity="positive",
            ))
        elif savings_rate < 0.05:
            recommendations.append(TrendRecommendation(
                type="savings_rate",
                title="Low savings rate",
                body=f"Your savings rate is ~{savings_rate:.0%}. Aim for at least 20%. Identify the top 2 categories to reduce this month.",
                severity="warning",
            ))

    # --- Spend trend direction ---
    if len(trend) >= 3:
        recent = [t["total"] for t in trend[-3:]]
        if recent[-1] > recent[0] * 1.15:
            recommendations.append(TrendRecommendation(
                type="spend_trend",
                title="Spending trending up",
                body=f"Your monthly spend has grown from ${recent[0]:,.0f} to ${recent[-1]:,.0f} over the last 3 months. Review discretionary categories.",
                severity="warning",
            ))
        elif recent[-1] < recent[0] * 0.90:
            recommendations.append(TrendRecommendation(
                type="spend_trend",
                title="Spending coming down",
                body=f"Your spend dropped from ${recent[0]:,.0f} to ${recent[-1]:,.0f} — good discipline. Keep it up.",
                severity="positive",
            ))

    # --- Subscription creep ---
    sub_avg = cat_avgs.get("Subscriptions", 0)
    if sub_avg > 0 and avg_income > 0 and sub_avg / avg_income > 0.05:
        recommendations.append(TrendRecommendation(
            type="subscription_creep",
            title="Subscription spend above 5% of income",
            body=f"Subscriptions average ${sub_avg:,.0f}/month (~{sub_avg/avg_income:.0%} of income). Audit and pause ones you use less than weekly.",
            severity="warning",
        ))

    # --- EMI stress ---
    emi_avg = cat_avgs.get("EMIs", 0)
    if emi_avg > 0 and avg_income > 0 and emi_avg / avg_income > 0.40:
        recommendations.append(TrendRecommendation(
            type="emi_stress",
            title="High EMI-to-income ratio",
            body=f"EMIs are consuming ~{emi_avg/avg_income:.0%} of income (${emi_avg:,.0f}/month). Financial guidelines suggest keeping this below 40%.",
            severity="warning",
        ))

    # --- Charge anomaly recommendations (duplicates, fees, suspicious) ---
    recommendations.extend(generate_anomaly_recommendations())

    # --- No recommendations ---
    if not recommendations:
        recommendations.append(TrendRecommendation(
            type="all_clear",
            title="Finances look healthy",
            body="No significant trends or risks detected based on your current data. Keep tracking to get more personalised insights.",
            severity="positive",
        ))

    return recommendations
