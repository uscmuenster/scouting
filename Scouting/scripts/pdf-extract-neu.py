#!/usr/bin/env python3
"""
Extrahiert Text aus allen PDF-Spielberichten in docs/data/stats_pdfs/
mithilfe von PyPDF2.PdfReader.

Bereinigt den Text:
- behält Buchstaben, Zahlen, Punkte, Prozentzeichen, runde Klammern und Leerzeichen
- entfernt überflüssige Leerzeichen
- fügt auseinandergerissene Buchstaben (z. B. 'S p i e l') wieder zu Wörtern zusammen
"""

from __future__ import annotations
from pathlib import Path
import re
import logging
from PyPDF2 import PdfReader


# ------------------------------------------------------------
# 🧹 Textbereinigung
# ------------------------------------------------------------
def clean_text(raw_text: str) -> str:
    """
    Bereinigt Text aus PDF:
    - behält Buchstaben, Zahlen, Punkte, Prozentzeichen, runde Klammern und Leerzeichen
    - entfernt überflüssige Leerzeichen zwischen Buchstaben
    """
    # Nur erlaubte Zeichen
    cleaned = re.sub(r"[^A-Za-zÄÖÜäöüß0-9().% ]+", " ", raw_text)

    # PDFs mit einzeln gesetzten Buchstaben wie 'S p i e l' korrigieren
    # Ersetzt Leerzeichen zwischen einzelnen Buchstaben
    # Beispiel: 'S p i e l' -> 'Spiel'
    cleaned = re.sub(r"(?:(?<=\b[A-Za-zÄÖÜäöüß])\s(?=[A-Za-zÄÖÜäöüß]\b))", "", cleaned)

    # Doppelte Leerzeichen reduzieren
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    # Zeilenumbrüche vereinheitlichen
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)

    return cleaned.strip()


# ------------------------------------------------------------
# 🧠 Textextraktion mit PyPDF2
# ------------------------------------------------------------
def extract_text_pypdf2(pdf_path: Path) -> str:
    """Liest Text aus einer PDF-Datei mithilfe von PyPDF2."""
    pdf_path = Path(pdf_path)
    text_parts = []

    try:
        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            for i, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    print(f"   🔸 Seite {i}: {len(page_text.split())} Wörter extrahiert")
                text_parts.append(page_text)
    except Exception as e:
        print(f"⚠️ Fehler beim Lesen von {pdf_path.name}: {e}")
        return ""

    return clean_text("\n".join(text_parts))


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
        text = extract_text_pypdf2(pdf)
        out_file = output_dir / f"{pdf.stem}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file.relative_to(root)}")

    print("\n✨ Alle PDFs verarbeitet.")
    print(f"📁 Ergebnisse: {output_dir.resolve()}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
