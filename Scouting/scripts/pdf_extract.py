#!/usr/bin/env python3
"""
Robuste PDF-Textextraktion für lokale und GitHub-Umgebung.
- Nutzt pdfminer.six für PDFs mit echtem Text.
- Fällt automatisch auf OCR (pytesseract + pdf2image) zurück.
- Bricht nicht ab, falls OCR-Tools fehlen.
"""

from __future__ import annotations
from pathlib import Path
import logging

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


def extract_text_auto(pdf_path: str | Path, lang: str = "deu") -> str:
    pdf_path = Path(pdf_path)
    text = ""

    # Versuch 1: pdfminer
    if pdfminer_extract:
        try:
            text = pdfminer_extract(pdf_path)
            if text and len(text.strip()) > 10:
                LOGGER.info(f"✅ Text direkt extrahiert: {pdf_path.name}")
                return text
        except Exception as e:
            LOGGER.warning(f"⚠️ pdfminer fehlgeschlagen ({pdf_path.name}): {e}")

    # Versuch 2: OCR
    if convert_from_path and pytesseract:
        try:
            LOGGER.info(f"📄 OCR-Fallback für {pdf_path.name}")
            pages = convert_from_path(pdf_path, dpi=200)
            text_parts = [pytesseract.image_to_string(p, lang=lang) for p in pages]
            return "\n\n".join(text_parts)
        except Exception as e:
            LOGGER.warning(f"⚠️ OCR fehlgeschlagen ({pdf_path.name}): {e}")

    LOGGER.error(f"❌ Keine Textextraktion möglich für {pdf_path.name}")
    return ""
