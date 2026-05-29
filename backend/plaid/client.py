"""
Plaid API client — plain httpx calls, no SDK dependency.
Auth: PLAID-CLIENT-ID + PLAID-SECRET request headers.
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

PLAID_ENV  = os.getenv("PLAID_ENV", "sandbox")
CLIENT_ID  = os.getenv("PLAID_CLIENT_ID", "")
SECRET     = os.getenv("PLAID_SECRET", "")

_BASE_URLS = {
    "sandbox":     "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production":  "https://production.plaid.com",
}
_BASE = _BASE_URLS.get(PLAID_ENV, "https://production.plaid.com")


def _auth() -> dict:
    return {"client_id": CLIENT_ID, "secret": SECRET}


def _post(path: str, body: dict) -> dict:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{_BASE}{path}",
            json={**_auth(), **body},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()


# ── Link / auth ──────────────────────────────────────────────────────────── #

def create_link_token(user_id: str = "arthaos-user") -> str:
    """Create a Plaid Link token to initialise the Link flow in the browser."""
    data = _post("/link/token/create", {
        "user": {"client_user_id": user_id},
        "client_name": "ArthaOS",
        "products": ["transactions"],
        "optional_products": ["investments", "liabilities"],
        "country_codes": ["US"],
        "language": "en",
        "transactions": {"days_requested": 730},
    })
    return data["link_token"]


def exchange_public_token(public_token: str) -> dict:
    """Exchange a Plaid Link public_token for a permanent access_token + item_id."""
    return _post("/item/public_token/exchange", {"public_token": public_token})


def get_institution_name(institution_id: str) -> str:
    try:
        data = _post("/institutions/get_by_id", {
            "institution_id": institution_id,
            "country_codes": ["US"],
        })
        return data.get("institution", {}).get("name", institution_id)
    except Exception:
        return institution_id


def remove_item(access_token: str) -> None:
    _post("/item/remove", {"access_token": access_token})


# ── Accounts ─────────────────────────────────────────────────────────────── #

def get_accounts(access_token: str) -> list[dict]:
    return _post("/accounts/get", {"access_token": access_token}).get("accounts", [])


def get_item(access_token: str) -> dict:
    return _post("/item/get", {"access_token": access_token}).get("item", {})


# ── Transactions sync (cursor-based, incremental) ────────────────────────── #

def sync_transactions(access_token: str, cursor: str | None = None) -> dict:
    """
    Pull all new/modified/removed transactions since cursor.
    Handles pagination automatically — returns when has_more is False.
    Returns {"added": [...], "modified": [...], "removed": [...], "next_cursor": str}
    """
    added, modified, removed = [], [], []
    next_cursor = cursor or ""

    while True:
        body: dict = {"access_token": access_token, "count": 500}
        if next_cursor:
            body["cursor"] = next_cursor

        data = _post("/transactions/sync", body)
        added.extend(data.get("added", []))
        modified.extend(data.get("modified", []))
        removed.extend(data.get("removed", []))
        next_cursor = data.get("next_cursor", "")

        if not data.get("has_more", False):
            break

    return {
        "added":       added,
        "modified":    modified,
        "removed":     removed,
        "next_cursor": next_cursor,
    }


# ── Investments ──────────────────────────────────────────────────────────── #

def get_investments(access_token: str) -> dict:
    """Returns {"holdings": [...], "securities": [...]}. Empty if not supported."""
    try:
        data = _post("/investments/holdings/get", {"access_token": access_token})
        return {
            "holdings":   data.get("holdings", []),
            "securities": data.get("securities", []),
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 400):
            # PRODUCTS_NOT_SUPPORTED or similar — not available for this item
            logger.debug("[PlaidClient] Investments not supported: %s", e.response.text)
        else:
            logger.warning("[PlaidClient] Investments fetch error: %s", e)
        return {"holdings": [], "securities": []}


# ── Liabilities ──────────────────────────────────────────────────────────── #

def get_liabilities(access_token: str) -> dict:
    """Returns Plaid liabilities object. Empty if not supported."""
    try:
        return _post("/liabilities/get", {"access_token": access_token}).get("liabilities", {})
    except Exception as e:
        logger.debug("[PlaidClient] Liabilities not supported: %s", e)
        return {}
