from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# Paths
DATA_DIR = BASE_DIR / "data"
STATEMENTS_DIR = DATA_DIR / "statements"
FAISS_INDEX_DIR = DATA_DIR / "faiss_index"
DB_PATH = DATA_DIR / "arthaos.db"

# LLM
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "groq" or "gemini"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Embeddings
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80

# Gmail
GMAIL_CREDENTIALS_FILE = BASE_DIR / "gmail_credentials.json"
GMAIL_TOKEN_FILE = BASE_DIR / "gmail_token.json"

# Yahoo IMAP
YAHOO_EMAIL = os.getenv("YAHOO_EMAIL", "")
YAHOO_APP_PASSWORD = os.getenv("YAHOO_APP_PASSWORD", "")
YAHOO_IMAP_HOST = "imap.mail.yahoo.com"
YAHOO_IMAP_PORT = 993

# Whitelisted sender domains for email fetcher
WHITELISTED_DOMAINS = os.getenv(
    "WHITELISTED_DOMAINS",
    "hdfcbank.com,icicibank.com,axisbank.com,sbicard.com,kotakbank.com,"
    "yesbank.in,indusind.com,sc.com,hsbc.co.in,amexindia.com,"
    "alerts.jio.com,airtel.in,vodafone.in",
).split(",")

# Agent thresholds (all configurable)
OVERSPEND_THRESHOLD = float(os.getenv("OVERSPEND_THRESHOLD", "0.25"))   # 25%
ANOMALY_MULTIPLIER = float(os.getenv("ANOMALY_MULTIPLIER", "2.0"))       # 2x category avg
ANOMALY_UNKNOWN_MIN = float(os.getenv("ANOMALY_UNKNOWN_MIN", "2000"))    # ₹2000 floor for unknown categories
DUPLICATE_WINDOW_DAYS = int(os.getenv("DUPLICATE_WINDOW_DAYS", "7"))
BUDGET_OVERSHOOT_THRESHOLD = float(os.getenv("BUDGET_OVERSHOOT_THRESHOLD", "0.20"))  # 20%
AGENT_MIN_MONTHS = int(os.getenv("AGENT_MIN_MONTHS", "2"))
CARD_DUE_ALERT_DAYS = int(os.getenv("CARD_DUE_ALERT_DAYS", "3"))

# Charge analyzer — anomaly detection rules
# Minimum description similarity (0–1) to flag two charges as duplicates
DUPLICATE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.80"))
# Debit amount above which a late-fee alert is escalated to "high" severity
LATE_FEE_HIGH_SEVERITY_AMOUNT = float(os.getenv("LATE_FEE_HIGH_SEVERITY_AMOUNT", "500.0"))
# Days to look back when suppressing re-insertion of identical alert descriptions
ALERT_DEDUP_WINDOW_DAYS = int(os.getenv("ALERT_DEDUP_WINDOW_DAYS", "7"))
# Default confidence score for pattern-matched interest and late-fee alerts
INTEREST_FEE_CONFIDENCE = float(os.getenv("INTEREST_FEE_CONFIDENCE", "0.90"))
LATE_FEE_CONFIDENCE = float(os.getenv("LATE_FEE_CONFIDENCE", "0.90"))
# Default confidence score for keyword-matched suspicious charges
SUSPICIOUS_KEYWORD_CONFIDENCE = float(os.getenv("SUSPICIOUS_KEYWORD_CONFIDENCE", "0.85"))

# FastAPI
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
