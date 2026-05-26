"""
Alert notifier — pushes new alerts to WebSocket clients and
optionally to WhatsApp (high-severity only) via REA Communication Agent.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def push_new_alerts(alert_ids: list[int]):
    """
    Fetch the newly created alerts by ID, push them over WebSocket,
    and send high-severity ones to WhatsApp.
    """
    if not alert_ids:
        return

    from backend.storage.database import db
    from backend.main import manager  # WebSocket connection manager

    with db() as conn:
        placeholders = ",".join("?" * len(alert_ids))
        rows = conn.execute(
            f"SELECT * FROM alerts WHERE id IN ({placeholders})", alert_ids
        ).fetchall()

    for row in rows:
        alert = dict(row)

        # Push to all WebSocket clients
        try:
            await manager.broadcast({"type": "alert", "data": alert})
        except Exception as exc:
            logger.warning("[Notifier] WebSocket broadcast failed: %s", exc)

        # Push all severities to WhatsApp via REA
        await _send_whatsapp(alert["severity"], alert["description"])
        with db() as conn:
            conn.execute(
                "UPDATE alerts SET whatsapp_sent=1 WHERE id=?", (alert["id"],)
            )


async def _send_whatsapp(severity: str, message: str):
    """
    POST the alert message to the REA Communication Agent.
    REA is responsible for sending it to the user's WhatsApp.
    """
    import os
    rea_url = os.getenv("REA_WEBHOOK_URL", "")
    if not rea_url:
        logger.debug("[Notifier] REA_WEBHOOK_URL not set — skipping WhatsApp push")
        return

    severity_emoji = {"high": "🚨", "medium": "⚠️", "low": "ℹ️"}.get(severity, "🔔")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(rea_url, json={
                "type": "arthaos_alert",
                "message": f"{severity_emoji} ArthaOS Alert ({severity.upper()})\n\n{message}",
            })
        logger.info("[Notifier] Alert sent to WhatsApp via REA")
    except Exception as exc:
        logger.warning("[Notifier] WhatsApp push failed: %s", exc)
