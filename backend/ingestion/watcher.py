"""
Watchdog-based file watcher — monitors /data/statements/ and triggers
the ingestion pipeline when a new PDF is detected.
"""
import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from backend.config import STATEMENTS_DIR

logger = logging.getLogger(__name__)


class StatementHandler(FileSystemEventHandler):
    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".pdf":
            return
        logger.info("[Watcher] New file detected: %s", path.name)
        try:
            from backend.ingestion.pipeline import ingest_file
            result = ingest_file(path)
            logger.info("[Watcher] Ingestion result: %s", result)
        except Exception as exc:
            logger.error("[Watcher] Ingestion error for %s: %s", path.name, exc)


def start_watcher(directory: Path | None = None, block: bool = True):
    target = directory or STATEMENTS_DIR
    target.mkdir(parents=True, exist_ok=True)

    handler = StatementHandler()
    observer = Observer()
    observer.schedule(handler, str(target), recursive=False)
    observer.start()
    logger.info("[Watcher] Watching %s", target)

    if block:
        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    return observer
