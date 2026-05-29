"""
Categorization engine — hybrid rule-based + learned rules + LLM fallback.

Lookup order:
  1. User correction (exact description match, highest priority)
  2. Learned rules (derived from corrections — keyword → category mapping)
  3. Keyword rules (static merchant patterns)
  4. LLM fallback (Groq / Gemini)
"""
import logging
import re
import threading

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static keyword rules
# ---------------------------------------------------------------------------

RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"big\s*bazaar|dmart|reliance\s*fresh|zepto|blinkit|grofer|swiggy\s*instamart|nature['\s]s\s*basket|spencer|lulu|bigbasket|more\s*supermart", re.I), "Groceries"),
    (re.compile(r"swiggy|zomato|domino|pizza\s*hut|mcdonald|kfc|burger\s*king|cafe\s*coffee|starbucks|subway|haldiram|barbeque\s*nation|restaurant|eatery|bistro|dine", re.I), "Dining"),
    (re.compile(r"uber|ola\b|rapido|metro|irctc|indian\s*railways|makemytrip|redbus|yatra|cleartrip|indigo|air\s*india|spicejet|vistara|goair|petrol|fuel|hp\s*petrol|indian\s*oil|bharat\s*petroleum", re.I), "Travel"),
    (re.compile(r"electricity|bescom|msedcl|tata\s*power|adani\s*electricity|water\s*board|bwssb|gas\s*bill|mahanagar\s*gas|igl\b|piped\s*gas", re.I), "Utilities"),
    (re.compile(r"\bjio\b|airtel|vodafone|vi\b|bsnl|tata\s*sky|dish\s*tv|sun\s*direct|netflix|amazon\s*prime|hotstar|spotify|youtube\s*premium|zee5|sony\s*liv|voot", re.I), "Subscriptions"),
    (re.compile(r"lic\b|hdfc\s*life|icici\s*pru|bajaj\s*allianz|star\s*health|niva\s*bupa|care\s*health|tata\s*aia|max\s*life|kotak\s*life|sbi\s*life|insurance|insure", re.I), "Insurance"),
    (re.compile(r"\bemi\b|loan\s*repay|bajaj\s*fin|home\s*loan|car\s*loan|personal\s*loan|hdfc\s*bank\s*emi|icicilombard|axis\s*bank\s*loan|emi\s*debit", re.I), "EMIs"),
    (re.compile(r"\brent\b|house\s*rent|rental|pg\s*rent|accommodation|lease", re.I), "Rent"),
    (re.compile(r"amazon|flipkart|myntra|ajio|nykaa|meesho|snapdeal|shopify|tatacliq|croma|vijay\s*sales|reliance\s*digital", re.I), "Shopping"),
    (re.compile(r"apollo|fortis|medplus|1mg\b|pharmeasy|netmeds|hospital|clinic|pharmacy|diagnostic|lab\s*test|dr\.", re.I), "Healthcare"),
    (re.compile(r"udemy|coursera|byju|unacademy|vedantu|school\s*fee|college\s*fee|tuition|exam\s*fee", re.I), "Education"),
    (re.compile(r"direct\s*deposit|salary|neft\s*cr|rtgs\s*cr|credit\s*salary|payroll|paylocity|stipend", re.I), "Income"),
    (re.compile(r"payment\s*thank\s*you|autopay|bill\s*pay|balance\s*payment|thank\s*you\s*payment|online\s*payment|web\s*payment|mobile\s*payment|ach\s*payment|wire\s*transfer|\bzelle\b|\bvenmo\b|\bpaypal\b|cc\s*payment|card\s*payment|citi\s*payment|chase\s*payment|capital\s*one\s*payment|wells\s*fargo\s*payment|bank\s*of\s*america\s*payment|bofa\s*payment|amex\s*payment", re.I), "Transfer"),
]

def _load_valid_categories() -> set[str]:
    try:
        from backend.storage.database import db
        with db() as conn:
            rows = conn.execute("SELECT name FROM categories").fetchall()
        if rows:
            return {r["name"] for r in rows}
    except Exception:
        pass
    return {
        "Groceries", "Dining", "Travel", "Utilities", "Subscriptions",
        "Insurance", "EMIs", "Rent", "Shopping", "Healthcare", "Education",
        "Investments", "Income", "Miscellaneous",
    }


def get_valid_categories() -> set[str]:
    return _load_valid_categories()


VALID_CATEGORIES = _load_valid_categories()

# ---------------------------------------------------------------------------
# Learned rules cache (rebuilt from corrections on demand)
# ---------------------------------------------------------------------------

_learned_lock = threading.Lock()
_learned_rules: dict[str, str] = {}   # keyword (lowercase) → category
_learned_dirty = True                  # rebuild on next access


def _rebuild_learned_rules():
    """Derive keyword→category rules from user corrections."""
    global _learned_rules, _learned_dirty
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            """SELECT t.description, t.category
               FROM transactions t
               WHERE t.category_source = 'user'
               GROUP BY t.description, t.category
               ORDER BY COUNT(*) DESC"""
        ).fetchall()

    rules: dict[str, str] = {}
    for row in rows:
        # Extract meaningful tokens (≥4 chars) from description as keywords
        tokens = re.findall(r"[a-zA-Z]{4,}", row["description"].lower())
        for token in tokens:
            if token not in rules:
                rules[token] = row["category"]

    with _learned_lock:
        _learned_rules = rules
        _learned_dirty = False

    logger.info("[Categorizer] Rebuilt learned rules: %d keywords", len(rules))


