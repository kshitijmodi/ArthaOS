import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox default
USER_WHATSAPP_NUMBER = os.getenv("USER_WHATSAPP_NUMBER", "")   # e.g. whatsapp:+1xxxxxxxxxx

ARTHAOS_API_URL      = os.getenv("ARTHAOS_API_URL", "http://localhost:8000")

REA_HOST = os.getenv("REA_HOST", "0.0.0.0")
REA_PORT = int(os.getenv("REA_PORT", "8001"))
