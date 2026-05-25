"""
Generates a synthetic Robinhood-style statement PDF for investment pipeline testing.
Uses plain-text paragraphs (not tables) so pdfplumber extracts full lines.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT

OUT = Path(__file__).parent / "robinhood_statement_apr_2026.pdf"

LINES = [
    "ROBINHOOD SECURITIES LLC",
    "Account Statement - April 2026",
    "Account Number: RH-88421-X",
    "Statement Period: 04/01/2026 - 04/30/2026",
    "",
    "PORTFOLIO SUMMARY",
    "As of April 30, 2026",
    "",
    "HOLDINGS",
    "AAPL Apple Inc. 10.000000 $172.50 $1,725.00 $215.00 14.24%",
    "NVDA NVIDIA Corporation 5.000000 $875.20 $4,376.00 $1,126.00 34.68%",
    "TSLA Tesla Inc 3.000000 $168.40 $505.20 -$94.80 -15.81%",
    "VOO Vanguard S&P 500 ETF 8.000000 $512.30 $4,098.40 $548.40 15.44%",
    "AMZN Amazon.com Inc 2.000000 $198.75 $397.50 $47.50 13.56%",
    "",
    "ACCOUNT ACTIVITY",
    "Date Description Type Quantity Price Amount",
    "04/03/2026 NVDA - NVIDIA Corporation Buy 2.000000 $865.10 $1,730.20",
    "04/07/2026 AAPL - Apple Inc Buy 3.000000 $170.80 $512.40",
    "04/10/2026 TSLA - Tesla Inc Sell 1.000000 $172.50 $172.50",
    "04/12/2026 VOO - Vanguard S&P 500 ETF Buy 2.000000 $508.90 $1,017.80",
    "04/15/2026 AAPL - Apple Inc Dividend 0 $0.00 $2.40",
    "04/18/2026 VOO - Vanguard S&P 500 ETF Dividend 0 $0.00 $6.10",
    "04/22/2026 AMZN - Amazon.com Inc Buy 1.000000 $195.30 $195.30",
    "04/28/2026 ACH Deposit Deposit 0 $0.00 $2,000.00",
    "",
    "ACCOUNT VALUE SUMMARY",
    "Total Portfolio Value: $11,102.10",
    "Cash Balance: $302.40",
    "Total Account Value: $11,404.50",
]

def build_pdf():
    doc = SimpleDocTemplate(str(OUT), pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    mono = styles["Code"]
    mono.fontName = "Courier"
    mono.fontSize = 9
    mono.leading = 12
    mono.alignment = TA_LEFT

    story = []
    for line in LINES:
        story.append(Paragraph(line if line else "&nbsp;", mono))
        story.append(Spacer(1, 1))

    doc.build(story)
    print(f"Generated: {OUT}")

if __name__ == "__main__":
    build_pdf()
