"""
Categorization engine — hybrid rule-based + LLM fallback.
Lookup order: user correction → keyword rules → LLM fallback.
"""
import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword rules — merchant keywords → category
# ---------------------------------------------------------------------------

RULES: list[tuple[re.Pattern, str]] = [
    # Food & Groceries
    (re.compile(r"big\s*bazaar|dmart|reliance\s*fresh|zepto|blinkit|grofer|swiggy\s*instamart|nature['\s]s\s*basket|spencer|lulu|bigbasket|more\s*supermart", re.I), "Groceries"),
    # Dining
    (re.compile(r"swiggy|zomato|domino|pizza\s*hut|mcdonald|kfc|burger\s*king|cafe\s*coffee|starbucks|subway|haldiram|barbeque\s*nation|restaurant|eatery|bistro|dine", re.I), "Dining"),
    # Transport
    (re.compile(r"uber|ola\b|rapido|metro|irctc|indian\s*railways|makemytrip|redbus|yatra|cleartrip|indigo|air\s*india|spicejet|vistara|goair|petrol|fuel|hp\s*petrol|indian\s*oil|bharat\s*petroleum", re.I), "Travel"),
    # Utilities
    (re.compile(r"electricity|bescom|msedcl|tata\s*power|adani\s*electricity|water\s*board|bwssb|gas\s*bill|mahanagar\s*gas|igl\b|piped\s*gas", re.I), "Utilities"),
    # Telecom / subscriptions
    (re.compile(r"\bjio\b|airtel|vodafone|vi\b|bsnl|tata\s*sky|dish\s*tv|sun\s*direct|netflix|amazon\s*prime|hotstar|spotify|youtube\s*premium|zee5|sony\s*liv|voot", re.I), "Subscriptions"),
    # Insurance
    (re.compile(r"lic\b|hdfc\s*life|icici\s*pru|bajaj\s*allianz|star\s*health|niva\s*bupa|care\s*health|tata\s*aia|max\s*life|kotak\s*life|sbi\s*life|insurance|insure", re.I), "Insurance"),
    # EMI / Loans
    (re.compile(r"\bemi\b|loan\s*repay|bajaj\s*fin|home\s*loan|car\s*loan|personal\s*loan|hdfc\s*bank\s*emi|icicilombard|axis\s*bank\s*loan|emi\s*debit", re.I), "EMIs"),
    # Rent
    (re.compile(r"\brent\b|house\s*rent|rental|pg\s*rent|accommodation|lease", re.I), "Rent"),
    # Shopping
    (re.compile(r"amazon|flipkart|myntra|ajio|nykaa|meesho|snapdeal|shopify|tatacliq|croma|vijay\s*sales|reliance\s*digital", re.I), "Shopping"),
    # Healthcare
    (re.compile(r"apollo|fortis|medplus|1mg\b|pharmeasy|netmeds|hospital|clinic|pharmacy|diagnostic|lab\s*test|dr\.", re.I), "Healthcare"),
    # Education
    (re.compile(r"udemy|coursera|byju|unacademy|vedantu|school\s*fee|college\s*fee|tuition|exam\s*fee", re.I), "Education"),
    # Income markers
    (re.compile(r"salary|neft\s*cr|rtgs\s*cr|credit\s*salary|payroll|stipend", re.I), "Income"),
]

VALID_CATEGORIES = {
    "Groceries", "Dining", "Travel", "Utilities", "Subscriptions",
    "Insurance", "EMIs", "Rent", "Shopping", "Healthcare", "Education",
    "Income", "Miscellaneous",
}


def _rule_match(description: str) -> str | None:
    for pattern, category in RULES:
        if pattern.search(description):
            return category
    return None


def _get_user_correction(description: str) -> str | None:
    """Check if the user has previously corrected this description's category."""
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            """SELECT t.category FROM transactions t
               WHERE t.description = ? AND t.category_source = 'user'
               ORDER BY t.created_at DESC LIMIT 1""",
            (description,),
        ).fetchone()
    return row["category"] if row else None


def _llm_categorize(description: str) -> str:
    """LLM fallback — call Groq/Gemini to categorize an unknown transaction."""
    try:
        from backend.rag.llm import complete
        categories_str = ", ".join(sorted(VALID_CATEGORIES))
        prompt = (
            f"Categorize this Indian bank transaction into exactly one of these categories: "
            f"{categories_str}.\n\n"
            f"Transaction: {description}\n\n"
            f"Reply with only the category name, nothing else."
        )
        result = complete(prompt, max_tokens=20).strip()
        if result in VALID_CATEGORIES:
            return result
    except Exception as exc:
        logger.debug("[Categorizer] LLM fallback failed: %s", exc)
    return "Miscellaneous"


def categorize(description: str) -> str:
    """
    Categorize a transaction description.
    Lookup order: user correction → keyword rules → LLM fallback.
    """
    # 1. User correction takes priority
    user_cat = _get_user_correction(description)
    if user_cat:
        return user_cat

    # 2. Keyword rules
    rule_cat = _rule_match(description)
    if rule_cat:
        return rule_cat

    # 3. LLM fallback
    return _llm_categorize(description)


def apply_correction(transaction_id: int, new_category: str) -> bool:
    """Persist a user category correction."""
    if new_category not in VALID_CATEGORIES:
        return False
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            "SELECT category FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not row:
            return False
        old_category = row["category"]
        conn.execute(
            "UPDATE transactions SET category = ?, category_source = 'user' WHERE id = ?",
            (new_category, transaction_id),
        )
        conn.execute(
            "INSERT INTO category_corrections (transaction_id, old_category, new_category) VALUES (?, ?, ?)",
            (transaction_id, old_category, new_category),
        )
    return True
