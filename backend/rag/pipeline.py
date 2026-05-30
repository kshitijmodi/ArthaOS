"""
RAG query pipeline.
Flow: query → FAISS retrieval → structured DB lookup → LLM reasoning → answer.
Structured DB is always checked first; RAG chunks are supplementary context.
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
If the context does not contain enough information to answer, say so clearly.
Never make up numbers. Never access information outside the provided context."""


@dataclass
class QueryResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    sql_context: str = ""
    low_confidence: bool = False


# ---------------------------------------------------------------------------
# Structured DB queries — handle common financial question patterns
# ---------------------------------------------------------------------------

def _sql_context(query: str) -> str:
    """Run targeted SQL queries based on keywords in the user's question."""
    q = query.lower()
    lines: list[str] = []

    with db() as conn:

        # --- Account balances (always inject for balance/account questions) ---
        balance_kw = any(w in q for w in [
            "balance", "account", "how much", "what do i have",
            "401k", "fidelity", "robinhood", "schwab", "bilt",
            "portfolio", "investment", "net worth", "bofa", "wells fargo",
            "bank", "credit card", "cc", "loan",
        ])
        if balance_kw:
            teller_rows = conn.execute(
                """SELECT ta.institution, ta.name, ta.type, ta.subtype,
                          ta.balance_ledger as balance, ta.last_synced_at
                   FROM teller_accounts ta
                   JOIN teller_enrollments te ON ta.enrollment_id = te.enrollment_id
                   WHERE te.status = 'active'
                   ORDER BY ta.institution, ta.type, ta.name"""
            ).fetchall()
            plaid_rows = conn.execute(
                """SELECT institution, name, type, subtype,
                          balance_current as balance, last_synced_at
                   FROM plaid_accounts ORDER BY institution, type, name"""
            ).fetchall()
            all_accounts = [dict(r) for r in teller_rows] + [dict(r) for r in plaid_rows]
            all_accounts.sort(key=lambda r: (r["institution"], r["type"], r["name"]))
            if all_accounts:
                lines.append("Connected account balances:")
                assets, liabilities = 0.0, 0.0
                for r in all_accounts:
                    bal = r["balance"]
                    bal_str = f"${abs(bal):,.2f}" if bal is not None else "N/A"
                    sign = " (liability)" if r["type"] in ("credit", "loan") else ""
                    lines.append(f"  {r['institution']} — {r['name']} ({r['type']}): {bal_str}{sign}")
                    if bal:
                        if r["type"] in ("credit", "loan"):
                            liabilities += abs(bal)
                        else:
                            assets += abs(bal)
                net = assets - liabilities
                lines.append(f"  TOTAL: Assets ${assets:,.2f} | Liabilities ${liabilities:,.2f} | Net ${net:,.2f}")

        # --- Recent alerts (inject when asking about alerts or follow-ups) ---
        alert_kw = any(w in q for w in [
            "alert", "duplicate", "unusual", "anomaly", "overspend", "missing",
            "that charge", "that transaction", "what was", "tell me more",
            "recurring", "fee", "interest", "due", "budget",
        ])
        if alert_kw:
            alert_rows = conn.execute(
                """SELECT alert_type, severity, description, created_at
                   FROM alerts
                   ORDER BY created_at DESC LIMIT 15"""
            ).fetchall()
            if alert_rows:
                lines.append("Recent alerts (newest first):")
                for r in alert_rows:
                    lines.append(f"  [{r['severity'].upper()}] {r['description']} (at {r['created_at']})")

        # --- Income ---
        income_kw = any(w in q for w in ["income", "salary", "paycheck", "payroll", "earn", "deposit", "direct deposit"])
        if income_kw:
            income_rows = conn.execute(
                """SELECT ROUND(SUM(amount),2) as total,
                          strftime('%Y-%m', date) as month
                   FROM transactions
                   WHERE transaction_type='credit' AND category='Income'
                   GROUP BY month ORDER BY month DESC LIMIT 6"""
            ).fetchall()
            if income_rows:
                lines.append("Income by month (recent):")
                for r in income_rows:
                    lines.append(f"  {r['month']}: ${r['total']:,.2f}")
            else:
                lines.append("Income: No income transactions found. BofA (payroll account) may need to be re-connected in Settings.")

        # --- Spending summary ---
        spend_kw = any(w in q for w in ["spend", "spent", "expense", "total", "much", "cost", "paid", "bought"])
        if spend_kw and not balance_kw:
            rows = conn.execute(
                """SELECT category, ROUND(SUM(amount),2) as total
                   FROM transactions WHERE transaction_type='debit'
                   GROUP BY category ORDER BY total DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Spend by category (all time):")
                for r in rows:
                    lines.append(f"  {r['category']}: ${r['total']}")

        # This month spending
        if any(w in q for w in ["this month", "current month", "month so far"]):
            rows = conn.execute(
                """SELECT category, ROUND(SUM(amount),2) as total
                   FROM transactions
                   WHERE transaction_type='debit'
                     AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
                   GROUP BY category ORDER BY total DESC"""
            ).fetchall()
            if rows:
                lines.append("This month's spend by category:")
                for r in rows:
                    lines.append(f"  {r['category']}: ${r['total']}")

        # Last month spending
        if any(w in q for w in ["last month", "previous month"]):
            rows = conn.execute(
                """SELECT category, ROUND(SUM(amount),2) as total
                   FROM transactions
                   WHERE transaction_type='debit'
                     AND strftime('%Y-%m', date) = strftime('%Y-%m', date('now', '-1 month'))
                   GROUP BY category ORDER BY total DESC"""
            ).fetchall()
            if rows:
                lines.append("Last month's spend by category:")
                for r in rows:
                    lines.append(f"  {r['category']}: ${r['total']}")

        # EMIs / loans
        if any(w in q for w in ["emi", "loan payment", "repay"]):
            rows = conn.execute(
                """SELECT description, amount, date FROM transactions
                   WHERE category='EMIs' AND transaction_type='debit'
                   ORDER BY date DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Recent EMI transactions:")
                for r in rows:
                    lines.append(f"  {r['date']} | {r['description']} | ${r['amount']}")

        # Subscriptions
        if any(w in q for w in ["subscription", "recurring charge", "netflix", "jio", "airtel", "spotify"]):
            rows = conn.execute(
                """SELECT description, amount, date FROM transactions
                   WHERE category='Subscriptions' AND transaction_type='debit'
                   ORDER BY date DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Recent subscription charges:")
                for r in rows:
                    lines.append(f"  {r['date']} | {r['description']} | ${r['amount']}")

        # Highest expenses
        if any(w in q for w in ["highest", "largest", "biggest", "top expense"]):
            rows = conn.execute(
                """SELECT date, description, amount, category FROM transactions
                   WHERE transaction_type='debit'
                   ORDER BY amount DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Highest individual expenses:")
                for r in rows:
                    lines.append(f"  {r['date']} | {r['description']} | ${r['amount']} [{r['category']}]")

        # Recent transactions — always include for follow-ups and generic queries
        if not lines or any(w in q for w in ["when", "last", "recent", "date", "charged", "time", "latest", "transaction"]):
            rows = conn.execute(
                """SELECT date, description, amount, category FROM transactions
                   WHERE transaction_type='debit'
                   ORDER BY date DESC LIMIT 20"""
            ).fetchall()
            if rows:
                lines.append("Most recent transactions:")
                for r in rows:
                    lines.append(f"  {r['date']} | {r['description']} | ${r['amount']} [{r['category']}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main query function
# ---------------------------------------------------------------------------

def query(user_query: str, top_k: int = 5, history: list[dict] | None = None) -> QueryResult:
    # 1. Structured DB context (primary source of truth)
    sql_ctx = _sql_context(user_query)

    # 2. FAISS retrieval (supplementary)
    chunks = search(user_query, top_k=top_k)
    low_confidence = any(c.get("score", 1.0) < 0.5 for c in chunks)

    rag_ctx = "\n\n".join(
        f"[Source: {c.get('source','?')}] {c['text']}"
        for c in chunks if c.get("text")
    )

    # 3. Build context block — structured data first
    context_parts = []
    if sql_ctx:
        context_parts.append(f"=== Structured Financial Data ===\n{sql_ctx}")
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
