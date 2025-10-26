#!/usr/bin/env python3
"""
Robuste PDF-Textextraktion für lokale und GitHub-Umgebung.
- Nutzt pdfminer.six für PDFs mit echtem Text.
- Fällt automatisch auf OCR (pytesseract + pdf2image) zurück, wenn kein Text extrahierbar ist.
- Bricht NICHT ab, falls OCR-Tools fehlen.
"""

from __future__ import annotations
from pathlib import Path
import logging

# optional import
try:
    from pdfminer.high_level import extract_text as pdfminer_extract
except ImportError:
    pdfminer_extract = None

try:
    from pdf2image import convert_from_path
    import pytesseract
except ImportError:
    convert_from_path = None
    pytesseract = None

LOGGER = logging.getLogger(__name__)


def extract_text_auto(pdf_path: str, lang: str = "deu") -> str:
    pdf_path = Path(pdf_path)

    # 1️⃣ Versuch: reinen Text extrahieren (pdfminer)
    text = ""
    if pdfminer_extract:
        try:
            text = pdfminer_extract(pdf_path)
            if text and len(text.strip()) > 10:
                LOGGER.info("✅ PDF-Text erfolgreich mit pdfminer gelesen")
                return text
        except Exception as e:
            LOGGER.warning(f"pdfminer fehlgeschlagen: {e}")

    # 2️⃣ Fallback: OCR, falls möglich
    if convert_from_path and pytesseract:
        try:
            LOGGER.info("📄 Fallback auf OCR (Tesseract)")
            pages = convert_from_path(pdf_path, dpi=300)
            text_parts = [pytesseract.image_to_string(p, lang=lang) for p in pages]
            return "\n\n".join(text_parts)
        except Exception as e:
            LOGGER.warning(f"OCR fehlgeschlagen: {e}")

    # 3️⃣ Kein Text verfügbar
    LOGGER.error("❌ Weder pdfminer noch OCR verfügbar – kein Text extrahiert")
    return ""


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python pdf_extract.py <pdf_path>")
        sys.exit(1)
    pdf_path = sys.argv[1]
    print(extract_text_auto(pdf_path))
