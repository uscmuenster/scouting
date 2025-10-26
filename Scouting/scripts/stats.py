#!/usr/bin/env python3
"""
Extrahiert Text aus allen PDF-Spielberichten in docs/data/stats_pdfs/
mithilfe von pdfplumber (keine OCR erforderlich).
Bereinigt den Text: behält nur Buchstaben, Zahlen, Punkte, Prozentzeichen,
runde Klammern und Leerzeichen.
"""

from __future__ import annotations
from pathlib import Path
import re
import logging
import pdfplumber


# ------------------------------------------------------------
# 🧹 Textbereinigung
# ------------------------------------------------------------
def clean_text(raw_text: str) -> str:
    """
    Entfernt alle Sonderzeichen außer:
    - Buchstaben (inkl. Umlaute)
    - Zahlen
    - Punkt (.)
    - Prozentzeichen (%)
    - Runde Klammern ()
    - Leerzeichen
    """
    cleaned = re.sub(r"[^A-Za-zÄÖÜäöüß0-9().% ]+", " ", raw_text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
    return cleaned.strip()


# ------------------------------------------------------------
# 🧠 Textextraktion mit pdfplumber
# ------------------------------------------------------------
def extract_text_pdfplumber(pdf_path: str | Path) -> str:
    pdf_path = Path(pdf_path)
    print(f"📄 Extrahiere Text aus {pdf_path.name} …")

    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
                text_parts.append(page_text)
                print(f"   🔸 Seite {i}: {len(page_text.split())} Wörter extrahiert")
    except Exception as e:
        print(f"⚠️ Fehler beim Lesen von {pdf_path.name}: {e}")
        return ""

    raw_text = "\n\n".join(text_parts)
    return clean_text(raw_text)


# ------------------------------------------------------------
# 🚀 Hauptlogik
# ------------------------------------------------------------
def main() -> None:
    # zwei Ebenen hoch (Scouting/scripts → Repo-Root)
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
        text = extract_text_pdfplumber(pdf)
        out_file = output_dir / f"{pdf.stem}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file.relative_to(root)}")

    print("\n✨ Alle PDFs verarbeitet.")
    print(f"📁 Ergebnisse: {output_dir.resolve()}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
