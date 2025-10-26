#!/usr/bin/env python3
"""
Extrahiert Text aus allen PDF-Spielberichten in docs/data/stats_pdfs/.
Funktioniert lokal und auf GitHub Actions.
Verwendet pdfminer (direkter Text) oder OCR (Tesseract + Poppler) als Fallback.
"""

from __future__ import annotations
import sys
from pathlib import Path
import logging

# ------------------------------------------------------------
# 🧩 Robuste PDF-Textextraktion (integriert)
# ------------------------------------------------------------
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


def extract_text_auto(pdf_path: str | Path, lang: str = "deu") -> str:
    """Extrahiert Text aus einem PDF – automatisch mit pdfminer oder OCR."""
    pdf_path = Path(pdf_path)
    text = ""

    # 1️⃣ Versuch: pdfminer
    if pdfminer_extract:
        try:
            text = pdfminer_extract(pdf_path)
            if text and len(text.strip()) > 10:
                print(f"✅ {pdf_path.name}: direkter Text extrahiert")
                return text
        except Exception as e:
            print(f"⚠️ pdfminer fehlgeschlagen ({pdf_path.name}): {e}")

    # 2️⃣ Versuch: OCR (nur wenn verfügbar)
    if convert_from_path and pytesseract:
        try:
            print(f"📄 {pdf_path.name}: OCR-Fallback aktiviert")
            pages = convert_from_path(pdf_path, dpi=200)
            text_parts = [pytesseract.image_to_string(p, lang=lang) for p in pages]
            return "\n\n".join(text_parts)
        except Exception as e:
            print(f"⚠️ OCR fehlgeschlagen ({pdf_path.name}): {e}")

    print(f"❌ {pdf_path.name}: keine Textextraktion möglich")
    return ""


# ------------------------------------------------------------
# 🚀 Hauptlogik – Ordner verarbeiten
# ------------------------------------------------------------
def main() -> None:
    root = Path(__file__).resolve().parents[1]  # → "Scouting/"
    pdf_dir = root / "docs" / "data" / "stats_pdfs"
    output_dir = root / "docs" / "data" / "stats_texts"

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"⚠️ Keine PDFs gefunden in {pdf_dir.resolve()}")
        return

    for pdf in pdf_files:
        print(f"🔹 Verarbeite {pdf.name} …")
        text = extract_text_auto(pdf)
        out_file = output_dir / f"{pdf.stem}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file.relative_to(root)}")

    print("\n✨ Alle PDFs verarbeitet.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
