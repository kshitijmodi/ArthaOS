"""
Email fetcher — Gmail (OAuth 2.0) + Yahoo (IMAP).
On each run it reads last_fetched_at from system_state and fetches only
emails received after that timestamp, enabling startup catch-up.
"""
import imaplib
import email
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path

from backend.config import (
    STATEMENTS_DIR,
    GMAIL_CREDENTIALS_FILE,
    GMAIL_TOKEN_FILE,
    YAHOO_EMAIL,
    YAHOO_APP_PASSWORD,
    YAHOO_IMAP_HOST,
    YAHOO_IMAP_PORT,
    WHITELISTED_DOMAINS,
)
from backend.storage.database import db

logger = logging.getLogger(__name__)

STATEMENTS_DIR.mkdir(parents=True, exist_ok=True)

# Filename patterns that suggest a bank/card statement PDF
STATEMENT_PATTERNS = re.compile(
    r"(statement|stmt|account|txn|transaction|credit.card|bill|invoice|passbook)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_whitelisted(sender: str) -> bool:
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in WHITELISTED_DOMAINS)


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _save_attachment(data: bytes, filename: str) -> Path:
    safe_name = re.sub(r"[^\w\.\-]", "_", filename)
    dest = STATEMENTS_DIR / safe_name
    # Avoid overwriting with a hash suffix
    if dest.exists():
        h = hashlib.md5(data).hexdigest()[:6]
        stem, suffix = os.path.splitext(safe_name)
        dest = STATEMENTS_DIR / f"{stem}_{h}{suffix}"
    dest.write_bytes(data)
    return dest


def _get_last_fetched(mailbox: str) -> datetime | None:
    with db() as conn:
        row = conn.execute(
            "SELECT last_fetched_at FROM system_state WHERE mailbox = ?", (mailbox,)
        ).fetchone()
    if row and row["last_fetched_at"]:
        return datetime.fromisoformat(row["last_fetched_at"]).replace(tzinfo=timezone.utc)
    return None


def _update_system_state(mailbox: str, status: str = "success"):
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE system_state SET last_fetched_at = ?, status = ? WHERE mailbox = ?",
            (now, status, mailbox),
        )


