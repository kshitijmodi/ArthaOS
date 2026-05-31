"""
RAG query pipeline.
Flow: query → FAISS retrieval → structured DB lookup → LLM reasoning → answer.
Structured DB is always checked first; RAG chunks are supplementary context.

Context strategy:
  - Base context (always included): account balances, this month spend summary,
    recent transactions, unread alerts. Ensures follow-up questions always have
    grounding data regardless of how they're phrased.
  - Extended context (keyword-triggered): income history, full category breakdown,
    specific transaction types, etc.
"""
import logging
from dataclasses import dataclass, field

from backend.embeddings.embedder import search
from backend.rag.llm import complete
from backend.storage.database import db

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ArthaOS, a personal financial intelligence assistant for a US-based user.
You answer questions about the user's finances using ONLY the context provided.
All amounts are in US dollars ($). Be concise, precise, and always cite specific amounts and dates.
When answering follow-up questions, use both the context provided AND the conversation history.
If the context does not contain enough information to answer, say so clearly.
Never make up numbers. Never access information outside the provided context."""


@dataclass
class QueryResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    sql_context: str = ""
    low_confidence: bool = False


# ---------------------------------------------------------------------------
# Structured DB queries
# ---------------------------------------------------------------------------

def _base_context(conn) -> list[str]:
    """Always-included context: balances, this month spend, recent txns, alerts."""
    lines = []

    # Account balances — always include so follow-ups like "what about my Bilt?" work
    teller_rows = conn.execute(
        """SELECT ta.institution, ta.name, ta.type, ta.subtype,
                  ta.balance_ledger as balance
           FROM teller_accounts ta
           JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
           WHERE te.status = 'active'
           ORDER BY ta.institution, ta.type, ta.name"""
    ).fetchall()
    plaid_rows = conn.execute(
        """SELECT institution, name, type, subtype, balance_current as balance
           FROM plaid_accounts ORDER BY institution, type, name"""
    ).fetchall()
    all_accounts = [dict(r) for r in teller_rows] + [dict(r) for r in plaid_rows]
    all_accounts.sort(key=lambda r: (r["institution"], r["type"], r["name"]))
    if all_accounts:
        assets, liabilities = 0.0, 0.0
        lines.append("Account balances:")
        for r in all_accounts:
            bal = r["balance"]
            bal_str = f"${abs(bal):,.2f}" if bal is not None else "N/A"
            tag = " [liability]" if r["type"] in ("credit", "loan") else ""
            lines.append(f"  {r['institution']} — {r['name']} ({r['type']}): {bal_str}{tag}")
            if bal:
                if r["type"] in ("credit", "loan"):
                    liabilities += abs(bal)
                else:
                    assets += abs(bal)
        lines.append(f"  Net worth: ${assets - liabilities:,.2f} (assets ${assets:,.2f} - liabilities ${liabilities:,.2f})")

    # This month spend summary
    month_rows = conn.execute(
        """SELECT category, ROUND(SUM(amount),2) as total
           FROM transactions
           WHERE transaction_type='debit'
             AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
           GROUP BY category ORDER BY total DESC LIMIT 8"""
    ).fetchall()
    if month_rows:
        lines.append("This month's spend by category:")
        for r in month_rows:
            lines.append(f"  {r['category']}: ${r['total']:,.2f}")

    # Last month spend summary
    last_month_rows = conn.execute(
        """SELECT category, ROUND(SUM(amount),2) as total
           FROM transactions
           WHERE transaction_type='debit'
             AND strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))
           GROUP BY category ORDER BY total DESC LIMIT 8"""
    ).fetchall()
    if last_month_rows:
        lines.append("Last month's spend by category:")
        for r in last_month_rows:
            lines.append(f"  {r['category']}: ${r['total']:,.2f}")

    # Recent transactions (last 15)
    recent = conn.execute(
        """SELECT date, description, amount, category, transaction_type
           FROM transactions ORDER BY date DESC LIMIT 15"""
    ).fetchall()
    if recent:
        lines.append("Most recent transactions:")
        for r in recent:
            sign = "-" if r["transaction_type"] == "debit" else "+"
            lines.append(f"  {r['date']} | {r['description']} | {sign}${r['amount']:,.2f} [{r['category']}]")

    # Unread alerts (last 10)
    alert_rows = conn.execute(
        """SELECT alert_type, severity, description, created_at
           FROM alerts ORDER BY created_at DESC LIMIT 10"""
    ).fetchall()
    if alert_rows:
        lines.append("Recent alerts:")
        for r in alert_rows:
            lines.append(f"  [{r['severity'].upper()}] {r['description']} ({r['created_at'][:10]})")

    return lines


_CATEGORY_MAP: dict[str, str] = {
    "dining": "Dining", "restaurant": "Dining", "restaurants": "Dining",
    "groceries": "Groceries", "grocery": "Groceries",
    "travel": "Travel", "hotel": "Travel", "hotels": "Travel", "flights": "Travel", "flight": "Travel",
    "utilities": "Utilities", "utility": "Utilities",
    "subscriptions": "Subscriptions", "subscription": "Subscriptions",
    "shopping": "Shopping",
    "rent": "Rent",
    "healthcare": "Healthcare", "medical": "Healthcare",
    "insurance": "Insurance",
    "education": "Education",
    "fees": "Fees & Interest", "interest": "Fees & Interest",
    "transfer": "Transfer", "transfers": "Transfer",
    "emis": "EMIs", "emi": "EMIs", "loans": "EMIs",
    "miscellaneous": "Miscellaneous", "misc": "Miscellaneous",
    "investments": "Investments",
}


def _detect_category(q: str) -> str | None:
    """Return the DB category name if the query targets a specific spend category."""
    for keyword, cat in _CATEGORY_MAP.items():
        if keyword in q:
            return cat
    return None


def _detect_period(q: str) -> tuple[str, str]:
    """Return (period_label, SQL WHERE clause fragment for date column)."""
    if "last month" in q or "previous month" in q:
        return (
            "last month",
            "strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))"
        )
    if "this month" in q or "current month" in q:
        return (
            "this month",
            "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
        )
    if "last 30 days" in q or "past 30 days" in q or "past month" in q:
        return "last 30 days", "date >= date('now', '-30 days')"
    if "last 60 days" in q or "past 60 days" in q or "past 2 months" in q:
        return "last 60 days", "date >= date('now', '-60 days')"
    if "last 90 days" in q or "past 90 days" in q or "past 3 months" in q:
        return "last 90 days", "date >= date('now', '-90 days')"
    if "last week" in q or "past week" in q:
        return "last 7 days", "date >= date('now', '-7 days')"
    if "last year" in q or "past year" in q:
        return "last year", "date >= date('now', '-365 days')"
    # Default: last 2 months so context is recent but not truncated to 15 rows
    return "last 2 months", "date >= date('now', '-60 days')"


def _extended_context(query: str, conn) -> list[str]:
    """Keyword-triggered additional context on top of base."""
    q = query.lower()
    lines = []

    # Category-specific transaction drill-down
    # Triggered when query asks about transactions in a specific category
    target_cat = _detect_category(q)
    drill_keywords = ["transaction", "transactions", "txn", "txns", "spent", "spend", "spending",
                      "show", "list", "give", "all", "breakdown", "detail", "details",
                      "amounting", "amount", "how much", "charges", "charge"]
    if target_cat and any(w in q for w in drill_keywords):
        period_label, period_sql = _detect_period(q)
        rows = conn.execute(
            f"""SELECT date, description, ROUND(amount,2) as amount, category
                FROM transactions
                WHERE transaction_type='debit'
                  AND category = ?
                  AND {period_sql}
                ORDER BY date DESC""",
            (target_cat,),
        ).fetchall()
        if rows:
            total = sum(r["amount"] for r in rows)
            lines.append(f"All {target_cat} transactions ({period_label}) — {len(rows)} transactions totalling ${total:,.2f}:")
            for r in rows:
                lines.append(f"  {r['date']} | {r['description']} | -${r['amount']:,.2f}")
        else:
            lines.append(f"No {target_cat} transactions found for {period_label}.")

    # Income
    if any(w in q for w in ["income", "salary", "paycheck", "payroll", "earn", "deposit", "direct deposit"]):
        rows = conn.execute(
            """SELECT ROUND(SUM(amount),2) as total, strftime('%Y-%m', date) as month
               FROM transactions
               WHERE transaction_type='credit' AND category='Income'
               GROUP BY month ORDER BY month DESC LIMIT 6"""
        ).fetchall()
        if rows:
            lines.append("Income by month:")
            for r in rows:
                lines.append(f"  {r['month']}: ${r['total']:,.2f}")
        else:
            lines.append("Income: No income transactions found. BofA (payroll account) may need reconnecting.")

    # EMIs
    if any(w in q for w in ["emi", "loan payment", "repay", "installment"]):
        rows = conn.execute(
            """SELECT description, amount, date FROM transactions
               WHERE category='EMIs' AND transaction_type='debit'
               ORDER BY date DESC LIMIT 10"""
        ).fetchall()
        if rows:
            lines.append("EMI transactions:")
            for r in rows:
                lines.append(f"  {r['date']} | {r['description']} | ${r['amount']:,.2f}")

    # Subscriptions
    if any(w in q for w in ["subscription", "netflix", "spotify", "hulu", "recurring charge"]):
        rows = conn.execute(
            """SELECT description, amount, date FROM transactions
               WHERE category='Subscriptions' AND transaction_type='debit'
               ORDER BY date DESC LIMIT 10"""
        ).fetchall()
        if rows:
            lines.append("Subscription charges:")
            for r in rows:
                lines.append(f"  {r['date']} | {r['description']} | ${r['amount']:,.2f}")

    # Investments / holdings
    if any(w in q for w in ["stock", "holding", "portfolio", "investment", "robinhood", "schwab", "fidelity", "401k"]):
        rows = conn.execute(
            """SELECT broker, ticker, quantity, current_price, market_value, gain_loss
               FROM plaid_holdings ORDER BY broker, market_value DESC LIMIT 20"""
        ).fetchall()
        if rows:
            lines.append("Investment holdings:")
            for r in rows:
                gl = f" (P/L: ${r['gain_loss']:,.2f})" if r["gain_loss"] is not None else ""
                lines.append(f"  {r['broker']} — {r['ticker']}: {r['quantity']} @ ${r['current_price']:,.2f} = ${r['market_value']:,.2f}{gl}")

    # All-time category totals
    if any(w in q for w in ["all time", "overall", "total ever", "historically"]):
        rows = conn.execute(
            """SELECT category, ROUND(SUM(amount),2) as total
               FROM transactions WHERE transaction_type='debit'
               GROUP BY category ORDER BY total DESC"""
        ).fetchall()
        if rows:
            lines.append("All-time spend by category:")
            for r in rows:
                lines.append(f"  {r['category']}: ${r['total']:,.2f}")

    return lines


def _sql_context(query: str) -> str:
    with db() as conn:
        lines = _base_context(conn)
        lines += _extended_context(query, conn)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main query function
# ---------------------------------------------------------------------------

def query(user_query: str, top_k: int = 5, history: list[dict] | None = None) -> QueryResult:
    # 1. Structured DB context — base always included, extended keyword-triggered
    sql_ctx = _sql_context(user_query)

    # 2. FAISS retrieval (supplementary document context)
    chunks = search(user_query, top_k=top_k)
    low_confidence = any(c.get("score", 1.0) < 0.5 for c in chunks)

    rag_ctx = "\n\n".join(
        f"[Source: {c.get('source','?')}] {c['text']}"
        for c in chunks if c.get("text")
    )

    # 3. Build context block — structured data first
    context_parts = []
    if sql_ctx:
        context_parts.append(f"=== Your Financial Data ===\n{sql_ctx}")
    if rag_ctx:
        context_parts.append(f"=== Document Context ===\n{rag_ctx}")

    if not context_parts:
        return QueryResult(
            answer="I don't have enough financial data to answer that question yet. "
                   "Please connect your accounts in Settings.",
            low_confidence=True,
        )

    context = "\n\n".join(context_parts)
    prompt = f"Context:\n{context}\n\nQuestion: {user_query}\n\nAnswer:"

    answer = complete(prompt, max_tokens=512, system=SYSTEM_PROMPT, history=history)

    return QueryResult(
        answer=answer,
        sources=chunks,
        sql_context=sql_ctx,
        low_confidence=low_confidence,
    )
