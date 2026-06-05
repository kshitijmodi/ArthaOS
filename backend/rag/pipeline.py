"""
RAG query pipeline — financially-intelligent context engine.

Architecture:
  1. Intent extraction — understand what the user is asking (query + conversation history)
  2. Precision DB fetch — pull exactly the right data for the detected intent
  3. LLM reasoning — answer with full, grounded context

Context strategy:
  Always injected:
    - Account balances + net worth
    - This month + last month spend summary (ALL categories with counts)
    - Recent 30 transactions

  Intent-driven additions:
    - Category drill-down: ALL transactions for the detected category + time period
      (no row limit — user gets the complete list with a verified total)
    - Month comparison: side-by-side this-vs-last for every category
    - Income: monthly income totals for last 6 months
    - Investment holdings: full portfolio from Plaid

  History inheritance:
    - If the current query is a follow-up ("those transactions", "break it down")
      without an explicit category/period, we inherit both from recent history turns.
"""
import re
import logging
from dataclasses import dataclass, field

from backend.embeddings.embedder import search
from backend.rag.llm import complete
from backend.storage.database import db

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ArthaOS — this user's personal financial analyst with full access to their real financial data.

Your role:
- Answer any question about their finances using their actual data provided in context
- For investment/portfolio questions: give specific insights referencing their actual holdings, amounts, and performance
- For advice questions (what to invest in, how to save more, where to cut): combine their real data with sound financial principles to give personalized, actionable answers
- For spending questions: reference exact amounts, categories, dates, and merchants
- For follow-up questions: use conversation history — the user expects you to remember the conversation
- If specific data is missing, say so briefly and move on — don't refuse to help

