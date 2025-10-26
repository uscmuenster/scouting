#!/usr/bin/env python3
"""
Automatische Textextraktion aus allen PDF-Spielberichten in docs/data/stats_pdfs/.
Speichert für jede PDF eine gleichnamige .txt-Datei in docs/data/stats_texts/.
"""
from pathlib import Path
from scripts.pdf_extract import extract_text_auto

PDF_DIR = Path("docs/data/stats_pdfs")
OUTPUT_DIR = Path("docs/data/stats_texts")

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print("⚠️ Keine PDFs gefunden in", PDF_DIR)
        return

    for pdf in pdf_files:
        print(f"📄 Verarbeite {pdf.name} …")
        text = extract_text_auto(pdf)
        out_file = OUTPUT_DIR / (pdf.stem + ".txt")
        out_file.write_text(text, encoding="utf-8")
        print(f"✅ Gespeichert: {out_file}")

    print("\n✨ Alle PDFs verarbeitet.")

if __name__ == "__main__":
    main()
