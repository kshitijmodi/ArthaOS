"""
REA Communication Agent — bridges ArthaOS alerts to WhatsApp and
routes inbound WhatsApp queries back to ArthaOS.

Two flows:
  1. ArthaOS → REA → WhatsApp
     POST /alert  {"type": "arthaos_alert", "message": "..."}
     REA sends the message to the user's WhatsApp via Twilio.

  2. WhatsApp → REA → ArthaOS → WhatsApp reply
     Twilio hits POST /whatsapp/inbound with the incoming message.
     REA forwards the text to ArthaOS /whatsapp/query and replies.
"""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from rea.config import (
    ARTHAOS_API_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    USER_WHATSAPP_NUMBER,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Twilio client (lazy — only initialised if credentials present)
# ---------------------------------------------------------------------------

def _twilio_client():
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials not configured — set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
    from twilio.rest import Client
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp(to: str, body: str) -> str:
    """Send a WhatsApp message via Twilio. Returns the message SID."""
    client = _twilio_client()
    msg = client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=to,
        body=body,
    )
    logger.info("[REA] WhatsApp sent → %s | sid=%s", to, msg.sid)
    return msg.sid


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    creds_ok = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and USER_WHATSAPP_NUMBER)
    logger.info("[REA] Starting — Twilio creds: %s | user number: %s | ArthaOS: %s",
                "OK" if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else "MISSING",
                USER_WHATSAPP_NUMBER or "MISSING",
                ARTHAOS_API_URL)
    if not creds_ok:
        logger.warning("[REA] WhatsApp delivery disabled — fill TWILIO_* and USER_WHATSAPP_NUMBER in .env")
    yield


app = FastAPI(title="REA Communication Agent", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
        "user_number": USER_WHATSAPP_NUMBER or "not set",
        "arthaos_url": ARTHAOS_API_URL,
    }


# ---------------------------------------------------------------------------
# Flow 1: ArthaOS → REA → WhatsApp
# ---------------------------------------------------------------------------

class AlertPayload(BaseModel):
    type: str
    message: str

@app.post("/alert")
async def receive_alert(payload: AlertPayload):
    """
    Called by ArthaOS notifier when a high-severity alert fires.
    Forwards the message to the user's WhatsApp.
    """
    if not USER_WHATSAPP_NUMBER:
        logger.warning("[REA] USER_WHATSAPP_NUMBER not set — alert dropped: %s", payload.message[:80])
        return {"status": "dropped", "reason": "USER_WHATSAPP_NUMBER not configured"}

    try:
        sid = send_whatsapp(USER_WHATSAPP_NUMBER, payload.message)
        return {"status": "sent", "sid": sid}
    except Exception as exc:
        logger.error("[REA] Failed to send WhatsApp alert: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Flow 2: WhatsApp → REA → ArthaOS → reply
# ---------------------------------------------------------------------------

@app.post("/whatsapp/inbound")
async def whatsapp_inbound(
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(default=""),
):
    """
    Twilio webhook — called when the user sends a WhatsApp message.
    Forwards the query to ArthaOS and replies with the answer.
    """
    logger.info("[REA] Inbound WhatsApp from %s: %s", From, Body[:120])

    # Forward to ArthaOS
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{ARTHAOS_API_URL}/whatsapp/query",
                json={"query": Body, "sender": From},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("[REA] ArthaOS query failed: %s", exc)
        reply = "Sorry, I couldn't reach ArthaOS right now. Try again in a moment."
        _send_twiml_reply(reply)
        return PlainTextResponse(_twiml(reply), media_type="application/xml")

    answer = data.get("answer", "No answer returned.")
    low_confidence = data.get("low_confidence", False)

    if low_confidence:
        answer += "\n\n_Low confidence — check dashboard for details._"

    return PlainTextResponse(_twiml(answer), media_type="application/xml")


def _twiml(message: str) -> str:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'


def _send_twiml_reply(message: str) -> str:
    return _twiml(message)


# ---------------------------------------------------------------------------
# Flow 2b: Manual query trigger (for testing without WhatsApp)
# ---------------------------------------------------------------------------

class QueryPayload(BaseModel):
    query: str
    send_to_whatsapp: bool = False

@app.post("/query")
async def manual_query(payload: QueryPayload):
    """
    Test endpoint — send a query to ArthaOS and optionally push the answer to WhatsApp.
    Useful for testing without a live Twilio webhook.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{ARTHAOS_API_URL}/whatsapp/query",
                json={"query": payload.query},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ArthaOS unreachable: {exc}")

    answer = data.get("answer", "")
    low_confidence = data.get("low_confidence", False)

    result = {"answer": answer, "low_confidence": low_confidence, "whatsapp_sent": False}

    if payload.send_to_whatsapp and USER_WHATSAPP_NUMBER:
        try:
            sid = send_whatsapp(USER_WHATSAPP_NUMBER, answer)
            result["whatsapp_sent"] = True
            result["sid"] = sid
        except Exception as exc:
            result["whatsapp_error"] = str(exc)

    return result
