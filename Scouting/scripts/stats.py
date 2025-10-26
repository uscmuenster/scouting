#!/usr/bin/env python3
"""
Extrahiert Text aus allen PDF-Spielberichten in docs/data/stats_pdfs/.
Funktioniert lokal und auf GitHub Actions.
Verwendet pdfminer (direkter Text) oder optimiertes OCR (Tesseract + Poppler).
Anschließend werden nur Buchstaben, Zahlen, Punkte und runde Klammern behalten.
"""

from __future__ import annotations
from pathlib import Path
import re
import logging
from PIL import Image, ImageOps, ImageFilter

# ------------------------------------------------------------
# 📚 OCR / PDF Abhängigkeiten laden
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


# ------------------------------------------------------------
# 🧩 Bildvorverarbeitung für bessere OCR-Erkennung
# ------------------------------------------------------------
def _preprocess_image(img: Image.Image) -> Image.Image:
    """Verbessert Kontrast und Lesbarkeit für OCR."""
    img = img.convert("L")  # Graustufen
    img = ImageOps.autocontrast(img)
    img = ImageOps.invert(img)  # Dunkle Schrift auf hellem Grund
    img = img.filter(ImageFilter.SHARPEN)
    return img


# ------------------------------------------------------------
# 🧹 Textbereinigung: nur Zahlen, Buchstaben, Punkte, Klammern, Leerzeichen
# ------------------------------------------------------------
def clean_text(raw_text: str) -> str:
    # Nur erlaubte Zeichen behalten
    cleaned = re.sub(r"[^A-Za-zÄÖÜäöüß0-9()%. ]+", " ", raw_text)
    # Mehrfache Leerzeichen reduzieren
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Zeilenumbrüche vereinheitlichen
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
    return cleaned.strip()


# ------------------------------------------------------------
# 🧠 Intelligente Textextraktion (Text oder OCR)
# ------------------------------------------------------------
def extract_text_auto(pdf_path: str | Path, lang: str = "deu+eng") -> str:
    """Liest Text aus PDF automatisch (pdfminer oder OCR) und bereinigt ihn."""
    pdf_path = Path(pdf_path)
    text = ""

    # 1️⃣ Versuch: pdfminer
    if pdfminer_extract:
        try:
            text = pdfminer_extract(pdf_path)
            if text and len(text.strip()) > 10:
                print(f"✅ {pdf_path.name}: direkter Text extrahiert")
                return clean_text(text)
        except Exception as e:
            print(f"⚠️ pdfminer fehlgeschlagen ({pdf_path.name}): {e}")

    # 2️⃣ Versuch: OCR (optimiert)
    if convert_from_path and pytesseract:
        try:
            print(f"📄 {pdf_path.name}: OCR-Fallback aktiviert (optimiert)")
            pages = convert_from_path(pdf_path, dpi=300)
            custom_config = r"--oem 3 --psm 6 -c preserve_interword_spaces=1"

            text_parts = []
            for i, page in enumerate(pages, start=1):
                img = _preprocess_image(page)
                ocr_text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
                text_parts.append(ocr_text)
                print(f"   🔸 Seite {i}: OCR abgeschlossen ({len(ocr_text.split())} Wörter)")

            return clean_text("\n\n".join(text_parts))
        except Exception as e:
            print(f"⚠️ OCR fehlgeschlagen ({pdf_path.name}): {e}")

    print(f"❌ {pdf_path.name}: keine Textextraktion möglich")
    return ""


# ------------------------------------------------------------
# 🚀 Hauptlogik – verarbeitet alle PDFs
# ------------------------------------------------------------
def main() -> None:
    # zwei Ebenen hoch (Scouting/scripts → root)
    root = Path(__file__).resolve().parents[2]
    pdf_dir = root / "docs" / "data" / "stats_pdfs"
    output_dir = root / "docs" / "data" / "stats_texts"

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"⚠️ Keine PDFs gefunden in {pdf_dir.resolve()}")
        return

    for pdf in pdf_files:
        print(f"\n🔹 Verarbeite {pdf.name} …")
        text = extract_text_auto(pdf)
        out_file = output_dir / f"{pdf.stem}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file.relative_to(root)}")

    print("\n✨ Alle PDFs verarbeitet.")
    print(f"📁 Ergebnisse: {output_dir.resolve()}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
