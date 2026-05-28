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

        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            keywords    TEXT NOT NULL DEFAULT '',
            is_system   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS investment_transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            ticker          TEXT,
            name            TEXT,
            transaction_type TEXT NOT NULL,
            quantity        REAL,
            price_per_unit  REAL,
            total_value     REAL NOT NULL,
            currency        TEXT NOT NULL DEFAULT 'USD',
            account         TEXT NOT NULL,
            broker          TEXT NOT NULL,
            source_file     TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(date, ticker, transaction_type, total_value, source_file)
        );

        CREATE TABLE IF NOT EXISTS charge_alerts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type           TEXT NOT NULL CHECK(alert_type IN ('duplicate','interest','late_fee','suspicious')),
            amount               REAL NOT NULL,
            transaction_id       INTEGER REFERENCES transactions(id),
            confidence_score     REAL NOT NULL DEFAULT 1.0,
            description          TEXT NOT NULL,
            created_at           TEXT NOT NULL DEFAULT (datetime('now')),
            status               TEXT NOT NULL DEFAULT 'unread' CHECK(status IN ('unread','dismissed'))
        );

        CREATE TABLE IF NOT EXISTS investment_holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            as_of_date      TEXT NOT NULL,
            ticker          TEXT,
            name            TEXT NOT NULL,
            quantity        REAL,
            price           REAL,
            total_value     REAL NOT NULL,
            gain_loss       REAL,
            gain_loss_pct   REAL,
            account         TEXT NOT NULL,
            broker          TEXT NOT NULL,
            source_file     TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(as_of_date, ticker, account, source_file)
        );

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            -- what to do
            task_type       TEXT NOT NULL,   -- 'track_category','track_total','monitor_investments','custom'
            description     TEXT NOT NULL,   -- human-readable summary of the task
            params          TEXT NOT NULL DEFAULT '{}',  -- JSON: category, threshold, metric, etc.
            -- when to fire
            fire_at         TEXT NOT NULL,   -- ISO datetime when task should next execute
            repeat_interval TEXT,            -- NULL=one-shot, 'daily','hourly','30min'
            -- lifecycle
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','running','completed','failed','cancelled')),
            -- context
            initiated_by    TEXT NOT NULL DEFAULT 'user'
                            CHECK(initiated_by IN ('user','agent')),
            snapshot        TEXT,            -- JSON: data captured at task creation time
            result          TEXT,            -- JSON: result after execution
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status   ON scheduled_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_fire_at  ON scheduled_tasks(fire_at);

        CREATE TABLE IF NOT EXISTS teller_enrollments (
            enrollment_id   TEXT PRIMARY KEY,
            access_token    TEXT NOT NULL,
            institution     TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_synced_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS teller_accounts (
            account_id        TEXT PRIMARY KEY,
            enrollment_id     TEXT NOT NULL,
            institution       TEXT NOT NULL,
            name              TEXT NOT NULL,
            type              TEXT NOT NULL,
            subtype           TEXT,
            currency          TEXT NOT NULL DEFAULT 'USD',
            balance_available REAL,
            balance_ledger    REAL,
            last_synced_at    TEXT,
            FOREIGN KEY (enrollment_id) REFERENCES teller_enrollments(enrollment_id)
        );

        -- Seed system_state rows
        INSERT OR IGNORE INTO system_state (mailbox, last_fetched_at) VALUES ('gmail', NULL);
        INSERT OR IGNORE INTO system_state (mailbox, last_fetched_at) VALUES ('yahoo', NULL);

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_categories_name       ON categories(name);
        CREATE INDEX IF NOT EXISTS idx_transactions_date     ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
        CREATE INDEX IF NOT EXISTS idx_transactions_source   ON transactions(source_file);
        CREATE INDEX IF NOT EXISTS idx_alerts_status         ON alerts(status);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity       ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_email_tracking_mailbox ON email_tracking(mailbox);
        CREATE INDEX IF NOT EXISTS idx_charge_alerts_type   ON charge_alerts(alert_type);
        CREATE INDEX IF NOT EXISTS idx_charge_alerts_status ON charge_alerts(status);
        CREATE INDEX IF NOT EXISTS idx_inv_tx_date   ON investment_transactions(date);
        CREATE INDEX IF NOT EXISTS idx_inv_tx_broker ON investment_transactions(broker);
        CREATE INDEX IF NOT EXISTS idx_inv_hld_date  ON investment_holdings(as_of_date);
        CREATE INDEX IF NOT EXISTS idx_inv_hld_broker ON investment_holdings(broker);
        """)
    _seed_categories()
    print(f"[DB] Initialised at {DB_PATH}")


def is_duplicate_transaction(
    conn: sqlite3.Connection,
    date: str,
    amount: float,
    transaction_type: str,
    description: str,
    similarity_threshold: float = 0.80,
) -> bool:
    """
    Cross-source duplicate check.
    Returns True if a transaction with the same date, amount, type,
    and sufficiently similar description already exists in the DB.
    """
    from difflib import SequenceMatcher
    rows = conn.execute(
        """SELECT description FROM transactions
           WHERE date = ?
             AND ABS(amount - ?) < 0.01
             AND transaction_type = ?""",
        (date, amount, transaction_type),
    ).fetchall()
    desc_lower = description.lower().strip()
    for row in rows:
        existing = (row["description"] or "").lower().strip()
        if not existing:
            continue
        ratio = SequenceMatcher(None, desc_lower, existing).ratio()
        if ratio >= similarity_threshold:
            return True
    return False


DEFAULT_CATEGORIES = [
    ("Groceries",     "big bazaar,dmart,reliance fresh,zepto,blinkit,grofer,swiggy instamart,bigbasket,more supermart,spencer,lulu", 1),
    ("Dining",        "swiggy,zomato,domino,pizza hut,mcdonald,kfc,burger king,starbucks,subway,haldiram,restaurant,eatery,bistro", 1),
    ("Travel",        "uber,ola,rapido,metro,irctc,makemytrip,redbus,yatra,cleartrip,indigo,air india,spicejet,petrol,fuel", 1),
    ("Utilities",     "electricity,bescom,msedcl,tata power,water board,gas bill,pseg,att,honest networks,airtel broadband", 1),
    ("Subscriptions", "jio,airtel,vodafone,netflix,amazon prime,hotstar,spotify,youtube premium,zee5,sony liv,voot,apple", 1),
    ("Insurance",     "lic,hdfc life,icici pru,bajaj allianz,star health,insurance,amfam,progressive,assurant", 1),
    ("EMIs",          "emi,loan repay,bajaj fin,home loan,car loan,personal loan,emi debit", 1),
    ("Rent",          "rent,house rent,rental,pg rent,accommodation,lease", 1),
    ("Shopping",      "amazon,flipkart,myntra,ajio,nykaa,meesho,snapdeal,croma,vijay sales,reliance digital,walmart,target,costco", 1),
    ("Healthcare",    "apollo,fortis,medplus,1mg,pharmeasy,netmeds,hospital,clinic,pharmacy,diagnostic,cvs,walgreens", 1),
    ("Education",     "udemy,coursera,byju,unacademy,school fee,college fee,tuition,exam fee", 1),
    ("Investments",   "robinhood,schwab,fidelity,vanguard,axis direct,zerodha,groww,mutual fund,stock,etf,brokerage", 1),
    ("Income",        "salary,neft cr,rtgs cr,credit salary,payroll,stipend,paylocity,direct deposit", 1),
    ("Miscellaneous", "", 1),
]


def _seed_categories():
    with db() as conn:
        for name, keywords, is_system in DEFAULT_CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, keywords, is_system) VALUES (?, ?, ?)",
                (name, keywords, is_system),
            )


if __name__ == "__main__":
    init_db()