Rules:
- All amounts are US dollars ($)
- Never invent transactions or balances — use only what's in the context
- When a verified total is in context, use it exactly
- Be direct and specific — reference their actual numbers, not generic percentages
- Do NOT say "I cannot provide financial advice" — you are analyzing THEIR OWN data to help them
- If asked about stocks to buy/sell: look at their portfolio, their spending, their cash position, and give a considered personal analysis"""


@dataclass
class QueryResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    sql_context: str = ""
    low_confidence: bool = False


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

_CAT_KEYWORDS: dict[str, str] = {
    "rent": "Rent", "lease": "Rent",
    "groceries": "Groceries", "grocery": "Groceries",
    "supermarket": "Groceries", "shoprite": "Groceries",
    "dining": "Dining", "restaurant": "Dining", "restaurants": "Dining",
    "eating out": "Dining", "eating": "Dining",
    "travel": "Travel", "hotel": "Travel", "hotels": "Travel",
    "flight": "Travel", "flights": "Travel",
    "airline": "Travel", "airlines": "Travel", "airfare": "Travel",
    "utilities": "Utilities", "utility": "Utilities", "electric": "Utilities",
    "internet": "Utilities", "phone bill": "Utilities",
    "subscriptions": "Subscriptions", "subscription": "Subscriptions",
    "streaming": "Subscriptions",
    "shopping": "Shopping",
    "healthcare": "Healthcare", "medical": "Healthcare",
    "pharmacy": "Healthcare", "doctor": "Healthcare",
    "insurance": "Insurance",
    "education": "Education",
    "transfer": "Transfer", "transfers": "Transfer",
    "emi": "EMIs", "emis": "EMIs",
    "loan payment": "EMIs", "loan": "EMIs",
    "miscellaneous": "Miscellaneous", "misc": "Miscellaneous",
    "fees": "Fees & Interest", "interest": "Fees & Interest",
    "income": "Income", "salary": "Income", "paycheck": "Income",
    "payroll": "Income",
}

# All valid DB category names (for direct-name matching in history/responses)
_ALL_CAT_NAMES = {
    "Rent", "Groceries", "Dining", "Travel", "Utilities", "Subscriptions",
    "Insurance", "EMIs", "Shopping", "Healthcare", "Education", "Income",
    "Transfer", "Fees & Interest", "Miscellaneous", "Investments",
}

# Strong signals that user wants a transaction list, not just a total
_DRILL_STRONG = frozenset([
    "transaction", "transactions", "txn", "txns",
    "those", "them", "these", "it",
    "list", "breakdown", "break down", "break it down",
    "itemize", "itemized", "individual",
    "amounting", "making up", "adding up",
    "details", "detail", "charges",
])

# Weaker signals — only trigger drill if a category is also present
_DRILL_WEAK = frozenset(["show", "give", "all", "what are"])

_MONTH_NAMES: dict[str, str] = {
    "january": "01", "jan": "01", "february": "02", "feb": "02",
    "march": "03", "mar": "03", "april": "04", "apr": "04",
    "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
    "august": "08", "aug": "08", "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10", "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


# ---------------------------------------------------------------------------
# Intent extraction helpers
# ---------------------------------------------------------------------------

def _categories_in_text(text: str) -> list[str]:
    """Extract DB category names from arbitrary text. Returns unique, ordered list."""
    t = text.lower()
    found: list[str] = []
    seen: set[str] = set()

    # Direct DB category name matches first (most reliable)
    for cat in _ALL_CAT_NAMES:
        if cat.lower() in t and cat not in seen:
            found.append(cat)
            seen.add(cat)

    # Keyword mappings
    for kw, cat in _CAT_KEYWORDS.items():
        if kw in t and cat not in seen:
            found.append(cat)
            seen.add(cat)

    return found


def _detect_period(text: str) -> tuple[str, str] | None:
    """
    Returns (human_label, SQL WHERE fragment on `date`) or None.
    """
    t = text.lower()

    if "last month" in t or "previous month" in t:
        return ("last month",
                "strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))")
    if "this month" in t or "current month" in t:
        return ("this month",
                "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')")
    if "last week" in t or "past week" in t or "this week" in t:
        return ("last 7 days", "date >= date('now', '-7 days')")
    if "last 30 days" in t or "past 30 days" in t:
        return ("last 30 days", "date >= date('now', '-30 days')")
    if "last 60 days" in t or "past 60 days" in t or "last 2 months" in t:
        return ("last 60 days", "date >= date('now', '-60 days')")
    if "last 90 days" in t or "past 90 days" in t or "last 3 months" in t:
        return ("last 90 days", "date >= date('now', '-90 days')")
    if "last 6 months" in t or "past 6 months" in t:
        return ("last 6 months", "date >= date('now', '-180 days')")
    if "last year" in t or "past year" in t:
        return ("last 12 months", "date >= date('now', '-365 days')")
    if any(w in t for w in ("all time", "all-time", "overall", "total ever",
                             "historically", "ever spent", "lifetime")):
        return ("all time", "1=1")

    # Named month: "in april", "last april", "in may 2026", etc.
    for month_name, month_num in _MONTH_NAMES.items():
        if month_name in t:
            year_m = re.search(r'\b(202[0-9])\b', t)
            if year_m:
                ym = f"{year_m.group(1)}-{month_num}"
                return (f"{month_name.title()} {year_m.group(1)}",
                        f"strftime('%Y-%m', date) = '{ym}'")
            return (month_name.title(),
                    f"strftime('%m', date) = '{month_num}' AND date >= date('now', '-400 days')")

    return None


def _inherit_period_from_history(history: list[dict]) -> tuple[str, str] | None:
    """Scan recent history (newest first) for a time period mention."""
    for msg in reversed(history[-6:]):
        p = _detect_period(msg.get("content", ""))
        if p:
            return p
    return None


def _inherit_categories_from_history(history: list[dict], n_turns: int = 2) -> list[str]:
    """Extract categories mentioned in the last n_turns of conversation."""
    seen: set[str] = set()
    cats: list[str] = []
    for msg in reversed(history[-(n_turns * 2):]):
        for c in _categories_in_text(msg.get("content", "")):
            if c not in seen:
                cats.append(c)
                seen.add(c)
    return cats


def _is_drill_down(q: str, has_categories: bool) -> bool:
    if any(s in q for s in _DRILL_STRONG):
        return True
    if has_categories and any(s in q for s in _DRILL_WEAK):
        return True
    return False


@dataclass
class _Intent:
    categories: list[str]
    period_label: str
    period_sql: str
    drill_down: bool
    needs_income: bool
    needs_investment: bool
    needs_comparison: bool


_DEFAULT_PERIOD = (
    "last 2 months",
    "date >= date('now', '-60 days')",
)


def _parse_intent(query: str, history: list[dict]) -> _Intent:
    q = query.lower()

    # Categories from current query
    cats = _categories_in_text(q)

    # Drill-down intent
    drill = _is_drill_down(q, bool(cats))

    # If drill-down but no explicit category, inherit from history
    if drill and not cats:
        cats = _inherit_categories_from_history(history)

    # Time period: current query first, then history, then default
    period = _detect_period(q)
    if period is None and (drill or cats):
        period = _inherit_period_from_history(history)
    if period is None:
        period = _DEFAULT_PERIOD
    period_label, period_sql = period

    needs_income = any(w in q for w in [
        "income", "salary", "paycheck", "payroll", "earn",
        "direct deposit", "how much did i make", "how much i made",
    ])
    needs_investment = any(w in q for w in [
        "stock", "stocks", "holding", "holdings", "portfolio", "robinhood",
        "schwab", "fidelity", "401k", "brokerage", "invest", "investment",
        "recommend", "advice", "diversif", "allocat", "rebalance",
        "buy", "sell", "etf", "mutual fund", "net worth",
    ])
    needs_comparison = any(w in q for w in [
        "compare", " vs ", "versus", "difference between",
        "more than last", "less than last", "change from last",
        "month over month", "month-over-month",
    ])

    return _Intent(
        categories=cats,
        period_label=period_label,
        period_sql=period_sql,
        drill_down=drill,
        needs_income=needs_income,
        needs_investment=needs_investment,
        needs_comparison=needs_comparison,
    )


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _ctx_balances(conn) -> list[str]:
    teller = conn.execute(
        """SELECT ta.institution, ta.name, ta.type, ta.subtype, ta.balance_ledger as bal
           FROM teller_accounts ta
           JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
           WHERE te.status = 'active'
           ORDER BY ta.institution, ta.type, ta.name"""
    ).fetchall()
    plaid = conn.execute(
        """SELECT institution, name, type, subtype, balance_current as bal
           FROM plaid_accounts ORDER BY institution, type, name"""
    ).fetchall()

    all_accs = sorted(
        [dict(r) for r in teller] + [dict(r) for r in plaid],
        key=lambda r: (r["institution"], r["type"], r["name"]),
    )
    if not all_accs:
        return []

    lines = ["=== Account Balances ==="]
    assets = liabilities = 0.0
    for r in all_accs:
        bal = r["bal"] or 0.0
        bal_str = f"${abs(bal):,.2f}" if r["bal"] is not None else "N/A"
        tag = " [LIABILITY]" if r["type"] in ("credit", "loan") else ""
        lines.append(f"  {r['institution']} — {r['name']} ({r['type']}): {bal_str}{tag}")
        if r["type"] in ("credit", "loan"):
            liabilities += abs(bal)
        else:
            assets += abs(bal)
    lines.append(
        f"  >> Net worth: ${assets - liabilities:,.2f}"
        f"  (assets ${assets:,.2f} − liabilities ${liabilities:,.2f})"
    )
    return lines


def _ctx_spend_summary(conn) -> list[str]:
    """This month + last month spend by ALL categories with transaction counts."""
    lines = ["=== Spending Summary ==="]

    this_rows = conn.execute(
        """SELECT category, ROUND(SUM(amount),2) as total, COUNT(*) as cnt
           FROM transactions
           WHERE transaction_type='debit'
             AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
           GROUP BY category ORDER BY total DESC"""
    ).fetchall()

    last_rows = conn.execute(
        """SELECT category, ROUND(SUM(amount),2) as total, COUNT(*) as cnt
           FROM transactions
           WHERE transaction_type='debit'
             AND strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))
           GROUP BY category ORDER BY total DESC"""
    ).fetchall()

    if this_rows:
        grand = sum(r["total"] for r in this_rows)
        lines.append(f"This month — ${grand:,.2f} total spend:")
        for r in this_rows:
            lines.append(f"  {r['category']}: ${r['total']:,.2f} ({r['cnt']} txns)")

    if last_rows:
        grand = sum(r["total"] for r in last_rows)
        lines.append(f"Last month — ${grand:,.2f} total spend:")
        for r in last_rows:
            lines.append(f"  {r['category']}: ${r['total']:,.2f} ({r['cnt']} txns)")

    return lines


def _ctx_recent_transactions(conn, limit: int = 30) -> list[str]:
    rows = conn.execute(
        """SELECT date, description, amount, category, transaction_type
           FROM transactions ORDER BY date DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    if not rows:
        return []
    lines = [f"=== Most Recent {limit} Transactions ==="]
    for r in rows:
        sign = "-" if r["transaction_type"] == "debit" else "+"
        lines.append(
            f"  {r['date']} | {r['description']} | {sign}${r['amount']:,.2f} [{r['category']}]"
        )
    return lines


