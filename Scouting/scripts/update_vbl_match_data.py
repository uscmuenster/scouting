"""Command-line helper to persist VBL match leg statistics as JSON files."""

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
            "Lädt Spiel- und Satzstatistiken von der VBL-DataProject-Seite und speichert "
            "sie als JSON-Datei im Unterordner docs/data/vbl."
        )
    )
    parser.add_argument(
        "competition_id",
        nargs="?",
        help="ID des Wettbewerbs (Parameter ID in den offiziellen URLs).",
    )
    parser.add_argument(
        "phase_id",
        nargs="?",
        help="ID der Phase (Parameter PID in den offiziellen URLs).",
    )
    parser.add_argument(
        "--club-id",
        help="Optionaler Vereinsfilter (Parameter CID in den offiziellen URLs).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Alternative Basis-URL für das DataProject-Portal (Standard: https://vbl-web.dataproject.com)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optionaler Zielpfad der JSON-Datei (überschreibt --output-dir).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Zielordner für die JSON-Datei (Standard: docs/data/vbl).",
    )
    parser.add_argument(
        "--use-default-datasets",
        action="store_true",
        help="Aktualisiert alle voreingestellten Wettbewerbe anstatt einzelner IDs.",
    )
    return parser


def main() -> int:
    _add_package_root_to_path()

    from scripts import (
        DEFAULT_VBL_BASE_URL,
        DEFAULT_VBL_DATASETS,
        DEFAULT_VBL_OUTPUT_DIR,
        save_vbl_match_leg_results,
    )

    parser = build_parser()
    args = parser.parse_args()

    base_url = args.base_url or DEFAULT_VBL_BASE_URL
    output_dir = args.output_dir or DEFAULT_VBL_OUTPUT_DIR

    if args.use_default_datasets:
        if args.competition_id or args.phase_id:
            parser.error("Positionsargumente sind mit --use-default-datasets nicht erlaubt.")
        if args.output is not None:
            parser.error("--output kann nicht mit --use-default-datasets kombiniert werden.")
        if args.club_id is not None:
            parser.error("--club-id ist bei Verwendung der Standarddatensätze nicht verfügbar.")

        datasets = list(DEFAULT_VBL_DATASETS)
        if not datasets:
            print("Keine vorkonfigurierten VBL-Datensätze definiert.", file=sys.stderr)
            return 1

        for dataset in datasets:
            target_path = save_vbl_match_leg_results(
                dataset.competition_id,
                dataset.phase_id,
                club_id=dataset.club_id,
                base_url=base_url,
                output_dir=output_dir,
            )
            print(
                "VBL-Matchdaten gespeichert:",
                f"Wettbewerb {dataset.competition_id}",
                f"Phase {dataset.phase_id}",
                (f"Verein {dataset.club_id}" if dataset.club_id else "Alle Vereine"),
                f"-> {target_path}",
            )
        return 0

    if not args.competition_id or not args.phase_id:
        parser.error("Es müssen sowohl Wettbewerb als auch Phase angegeben werden.")

    output_path = args.output
    if output_path is None:
        output_path = None  # ensure optional argument remains optional

    target_path = save_vbl_match_leg_results(
        args.competition_id,
        args.phase_id,
        club_id=args.club_id,
        base_url=base_url,
        output_path=output_path,
        output_dir=output_dir,
    )

    print(
        "VBL-Matchdaten gespeichert:",
        f"Wettbewerb {args.competition_id}",
        f"Phase {args.phase_id}",
        f"-> {target_path}",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
