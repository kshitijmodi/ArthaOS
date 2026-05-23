"""
End-to-end test seeder.

Generates a realistic synthetic HDFC bank statement PDF, runs it through
the full ingestion pipeline, then runs the eval suite.

Usage:
    python eval/seed_test_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

# ---------------------------------------------------------------------------
# Synthetic transactions — spans 3 months so the agent has enough data
# ---------------------------------------------------------------------------

TRANSACTIONS = [
    # March 2026
    ("01/03/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               450.00,   "Dr"),
    ("03/03/2026", "NEFT/HDFC0001234/Amazon India",                1850.00,  "Dr"),
    ("05/03/2026", "UPI/PHONEPE/BigBasket Groceries",              2100.00,  "Dr"),
    ("07/03/2026", "IMPS/NETFLIX SUBSCRIPTION",                     649.00,  "Dr"),
    ("10/03/2026", "SALARY CREDIT/EMPLOYER TECH PVT LTD",         85000.00, "Cr"),
    ("12/03/2026", "UPI/ZOMATO MEDIA/Zomato Order",                 380.00,  "Dr"),
    ("15/03/2026", "NEFT/ICICI BANK/HOME LOAN EMI",               22000.00, "Dr"),
    ("18/03/2026", "UPI/PHONEPE/Jio Prepaid Recharge",              239.00,  "Dr"),
    ("20/03/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               520.00,   "Dr"),
    ("22/03/2026", "POS/DMART AVENUE SUPERMARTS",                  3400.00,  "Dr"),
    ("25/03/2026", "UPI/SPOTIFY AB/Spotify Premium",                119.00,  "Dr"),
    ("28/03/2026", "NEFT/LIC/LIC PREMIUM PAYMENT",                5000.00,  "Dr"),
    ("30/03/2026", "UPI/MAKEMYTRIP/Hotel Booking",                 8500.00,  "Dr"),
    # April 2026
    ("02/04/2026", "UPI/ZOMATO MEDIA/Zomato Order",                 420.00,  "Dr"),
    ("05/04/2026", "UPI/PHONEPE/BigBasket Groceries",              1950.00,  "Dr"),
    ("07/04/2026", "IMPS/NETFLIX SUBSCRIPTION",                     649.00,  "Dr"),
    ("10/04/2026", "SALARY CREDIT/EMPLOYER TECH PVT LTD",         85000.00, "Cr"),
    ("12/04/2026", "NEFT/ICICI BANK/HOME LOAN EMI",               22000.00, "Dr"),
    ("14/04/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               610.00,  "Dr"),
    ("16/04/2026", "POS/DMART AVENUE SUPERMARTS",                  2800.00,  "Dr"),
    ("18/04/2026", "UPI/PHONEPE/Jio Prepaid Recharge",              239.00,  "Dr"),
    ("20/04/2026", "UPI/SPOTIFY AB/Spotify Premium",                119.00,  "Dr"),
    ("22/04/2026", "NEFT/AMAZON INDIA/Amazon Shopping",            3200.00,  "Dr"),
    ("24/04/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               450.00,  "Dr"),
    ("26/04/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               450.00,  "Dr"),  # duplicate within 7d
    ("28/04/2026", "NEFT/LIC/LIC PREMIUM PAYMENT",                5000.00,  "Dr"),
    # May 2026
    ("02/05/2026", "UPI/ZOMATO MEDIA/Zomato Order",                 510.00,  "Dr"),
    ("04/05/2026", "UPI/PHONEPE/BigBasket Groceries",              2400.00,  "Dr"),
    ("07/05/2026", "IMPS/NETFLIX SUBSCRIPTION",                     649.00,  "Dr"),
    ("10/05/2026", "SALARY CREDIT/EMPLOYER TECH PVT LTD",         85000.00, "Cr"),
    ("12/05/2026", "NEFT/ICICI BANK/HOME LOAN EMI",               22000.00, "Dr"),
    ("14/05/2026", "UPI/SWIGGY TECHNOLOGIES/Swiggy",               780.00,  "Dr"),
    ("16/05/2026", "POS/DMART AVENUE SUPERMARTS",                  4100.00,  "Dr"),
    ("18/05/2026", "UPI/PHONEPE/Jio Prepaid Recharge",              239.00,  "Dr"),
    ("20/05/2026", "UPI/SPOTIFY AB/Spotify Premium",                119.00,  "Dr"),
    ("22/05/2026", "NEFT/MAKEMYTRIP/Flight Booking",              15000.00,  "Dr"),
]

STATEMENT_PERIOD = "01/03/2026 to 31/05/2026"
ACCOUNT_NUMBER   = "XXXX XXXX 4291"


def generate_pdf(output_path: Path) -> Path:
    """
    Generate a plain-text-style PDF whose rows match the parser's TRANSACTION_LINE regex:
      DD/MM/YYYY  Description  Amount.00  Dr/Cr  Balance.00
    Each row is a single Paragraph so PyMuPDF extracts it as one unbroken line.
    """
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            topMargin=40, bottomMargin=40,
                            leftMargin=50, rightMargin=50)
    styles = getSampleStyleSheet()
    mono   = ParagraphStyle("mono", parent=styles["Normal"],
                            fontName="Courier", fontSize=7.5, leading=11)
    story  = []

    story.append(Paragraph("<b>HDFC Bank Account Statement</b>", styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Account No: {ACCOUNT_NUMBER}    Period: {STATEMENT_PERIOD}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Date        Description                                    Amount       Type  Balance",
        mono
    ))
    story.append(Paragraph("-" * 100, mono))

    balance = 120000.00
    for date, desc, amount, tx_type in TRANSACTIONS:
        if tx_type == "Cr":
            balance += amount
        else:
            balance -= amount
        # Format so regex sees: date  description  amount  Dr/Cr  balance
        # TRANSACTION_LINE captures: group1=date, group2=description, group3=amount
        line = (
            f"{date}  {desc:<48}  {amount:>12,.2f}  {tx_type}  {balance:>14,.2f}"
        )
        story.append(Paragraph(line, mono))

    total_cr = sum(a for _, _, a, t in TRANSACTIONS if t == "Cr")
    total_dr = sum(a for _, _, a, t in TRANSACTIONS if t == "Dr")
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Total Credits: {total_cr:,.2f}    Total Debits: {total_dr:,.2f}",
        styles["Normal"]
    ))

    doc.build(story)
    return output_path


def main():
    from backend.storage.database import init_db
    from backend.ingestion.pipeline import ingest_file

    print("\n=== ArthaOS End-to-End Test ===\n")

    # 1. Init DB
    init_db()
    print("✓ Database initialised")

    # 2. Generate synthetic PDF
    statements_dir = Path(__file__).parent.parent / "data" / "statements"
    statements_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = statements_dir / "hdfc_statement_mar_may_2026.pdf"
    generate_pdf(pdf_path)
    print(f"✓ Synthetic statement generated: {pdf_path.name}")

    # 3. Ingest
    result = ingest_file(pdf_path)
    print(f"✓ Ingestion result: {result}")

    if result.get("status") in ("skipped",):
        print("  (already ingested — delete data/arthaos.db to re-run from scratch)")

    stored = result.get("transactions_stored", 0)
    print(f"  Transactions stored: {stored}")

    # 4. Quick sanity checks via DB
    from backend.storage.database import db
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        cats  = conn.execute(
            "SELECT category, COUNT(*) as n FROM transactions GROUP BY category ORDER BY n DESC"
        ).fetchall()
        alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

    print(f"\n  DB totals — transactions: {total}, alerts: {alerts}")
    print("  Categories detected:")
    for row in cats:
        print(f"    {row['category']}: {row['n']}")

    # 5. Run eval
    print("\n--- Running eval suite ---\n")
    from eval.run_eval import run
    run()


if __name__ == "__main__":
    main()