def _ctx_category_drill(categories: list[str], period_label: str, period_sql: str, conn) -> list[str]:
    """ALL transactions for each requested category in the given period."""
    lines = []
    for cat in categories:
        rows = conn.execute(
            f"""SELECT date, description, ROUND(amount,2) as amount
                FROM transactions
                WHERE transaction_type='debit' AND category=? AND {period_sql}
                ORDER BY date DESC""",
            (cat,),
        ).fetchall()
        if rows:
            total = sum(r["amount"] for r in rows)
            lines.append(
                f"=== {cat} — {period_label} "
                f"({len(rows)} transactions, ${total:,.2f} total) ==="
            )
            for r in rows:
                lines.append(f"  {r['date']} | {r['description']} | -${r['amount']:,.2f}")
        else:
            lines.append(f"=== {cat} — {period_label}: no transactions found ===")
    return lines


def _ctx_comparison(conn) -> list[str]:
    rows = conn.execute(
        """SELECT
             category,
             ROUND(SUM(CASE WHEN strftime('%Y-%m',date)=strftime('%Y-%m','now')
                            THEN amount ELSE 0 END), 2) as this_m,
             ROUND(SUM(CASE WHEN strftime('%Y-%m',date)=strftime('%Y-%m',date('now','-1 month'))
                            THEN amount ELSE 0 END), 2) as last_m
           FROM transactions
           WHERE transaction_type='debit' AND date >= date('now','-60 days')
           GROUP BY category HAVING this_m > 0 OR last_m > 0
           ORDER BY (this_m + last_m) DESC"""
    ).fetchall()
    if not rows:
        return []
    lines = ["=== Month-over-Month Comparison ===",
             "  Category                | This Month   | Last Month   | Change"]
    for r in rows:
        change = r["this_m"] - r["last_m"]
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
        lines.append(
            f"  {r['category']:<24}| ${r['this_m']:>10,.2f} | ${r['last_m']:>10,.2f}"
            f" | {arrow} ${abs(change):,.2f}"
        )
    return lines


