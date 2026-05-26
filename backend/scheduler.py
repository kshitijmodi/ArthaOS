"""
APScheduler — runs daily tasks:
  - Email fetch + ingestion
  - Agent detection run
"""
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _daily_email_fetch():
    logger.info("[Scheduler] Running daily email fetch...")
    try:
        from backend.ingestion.email_fetcher import run_fetch
        from backend.ingestion.pipeline import ingest_file
        files = run_fetch()
        for f in files:
            ingest_file(f)
        logger.info("[Scheduler] Email fetch complete: %d files", len(files))
    except Exception as exc:
        logger.error("[Scheduler] Email fetch failed: %s", exc)

    # Teller sync after email fetch
    try:
        from backend.teller.sync import sync_all
        result = sync_all()
        logger.info("[Scheduler] Teller sync complete: %s", result)
    except Exception as exc:
        logger.error("[Scheduler] Teller sync failed: %s", exc)


def _daily_agent_run():
    logger.info("[Scheduler] Running daily agent scan...")
    try:
        from backend.agent.engine import run_agent
        alert_ids = run_agent()
        if alert_ids:
            from backend.agent.notifier import push_new_alerts
            asyncio.run(push_new_alerts(alert_ids))
        logger.info("[Scheduler] Agent scan complete: %d new alerts", len(alert_ids))
    except Exception as exc:
        logger.error("[Scheduler] Agent run failed: %s", exc)


def _teller_poll():
    try:
        from backend.teller.sync import sync_all
        result = sync_all()
        if result.get("new_transactions", 0) > 0:
            logger.info("[Scheduler] Teller poll — %d new transaction(s)", result["new_transactions"])
    except Exception as exc:
        logger.error("[Scheduler] Teller poll failed: %s", exc)


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()

    # Email fetch every 24h at 13:00 ET
    _scheduler.add_job(_daily_email_fetch, "cron", hour=13, minute=0, id="email_fetch", timezone="America/New_York")
    # Agent scan every day at 13:30 ET (after fetch)
    _scheduler.add_job(_daily_agent_run, "cron", hour=13, minute=30, id="agent_scan", timezone="America/New_York")
    # Teller poll every 30 minutes
    _scheduler.add_job(_teller_poll, "interval", minutes=30, id="teller_poll")

    _scheduler.start()
    logger.info("[Scheduler] Started — daily fetch at 13:00 ET, agent scan at 13:30 ET, Teller poll every 30m")
    return _scheduler


def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)