def invalidate_learned_rules():
    """Call this after any user correction so rules are rebuilt on next use."""
    global _learned_dirty
    _learned_dirty = True


def _learned_match(description: str) -> str | None:
    global _learned_dirty
    if _learned_dirty:
        _rebuild_learned_rules()
    tokens = re.findall(r"[a-zA-Z]{4,}", description.lower())
    with _learned_lock:
        for token in tokens:
            if token in _learned_rules:
                return _learned_rules[token]
    return None


def _db_keyword_match(description: str) -> str | None:
    """Match against user-editable keywords stored in the categories table."""
    try:
        from backend.storage.database import db
        with db() as conn:
            rows = conn.execute(
                "SELECT name, keywords FROM categories WHERE keywords != ''"
            ).fetchall()
        desc_lower = description.lower()
        for row in rows:
            for kw in row["keywords"].split(","):
                kw = kw.strip()
                if kw and kw in desc_lower:
                    return row["name"]
    except Exception:
        pass
    return None


def _rule_match(description: str) -> str | None:
    for pattern, category in RULES:
        if pattern.search(description):
            return category
    return _db_keyword_match(description)


def _get_user_correction(description: str) -> str | None:
    from backend.storage.database import db
    with db() as conn:
        row = conn.execute(
            """SELECT category FROM transactions
               WHERE description = ? AND category_source = 'user'
               ORDER BY created_at DESC LIMIT 1""",
            (description,),
        ).fetchone()
    return row["category"] if row else None


def _llm_categorize(description: str) -> str:
    try:
        from backend.rag.llm import complete
        valid = get_valid_categories()
        categories_str = ", ".join(sorted(valid))
        prompt = (
            f"Categorize this bank transaction into exactly one of these categories: "
            f"{categories_str}.\n\n"
            f"Transaction: {description}\n\n"
            f"Reply with only the category name, nothing else."
        )
        result = complete(prompt, max_tokens=20).strip()
        if result in valid:
            return result
    except Exception as exc:
        logger.debug("[Categorizer] LLM fallback failed: %s", exc)
    return "Miscellaneous"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(description: str, keyword_only: bool = False) -> str:
    """
    Categorize a transaction description.
    Order: user correction → learned rules → keyword rules → LLM fallback.

    Pass keyword_only=True to skip the LLM fallback (avoids Groq rate limiting
    during bulk sync operations where holding a DB lock during retries causes
    "database is locked" errors for all other writers).
    """
    user_cat = _get_user_correction(description)
    if user_cat:
        return user_cat

    learned_cat = _learned_match(description)
    if learned_cat:
        return learned_cat

    rule_cat = _rule_match(description)
    if rule_cat:
        return rule_cat

    if keyword_only:
        return "Miscellaneous"

    return _llm_categorize(description)


def apply_correction(transaction_id: int, new_category: str) -> bool:
    """Persist a single user category correction and invalidate learned rules."""
    if new_category not in get_valid_categories():
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
    invalidate_learned_rules()
    return True


def apply_bulk_correction(transaction_ids: list[int], new_category: str) -> int:
    """Apply the same category correction to multiple transactions at once."""
    if new_category not in VALID_CATEGORIES:
        return 0
    count = 0
    for tx_id in transaction_ids:
        if apply_correction(tx_id, new_category):
            count += 1
    return count


def recategorize_all() -> int:
    """
    Re-run keyword/learned-rule categorization on every auto-categorized transaction.
    Skips LLM to stay fast. Only updates rows where the new category differs.
    """
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            "SELECT id, description, category FROM transactions WHERE category_source='auto'"
        ).fetchall()

    updated = 0
    with db() as conn:
        for row in rows:
            new_cat = _learned_match(row["description"]) or _rule_match(row["description"])
            if new_cat and new_cat != row["category"]:
                conn.execute(
                    "UPDATE transactions SET category = ? WHERE id = ?",
                    (new_cat, row["id"]),
                )
                updated += 1

    logger.info("[Categorizer] recategorize_all: updated %d transactions", updated)
    return updated


def recategorize_miscellaneous() -> int:
    """
    Re-run categorization on all Miscellaneous transactions that were auto-categorized.
    Useful after adding new keyword rules or when LLM was unavailable at ingest time.
    """
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            "SELECT id, description FROM transactions WHERE category='Miscellaneous' AND category_source='auto'"
        ).fetchall()

    updated = 0
    with db() as conn:  # noqa: SIM117  (separate context so each write commits)
        for row in rows:
            new_cat = _learned_match(row["description"]) or _rule_match(row["description"])
            if new_cat and new_cat != "Miscellaneous":
                conn.execute(
                    "UPDATE transactions SET category = ? WHERE id = ?",
                    (new_cat, row["id"]),
                )
                updated += 1

    logger.info("[Categorizer] Recategorized %d Miscellaneous transactions", updated)
    return updated
