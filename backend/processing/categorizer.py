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
    # Rent — must be before Travel/Utilities so Bilt housing payments are caught first
    (re.compile(r"bilt\s*rewards|bilt\s*housing|bilt\s*rent|\brent\b|house\s*rent|rental|pg\s*rent|accommodation|lease", re.I), "Rent"),

    # Groceries — US + India
    (re.compile(r"whole\s*foods|trader\s*joe|kroger|safeway|wegmans|publix|costco|target\s*grocery|walmart|stop\s*&?\s*shop|aldi|lidl|fresh\s*market|sprouts|food\s*lion|market\s*basket|giant\s*food|h[-\s]?e[-\s]?b|hannaford|meijer|weis|shoprite|shop\s*rite|grocery\s*square|patels\s*cash|cash\s*and\s*carry|food\s*bazaar|compare\s*foods|international\s*grocery|big\s*bazaar|dmart|reliance\s*fresh|zepto|blinkit|grofer|swiggy\s*instamart|bigbasket", re.I), "Groceries"),

    # Dining — US chains, TST* (Square/Toast POS prefix), food courts, India
    (re.compile(r"\btst\*|\bsq\s*\*|chipotle|chick.fil|popeyes?|panda\s*express|olive\s*garden|red\s*lobster|applebee|outback|cheesecake\s*factory|shake\s*shack|five\s*guys|in-n-out|raising\s*cane|wingstop|waffle\s*house|ihop|denny|panera|dunkin|tim\s*horton|doordash|grubhub|uber\s*eats|seamless|instacart\s*food|tikka|tandoori|indian\s*kitchen|swiggy|zomato|domino|pizza\s*hut|mcdonald|kfc|burger\s*king|starbucks|subway|restaurant|eatery|bistro|dine|bakery|cafe\b|coffee\b|bagel|sushi|ramen|poke\b|boba|smoothie|juice\s*bar|bar\s*&?\s*grill|tavern|brasserie|trattoria|pizzeria", re.I), "Dining"),

    # Travel — hotels, airlines, rideshare, car rental, parking, transit
    (re.compile(r"hyatt|marriott|hilton|westin|sheraton|hampton\s*inn|holiday\s*inn|best\s*western|wyndham|radisson|kimpton|four\s*seasons|ritz\s*carlton|hotel\.?com|hotels\.?com|booking\.?com|expedia|airbnb|vrbo|kayak\s*hotel|priceline|hotelcom|super\.?com.*hotel|nordic\s*village|ramada|homewood\s*suite|homewood\s*suites|residence\s*inn|courtyard|fairfield\s*inn|springhill|towneplace|aloft\s*hotel|element\s*hotel|moxy\s*hotel|ac\s*hotel|w\s*hotel|resort\b.*\bfolio|folio\s*number|arrive:.*depart:|uber\b|lyft|waymo|turo\b|hertz|enterprise\s*rent|avis|budget\s*car|national\s*car|dollar\s*rent|thrifty\s*car|zipcar|spothero|parkwhiz|parking|eztoll|e-zpass|toll\b|sunpass|peach\s*pass|amtrak|greyhound|megabus|flixbus|delta\b|united\b|american\s*air|southwest\b|jetblue|spirit\b|frontier\s*air|alaska\s*air|ola\b|rapido|irctc|indian\s*railways|makemytrip|redbus|indigo|air\s*india|spicejet|gas\s*station|shell\b|exxon|bp\b|chevron|circle\s*k|speedway|wawa|petrol|fuel", re.I), "Travel"),

    # Utilities — electric, water, internet, phone, municipal
    (re.compile(r"electric|con\s*ed|coned|pge\b|pg&e|national\s*grid|eversource|xcel\s*energy|duke\s*energy|dominion\s*energy|water\s*authority|municipal\s*util|utility|utilities\s*authority|jersey\s*city\s*municipal|internet|comcast|xfinity|verizon\s*fios|spectrum\b|cox\s*comm|optimum|frontier\s*comm|rcn\b|honest\s*networks|at&t\b|att\b|verizon\b|t-mobile|cricket\s*wireless|metro\s*pcs|boost\s*mobile|electricity|bescom|msedcl|tata\s*power|water\s*board|gas\s*bill|mahanagar\s*gas|igl\b", re.I), "Utilities"),

    # Subscriptions — streaming, SaaS, recurring digital
    (re.compile(r"netflix|hulu|disney\+?|hbo\s*max|max\b.*stream|peacock|paramount\+?|apple\s*tv|amazon\s*prime|spotify|apple\s*music|pandora|tidal|youtube\s*premium|twitch|adobe|microsoft\s*365|office\s*365|google\s*one|dropbox|icloud|github|notion|slack|zoom\b|lastpass|1password|nytimes|wsj\b|washington\s*post|linkedin\s*premium|claude\.ai|anthropic|openai|chatgpt|working\s*advantage|\bjio\b|airtel\s*post|vodafone|hotstar|zee5|sony\s*liv", re.I), "Subscriptions"),

    # Insurance
    (re.compile(r"geico|progressive\s*ins|state\s*farm|allstate|nationwide\s*ins|liberty\s*mutual|farmers\s*ins|usaa|travelers\s*ins|aetna|cigna|humana|unitedhealth|blue\s*cross|bcbs|oscar\s*health|kaiser|seven\s*corners|sevencorners|allianz\s*travel|lic\b|hdfc\s*life|insurance|insure", re.I), "Insurance"),

    # EMIs / loan payments
    (re.compile(r"\bemi\b|loan\s*payment|loan\s*repay|auto\s*loan|car\s*loan|home\s*loan|mortgage|student\s*loan|navient|sallie\s*mae|nelnet|wells\s*fargo\s*loan|bajaj\s*fin|personal\s*loan", re.I), "EMIs"),

    # Shopping — US + India
    (re.compile(r"amazon(?!.*prime)|walmart(?!.*grocery)|target(?!.*grocery)|best\s*buy|apple\s*store|apple\.com\/shop|dyson|ikea|wayfair|home\s*depot|lowe['']?s|bed\s*bath|crate\s*&?\s*barrel|pottery\s*barn|williams\s*sonoma|nordstrom|macy['']?s|bloomingdale|gap\b|old\s*navy|h&m\b|zara\b|uniqlo|forever\s*21|tj\s*maxx|marshalls|ross\s*store|kohls|jcpenney|flipkart|myntra|ajio|nykaa|meesho|shopify", re.I), "Shopping"),

    # Healthcare
    (re.compile(r"cvs\b|walgreens|rite\s*aid|duane\s*reade|pharmacy|urgent\s*care|labcorp|quest\s*diag|hospital|medical\s*center|health\s*system|clinic|doctor|physician|dentist|optometrist|orthodont|apollo|fortis|medplus|1mg\b|pharmeasy", re.I), "Healthcare"),

    # Education
    (re.compile(r"udemy|coursera|skillshare|linkedin\s*learn|pluralsight|khan\s*academy|chegg|tutor|school\s*fee|college\s*fee|tuition|exam\s*fee|byju|unacademy", re.I), "Education"),

    # Income — direct deposits, payroll
    (re.compile(r"direct\s*deposit|payroll|paylocity|adp\b|gusto\b|salary|stipend|neft\s*cr|rtgs\s*cr|credit\s*salary", re.I), "Income"),

    # Investments — brokerages and investment platforms (before Transfer to prevent misclassification)
    (re.compile(r"robinhood|schwab|fidelity|vanguard|e[\s*]?trade|td\s*ameritrade|merrill\s*lynch|merrill\s*edge|wealthfront|betterment|acorns\b|stash\s*invest|sofi\s*invest|m1\s*finance|public\.com|webull|coinbase|binance|kraken\b|gemini\s*crypto|investment|brokerage|stock\s*purchase|dividend|mutual\s*fund|sip\s*invest|zerodha|groww\b|kuvera|paytm\s*money|upstox", re.I), "Investments"),

    # Transfer — CC payments, ACH, P2P (must be last before Misc to catch broad patterns)
    (re.compile(r"payment\s*thank\s*you|autopay|online\s*payment\s*thank|thank\s*you\s*payment|balance\s*payment|web\s*payment|mobile\s*payment|ach\s*(?:debit|credit|transfer)|wire\s*transfer|\bzelle\b|\bvenmo\b|\bpaypal\b|cc\s*payment|card\s*payment|citi\s*payment|chase\s*payment|capital\s*one\s*payment|wells\s*fargo\s*payment|bank\s*of\s*america\s*payment|bofa\s*payment|amex\s*payment|bill\s*pay", re.I), "Transfer"),
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