def _track_email(conn, email_id: str, mailbox: str, sender: str, subject: str,
                 attachment_file: str | None, status: str):
    try:
        conn.execute(
            """INSERT OR IGNORE INTO email_tracking
               (email_id, mailbox, sender, subject, attachment_file, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (email_id, mailbox, sender, subject, attachment_file, status),
        )
    except Exception as exc:
        logger.warning("Could not track email %s: %s", email_id, exc)


def _already_tracked(mailbox: str, email_id: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM email_tracking WHERE mailbox = ? AND email_id = ?",
            (mailbox, email_id),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Gmail fetcher
# ---------------------------------------------------------------------------

def fetch_gmail(since: datetime | None = None) -> list[Path]:
    """Fetch PDF attachments from Gmail since `since`. Returns saved file paths."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        import base64
    except ImportError as exc:
        logger.error("Gmail dependencies missing: %s", exc)
        return []

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = None

    if GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GMAIL_CREDENTIALS_FILE.exists():
                logger.error("gmail_credentials.json not found. Run OAuth setup first.")
                return []
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GMAIL_CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        GMAIL_TOKEN_FILE.write_text(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    saved_files: list[Path] = []

    # Build search query
    query_parts = ["has:attachment filename:pdf"]
    if since:
        date_str = since.strftime("%Y/%m/%d")
        query_parts.append(f"after:{date_str}")
    query = " ".join(query_parts)

    try:
        results = service.users().messages().list(userId="me", q=query, maxResults=200).execute()
        messages = results.get("messages", [])
        logger.info("[Gmail] Found %d candidate messages", len(messages))

        for msg_meta in messages:
            msg_id = msg_meta["id"]
            if _already_tracked("gmail", msg_id):
                continue

            msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
            sender = headers.get("from", "")
            subject = _decode_header_value(headers.get("subject", ""))

            if not _is_whitelisted(sender):
                with db() as conn:
                    _track_email(conn, msg_id, "gmail", sender, subject, None, "skipped")
                continue

            parts = msg["payload"].get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                mime = part.get("mimeType", "")
                if "pdf" not in mime.lower() and not filename.lower().endswith(".pdf"):
                    continue
                if not STATEMENT_PATTERNS.search(filename) and not STATEMENT_PATTERNS.search(subject):
                    continue

                body = part.get("body", {})
                att_id = body.get("attachmentId")
                if not att_id:
                    data = base64.urlsafe_b64decode(body.get("data", ""))
                else:
                    att = service.users().messages().attachments().get(
                        userId="me", messageId=msg_id, id=att_id
                    ).execute()
                    data = base64.urlsafe_b64decode(att["data"])

                if not data:
                    continue

                saved = _save_attachment(data, filename or f"gmail_{msg_id}.pdf")
                saved_files.append(saved)
                with db() as conn:
                    _track_email(conn, msg_id, "gmail", sender, subject, saved.name, "processed")
                logger.info("[Gmail] Saved: %s", saved.name)

        _update_system_state("gmail", "success")
    except Exception as exc:
        logger.error("[Gmail] Fetch failed: %s", exc)
        _update_system_state("gmail", "failed")

    return saved_files


# ---------------------------------------------------------------------------
# Yahoo IMAP fetcher
# ---------------------------------------------------------------------------

def fetch_yahoo(since: datetime | None = None) -> list[Path]:
    """Fetch PDF attachments from Yahoo Mail via IMAP since `since`."""
    if not YAHOO_EMAIL or not YAHOO_APP_PASSWORD:
        logger.warning("[Yahoo] Credentials not configured — skipping.")
        return []

    saved_files: list[Path] = []
    try:
        mail = imaplib.IMAP4_SSL(YAHOO_IMAP_HOST, YAHOO_IMAP_PORT)
        mail.login(YAHOO_EMAIL, YAHOO_APP_PASSWORD)
        mail.select("INBOX")

        if since:
            date_str = since.strftime("%d-%b-%Y")
            _, data = mail.search(None, f'(SINCE "{date_str}")')
        else:
            # First run: limit to last 6 months to avoid scanning entire mailbox
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%d-%b-%Y")
            _, data = mail.search(None, f'(SINCE "{cutoff}")')

        msg_ids = data[0].split()
        logger.info("[Yahoo] Found %d candidate messages", len(msg_ids))

        for msg_id_bytes in msg_ids:
            msg_id = msg_id_bytes.decode()
            if _already_tracked("yahoo", msg_id):
                continue

            _, msg_data = mail.fetch(msg_id_bytes, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = _decode_header_value(msg.get("From", ""))
            subject = _decode_header_value(msg.get("Subject", ""))

            if not _is_whitelisted(sender):
                with db() as conn:
                    _track_email(conn, msg_id, "yahoo", sender, subject, None, "skipped")
                continue

            for part in msg.walk():
                content_type = part.get_content_type()
                filename = part.get_filename() or ""
                if "pdf" not in content_type.lower() and not filename.lower().endswith(".pdf"):
                    continue
                if not STATEMENT_PATTERNS.search(filename) and not STATEMENT_PATTERNS.search(subject):
                    continue

                data = part.get_payload(decode=True)
                if not data:
                    continue

                saved = _save_attachment(data, filename or f"yahoo_{msg_id}.pdf")
                saved_files.append(saved)
                with db() as conn:
                    _track_email(conn, msg_id, "yahoo", sender, subject, saved.name, "processed")
                logger.info("[Yahoo] Saved: %s", saved.name)

        mail.logout()
        _update_system_state("yahoo", "success")
    except imaplib.IMAP4.error as exc:
        logger.error("[Yahoo] IMAP auth/connection error: %s", exc)
        _update_system_state("yahoo", "failed")
    except Exception as exc:
        logger.error("[Yahoo] Fetch failed: %s", exc)
        _update_system_state("yahoo", "failed")

    return saved_files


# ---------------------------------------------------------------------------
# Main entry point — runs both mailboxes with catch-up
# ---------------------------------------------------------------------------

def run_fetch() -> list[Path]:
    """Fetch from all configured mailboxes using last_fetched_at for catch-up."""
    gmail_since = _get_last_fetched("gmail")
    yahoo_since = _get_last_fetched("yahoo")

    logger.info("[Fetcher] Gmail since: %s | Yahoo since: %s", gmail_since, yahoo_since)

    files: list[Path] = []
    files += fetch_gmail(since=gmail_since)
    files += fetch_yahoo(since=yahoo_since)

    logger.info("[Fetcher] Total new attachments downloaded: %d", len(files))
    return files


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_fetch()
