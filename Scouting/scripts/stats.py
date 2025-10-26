#!/usr/bin/env python3
"""
Extrahiert Text aus allen PDF-Spielberichten in docs/data/stats_pdfs/.
Funktioniert lokal und in GitHub Actions.
Verwendet pdfminer (direkter Text) oder OCR (Tesseract + Poppler) als Fallback.
"""

from __future__ import annotations
import sys
from pathlib import Path
import logging

# --- Fix: sys.path erweitern, damit "scripts" gefunden wird ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pdf_extract import extract_text_auto  # ← Hilfsfunktion

PDF_DIR = ROOT / "docs" / "data" / "stats_pdfs"
OUTPUT_DIR = ROOT / "docs" / "data" / "stats_texts"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️ Keine PDFs gefunden in {PDF_DIR.resolve()}")
        return

    for pdf in pdf_files:
        print(f"🔹 Verarbeite {pdf.name} …")
        text = extract_text_auto(pdf)
        out_file = OUTPUT_DIR / f"{pdf.stem}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file.relative_to(ROOT)}")

    print("\n✨ Alle PDFs verarbeitet.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
