import sqlite3
from pathlib import Path
from contextlib import contextmanager
from backend.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            description     TEXT NOT NULL,
            amount          REAL NOT NULL,
            currency        TEXT NOT NULL DEFAULT 'INR',
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('debit','credit')),
            category        TEXT NOT NULL DEFAULT 'Miscellaneous',
            category_source TEXT NOT NULL DEFAULT 'auto' CHECK(category_source IN ('auto','user')),
            source_file     TEXT NOT NULL,
            raw_text        TEXT,
            confidence_score REAL DEFAULT 1.0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(date, description, amount, source_file)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type           TEXT NOT NULL,
            severity             TEXT NOT NULL CHECK(severity IN ('low','medium','high')),
            description          TEXT NOT NULL,
            related_transactions TEXT,
            created_at           TEXT NOT NULL DEFAULT (datetime('now')),
            status               TEXT NOT NULL DEFAULT 'unread' CHECK(status IN ('unread','dismissed','snoozed')),
            snoozed_until        TEXT,
            whatsapp_sent        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS email_tracking (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id        TEXT NOT NULL,
            mailbox         TEXT NOT NULL CHECK(mailbox IN ('gmail','yahoo')),
            sender          TEXT,
            subject         TEXT,
            fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
            attachment_file TEXT,
            status          TEXT NOT NULL DEFAULT 'processed' CHECK(status IN ('processed','failed','skipped')),
            UNIQUE(email_id, mailbox)
        );

        CREATE TABLE IF NOT EXISTS system_state (
            mailbox         TEXT PRIMARY KEY CHECK(mailbox IN ('gmail','yahoo')),
            last_fetched_at TEXT,
            status          TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success','failed'))
        );

        CREATE TABLE IF NOT EXISTS ingested_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash   TEXT NOT NULL UNIQUE,
            filename    TEXT NOT NULL,
            file_size   INTEGER NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
            status      TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success','failed','warning')),
            failure_reason TEXT,
            transaction_count INTEGER DEFAULT 0,
            verified    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS category_corrections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id  INTEGER NOT NULL REFERENCES transactions(id),
            old_category    TEXT NOT NULL,
            new_category    TEXT NOT NULL,
            corrected_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Seed system_state rows
        INSERT OR IGNORE INTO system_state (mailbox, last_fetched_at) VALUES ('gmail', NULL);
        INSERT OR IGNORE INTO system_state (mailbox, last_fetched_at) VALUES ('yahoo', NULL);

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_transactions_date     ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
        CREATE INDEX IF NOT EXISTS idx_transactions_source   ON transactions(source_file);
        CREATE INDEX IF NOT EXISTS idx_alerts_status         ON alerts(status);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity       ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_email_tracking_mailbox ON email_tracking(mailbox);
        """)
    print(f"[DB] Initialised at {DB_PATH}")


if __name__ == "__main__":
    init_db()
