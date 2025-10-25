from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import requests


def _add_package_root_to_path() -> None:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lädt alle verfügbaren Statistik-PDFs aus dem offiziellen VBL-Spielplan "
            "herunter und legt sie im Repository ab."
        ),
    )
    parser.add_argument(
        "--schedule-page-url",
        default=None,
        help="Optionaler Override für die HTML-Seite mit Statistik-Links.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Zielverzeichnis für die PDF-Dateien (Standard: docs/data/stats_pdfs)."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Existierende PDF-Dateien erneut herunterladen und überschreiben.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Anzahl der Download-Versuche pro PDF (Standard: 3).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Initiale Wartezeit zwischen Wiederholungen in Sekunden (Standard: 2.0).",
    )
    return parser


def _collect_stats_links(metadata: Dict[str, Dict[str, Optional[str]]]) -> Dict[str, List[str]]:
    stats_lookup: Dict[str, List[str]] = {}
    for match_number, entry in metadata.items():
        stats_url = (entry.get("stats_url") or "").strip()
        if not stats_url:
            continue
        stats_lookup.setdefault(stats_url, []).append(match_number)
    return stats_lookup


def _ensure_relative(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def main() -> int:
    _add_package_root_to_path()
    from scripts.report import (
        SCHEDULE_PAGE_URL,
        download_stats_pdf,
        fetch_schedule_match_metadata,
        resolve_stats_pdf_cache_path,
        STATS_PDF_CACHE_DIR,
    )

    parser = build_parser()
    args = parser.parse_args()

    schedule_page_url = args.schedule_page_url or SCHEDULE_PAGE_URL
    output_dir = args.output_dir or STATS_PDF_CACHE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = fetch_schedule_match_metadata(schedule_page_url)
    stats_lookup = _collect_stats_links(metadata)

    if not stats_lookup:
        print("Keine Statistik-Links gefunden.")
        return 0

    downloaded = 0
    skipped = 0
    failed: List[str] = []
    index_payload: Dict[str, str] = {}

    for stats_url, match_numbers in sorted(
        stats_lookup.items(), key=lambda item: (item[1][0], item[0])
    ):
        target_path = resolve_stats_pdf_cache_path(stats_url, cache_dir=output_dir)
        existing = target_path.exists()
        if existing and not args.overwrite:
            skipped += 1
        else:
            try:
                download_stats_pdf(
                    stats_url,
                    output_path=target_path,
                    retries=args.retries,
                    delay_seconds=args.delay_seconds,
                )
            except requests.RequestException as exc:  # pragma: no cover - Netzwerk
                failed.append(f"{match_numbers[0]}: {stats_url} -> {exc}")
                continue
            downloaded += 1
            existing = True

        if existing:
            relative_name = _ensure_relative(target_path, output_dir)
            print(
                f"✔︎ {relative_name} für Match {', '.join(match_numbers)} gespeichert"
            )
            for match_number in match_numbers:
                index_payload[match_number] = relative_name
        else:
            print(f"⚠︎ Keine Datei für Match {', '.join(match_numbers)} gespeichert")

    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "Zusammenfassung:",
        f"{downloaded} neue PDFs",
        f"{skipped} übersprungen",
        f"{len(failed)} Fehler",
    )

    if failed:
        print("Fehler beim Download:")
        for entry in failed:
            print(f"  {entry}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI Einstiegspunkt
    raise SystemExit(main())