def _ctx_income(conn) -> list[str]:
    rows = conn.execute(
        """SELECT strftime('%Y-%m', date) as month,
                  ROUND(SUM(amount),2) as total, COUNT(*) as cnt
           FROM transactions
           WHERE transaction_type='credit' AND category='Income'
           GROUP BY month ORDER BY month DESC LIMIT 12"""
    ).fetchall()
    if not rows:
        return ["=== Income === No income transactions found. "
                "(BofA payroll account may need reconnecting in Settings.)"]
    lines = ["=== Income History ==="]
    for r in rows:
        lines.append(f"  {r['month']}: ${r['total']:,.2f} ({r['cnt']} deposits)")
    return lines


def _ctx_investments(conn) -> list[str]:
    rows = conn.execute(
        """SELECT broker, ticker, name, quantity, price, total_value,
                  gain_loss, gain_loss_day, account
           FROM investment_holdings h
           WHERE h.as_of_date = (
               SELECT MAX(as_of_date) FROM investment_holdings h2
               WHERE h2.broker = h.broker AND h2.account = h.account
           )
           ORDER BY broker, total_value DESC"""
    ).fetchall()
    if not rows:
        return ["=== Investments — No holdings data ==="]
    lines = ["=== Investment Holdings ==="]
    current_broker = None
    broker_total = 0.0
    for r in rows:
        if r["broker"] != current_broker:
            if current_broker:
                lines.append(f"  {current_broker} subtotal: ${broker_total:,.2f}")
            current_broker = r["broker"]
            broker_total = 0.0
            lines.append(f"  [{r['broker']} — {r['account']}]")
        mv = r["total_value"] or 0.0
        broker_total += mv
        day_gl = f" | day: ${r['gain_loss_day']:,.2f}" if r["gain_loss_day"] else ""
        price_str = f" @ ${r['price']:,.2f}" if r["price"] else ""
        lines.append(
            f"    {r['ticker'] or r['name']}: {r['quantity']}{price_str}"
            f" = ${mv:,.2f}{day_gl}"
        )
    if current_broker:
        lines.append(f"  {current_broker} subtotal: ${broker_total:,.2f}")
    return lines


