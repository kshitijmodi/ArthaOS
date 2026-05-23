"""
ArthaOS startup script.
1. Initialises the database
2. Starts the FastAPI backend immediately
3. Runs email catch-up fetch + ingestion in a background thread

Run with: python start.py
"""
import logging
import threading

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("startup")


def _background_catchup():
    try:
        from backend.ingestion.email_fetcher import run_fetch
        files = run_fetch()
        logger.info("Email fetch complete: %d new files", len(files))
    except Exception as exc:
        logger.warning("Email fetch failed (continuing): %s", exc)

    try:
        from backend.ingestion.pipeline import ingest_directory
        results = ingest_directory()
        logger.info("Ingestion complete: %d files processed", len(results))
    except Exception as exc:
        logger.warning("Ingestion failed (continuing): %s", exc)


def main():
    from backend.storage.database import init_db
    init_db()

    # Email fetch + ingestion runs in background so the API starts immediately
    threading.Thread(target=_background_catchup, daemon=True).start()

    logger.info("Starting ArthaOS backend on http://localhost:8000")
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