def categorize(description: str, keyword_only: bool = False, tx_type: str | None = None, institution: str | None = None) -> str:
    """
    Categorize a transaction description.
    Order: user correction → learned rules → keyword rules → LLM fallback.

    Args:
        description: transaction description
        keyword_only: skip LLM fallback (for bulk sync)
        tx_type: 'debit' or 'credit' — used to handle special cases
        institution: 'Bilt', 'BofA', etc. — used to handle special cases

    Special case: Bilt credit transactions (rent/utilities paid via Bilt to BofA)
    should be categorized as Transfer, not Rent/Utilities, to avoid double-counting.
    """
    # Special case: Bilt credit txns should be Transfer (payment routing), not the underlying category
    if tx_type == "credit" and institution == "Bilt":
        return "Transfer"

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


def categorize_static(description: str, tx_type: str | None = None, institution: str | None = None) -> str:
    """
    Categorize using ONLY static keyword rules — no user corrections, no learned
    rules, no LLM.  Use this during data import (Teller sync, PDF ingestion) so
    learned rules from one source can't contaminate another source's categories.
    User corrections applied afterward (via re-categorize or manual edit) are
    always respected because they have the highest priority in categorize().

    Args:
        description: transaction description
        tx_type: 'debit' or 'credit' — for special case handling
        institution: institution name — for special case handling
    """
    # Special case: Bilt credit txns are payment routing, not the underlying category
    if tx_type == "credit" and institution == "Bilt":
        return "Transfer"

    rule_cat = _rule_match(description)
    return rule_cat if rule_cat else "Miscellaneous"


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
