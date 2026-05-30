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

SYSTEM_PROMPT = """You are ArthaOS, a personal financial intelligence assistant.
You answer questions about the user's finances using ONLY the context provided.
Be concise, precise, and always cite specific amounts and dates from the context.
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
        # Spending summary
        if any(w in q for w in ["spend", "spent", "expense", "total", "much"]):
            rows = conn.execute(
                """SELECT category, ROUND(SUM(amount),2) as total
                   FROM transactions WHERE transaction_type='debit'
                   GROUP BY category ORDER BY total DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Spend by category (all time):")
                for r in rows:
                    lines.append(f"  {r['category']}: ${r['total']}")

        # This month
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

        # Last month
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

        # EMIs
        if any(w in q for w in ["emi", "loan", "repay"]):
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
        if any(w in q for w in ["subscription", "recurring", "netflix", "jio", "airtel"]):
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
        if any(w in q for w in ["highest", "largest", "biggest", "top"]):
            rows = conn.execute(
                """SELECT date, description, amount, category FROM transactions
                   WHERE transaction_type='debit'
                   ORDER BY amount DESC LIMIT 10"""
            ).fetchall()
            if rows:
                lines.append("Highest individual expenses:")
                for r in rows:
                    lines.append(f"  {r['date']} | {r['description']} | ${r['amount']} [{r['category']}]")

        # Recent transactions for any follow-up or date-related questions
        if not lines or any(w in q for w in ["when", "last", "recent", "date", "charged", "time", "latest"]):
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
                   "Please ingest some bank statements first.",
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