def _ctx_alerts(conn, limit: int = 10) -> list[str]:
    rows = conn.execute(
        """SELECT alert_type, severity, description, created_at
           FROM alerts ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    if not rows:
        return []
    lines = ["=== Recent Alerts ==="]
    for r in rows:
        lines.append(
            f"  [{r['severity'].upper()}] {r['alert_type']}: "
            f"{r['description']} ({r['created_at'][:10]})"
        )
    return lines


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def _build_context(query: str, history: list[dict] | None, conn) -> str:
    history = history or []
    intent = _parse_intent(query, history)

    sections: list[str] = []

    # Always: balances
    sections.extend(_ctx_balances(conn))

    # Always: spend summary (all categories, this + last month)
    sections.extend(_ctx_spend_summary(conn))

    # Month comparison if asked
    if intent.needs_comparison:
        sections.extend(_ctx_comparison(conn))

    # Category drill-down: full transaction list
    if intent.categories and intent.drill_down:
        sections.extend(_ctx_category_drill(
            intent.categories, intent.period_label, intent.period_sql, conn
        ))
    elif intent.categories and not intent.drill_down:
        # User asked about a category (e.g. "how much did I spend on dining?")
        # Spend summary already covers this month/last month.
        # Add the full period breakdown if they specified a period beyond that.
        if intent.period_label not in ("this month", "last month", "last 2 months"):
            sections.extend(_ctx_category_drill(
                intent.categories, intent.period_label, intent.period_sql, conn
            ))

    # Recent transactions: skip if we already injected full category data
    if not (intent.categories and intent.drill_down):
        sections.extend(_ctx_recent_transactions(conn, limit=30))

    # Income history
    if intent.needs_income:
        sections.extend(_ctx_income(conn))

    # Investment holdings
    if intent.needs_investment:
        sections.extend(_ctx_investments(conn))

    # Recent alerts — always include (compact)
    sections.extend(_ctx_alerts(conn, limit=10))

    return "\n".join(sections)


def _sql_context(query: str, history: list[dict] | None = None) -> str:
    with db() as conn:
        return _build_context(query, history, conn)


# ---------------------------------------------------------------------------
# Main query entry point
# ---------------------------------------------------------------------------

def query(user_query: str, top_k: int = 3, history: list[dict] | None = None) -> QueryResult:
    with db() as conn:
        sql_ctx = _build_context(user_query, history, conn)

    # FAISS supplementary context (reduced top_k since DB context is now comprehensive)
    chunks = search(user_query, top_k=top_k)
    low_confidence = any(c.get("score", 1.0) < 0.5 for c in chunks)

    rag_ctx = "\n\n".join(
        f"[Source: {c.get('source', '?')}] {c['text']}"
        for c in chunks if c.get("text")
    )

    context_parts: list[str] = []
    if sql_ctx:
        context_parts.append(sql_ctx)
    if rag_ctx:
        context_parts.append(f"=== Additional Context ===\n{rag_ctx}")

    if not context_parts:
        return QueryResult(
            answer=(
                "I don't have enough financial data yet. "
                "Please connect your accounts in Settings and run a sync."
            ),
            low_confidence=True,
        )

    context = "\n\n".join(context_parts)
    prompt = f"Financial Context:\n{context}\n\nUser Question: {user_query}\n\nAnswer:"

    answer = complete(prompt, max_tokens=1000, system=SYSTEM_PROMPT, history=history)

    return QueryResult(
        answer=answer,
        sources=chunks,
        sql_context=sql_ctx,
        low_confidence=low_confidence,
    )
