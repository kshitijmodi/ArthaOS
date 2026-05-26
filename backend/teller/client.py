"""
Teller API client — uses mutual TLS with app certificate + private key.
"""
import os
import logging
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

TELLER_BASE = "https://api.teller.io"
TELLER_ENV  = os.getenv("TELLER_ENV", "sandbox")
APP_ID      = os.getenv("TELLER_APP_ID", "")

_CERT_PATH = Path(os.getenv("TELLER_CERT_PATH", "backend/teller/certificate.pem"))
_KEY_PATH  = Path(os.getenv("TELLER_KEY_PATH",  "backend/teller/private_key.pem"))


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=TELLER_BASE,
        cert=(_CERT_PATH, _KEY_PATH),
        timeout=15,
    )


def get_accounts(access_token: str) -> list[dict]:
    with _client() as c:
        r = c.get("/accounts", auth=(access_token, ""))
        r.raise_for_status()
        return r.json()


def get_account_balances(access_token: str, account_id: str) -> dict:
    with _client() as c:
        r = c.get(f"/accounts/{account_id}/balances", auth=(access_token, ""))
        r.raise_for_status()
        return r.json()


def get_transactions(access_token: str, account_id: str, count: int = 250) -> list[dict]:
    with _client() as c:
        r = c.get(
            f"/accounts/{account_id}/transactions",
            params={"count": count},
            auth=(access_token, ""),
        )
        r.raise_for_status()
        return r.json()


def get_identity(access_token: str, account_id: str) -> dict:
    with _client() as c:
        r = c.get(f"/accounts/{account_id}/identity", auth=(access_token, ""))
        r.raise_for_status()
        return r.json()
