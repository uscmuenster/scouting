from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_package_root_to_path() -> None:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Erstellt eine Scouting-Übersicht aller USC-Statistiken aus den offiziellen "
            "VBL-PDFs und schreibt Team- sowie Spielerinnenwerte als JSON-Datei."
        ),
    )
    parser.add_argument(
        "--schedule-url",
        default=None,
        help="Optionaler Override für die CSV-Export-URL des Spielplans.",
    )
    parser.add_argument(
        "--schedule-page-url",
        default=None,
        help="Optionaler Override für die HTML-Seite mit Statistik-Links.",
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=None,
        help=(
            "Pfad zu einer vorhandenen Spielplan-CSV. Wird die Datei gefunden, wird sie "
            "anstelle eines Downloads genutzt."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Zielpfad für die erzeugte JSON-Datei (Standard: docs/data/usc_stats_overview.json).",
    )
    return parser


def main() -> int:
    _add_package_root_to_path()
    from scripts import STATS_OUTPUT_PATH
    from scripts.stats import build_stats_overview

    parser = build_parser()
    args = parser.parse_args()

    output_path = args.output or STATS_OUTPUT_PATH

    build_kwargs = {
        "schedule_path": args.schedule_path,
        "output_path": output_path,
    }
    if args.schedule_url:
        build_kwargs["schedule_csv_url"] = args.schedule_url
    if args.schedule_page_url:
        build_kwargs["schedule_page_url"] = args.schedule_page_url

    payload = build_stats_overview(**build_kwargs)

    print(
        "Scouting-Übersicht aktualisiert:",
        f"{payload['match_count']} Spiele verarbeitet",
        f"-> {output_path}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manuelle Ausführung
    raise SystemExit(main())
