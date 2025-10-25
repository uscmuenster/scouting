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
        description="Erzeugt eine Übersicht manueller Teamstatistiken aus JSON-Dateien.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=None,
        help=(
            "Pfad zu den manuellen Statistikdateien (Standard: docs/data/manual_stats)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Übersicht (Standard: docs/data/manual_stats_overview.json)."
        ),
    )
    return parser


def main() -> int:
    _add_package_root_to_path()
    from scripts.manual_stats import (
        DEFAULT_MANUAL_STATS_OVERVIEW_PATH,
        build_manual_stats_overview,
    )

    parser = build_parser()
    args = parser.parse_args()

    payload = build_manual_stats_overview(
        directory=args.directory,
        output_path=args.output,
    )

    output_path = args.output or DEFAULT_MANUAL_STATS_OVERVIEW_PATH
    print(
        "Manuelle Statistik-Übersicht aktualisiert:",
        f"{payload['team_count']} Teams verarbeitet",
        f"-> {output_path}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manueller Aufruf
    raise SystemExit(main())
