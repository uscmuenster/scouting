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
        help="Zielpfad für die USC-JSON-Datei (Standard: docs/data/usc_stats_overview.json).",
    )
    parser.add_argument(
        "--hamburg-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Hamburg-JSON-Datei (Standard: docs/data/hamburg_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--aachen-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Aachen-JSON-Datei (Standard: docs/data/aachen_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--schwerin-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Schwerin-JSON-Datei (Standard: docs/data/schwerin_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--dresden-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Dresden-JSON-Datei (Standard: docs/data/dresden_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--wiesbaden-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Wiesbaden-JSON-Datei (Standard: docs/data/wiesbaden_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--erfurt-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Erfurt-JSON-Datei (Standard: docs/data/erfurt_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--league-output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die Liga-JSON-Datei mit allen Teams (Standard: docs/data/league_stats_overview.json)."
        ),
    )
    parser.add_argument(
        "--focus-team",
        default=None,
        help=(
            "Optionaler Teamname, für den die Haupt-JSON generiert wird (Standard: USC Münster)."
        ),
    )
    return parser


def main() -> int:
    _add_package_root_to_path()
    from scripts import (
        AACHEN_CANONICAL_NAME,
        AACHEN_OUTPUT_PATH,
        DRESDEN_CANONICAL_NAME,
        DRESDEN_OUTPUT_PATH,
        ERFURT_CANONICAL_NAME,
        ERFURT_OUTPUT_PATH,
        HAMBURG_CANONICAL_NAME,
        HAMBURG_OUTPUT_PATH,
        LEAGUE_STATS_OUTPUT_PATH,
        SCHWERIN_CANONICAL_NAME,
        SCHWERIN_OUTPUT_PATH,
        WIESBADEN_CANONICAL_NAME,
        WIESBADEN_OUTPUT_PATH,
        STATS_OUTPUT_PATH,
    )
    from scripts.report import USC_CANONICAL_NAME
    from scripts.stats import build_league_stats_overview, build_stats_overview

    parser = build_parser()
    args = parser.parse_args()

    focus_team = args.focus_team or USC_CANONICAL_NAME

    usc_output_path = args.output or STATS_OUTPUT_PATH
    hamburg_output_path = args.hamburg_output or HAMBURG_OUTPUT_PATH
    aachen_output_path = args.aachen_output or AACHEN_OUTPUT_PATH
    schwerin_output_path = args.schwerin_output or SCHWERIN_OUTPUT_PATH
    dresden_output_path = args.dresden_output or DRESDEN_OUTPUT_PATH
    wiesbaden_output_path = args.wiesbaden_output or WIESBADEN_OUTPUT_PATH
    erfurt_output_path = args.erfurt_output or ERFURT_OUTPUT_PATH
    league_output_path = args.league_output or LEAGUE_STATS_OUTPUT_PATH

    build_kwargs = {
        "schedule_path": args.schedule_path,
    }
    if args.schedule_url:
        build_kwargs["schedule_csv_url"] = args.schedule_url
    if args.schedule_page_url:
        build_kwargs["schedule_page_url"] = args.schedule_page_url

    usc_payload = build_stats_overview(
        output_path=usc_output_path,
        focus_team=focus_team,
        **build_kwargs,
    )

    print(
        f"Scouting-Übersicht ({usc_payload['team']}) aktualisiert:",
        f"{usc_payload['match_count']} Spiele verarbeitet",
        f"-> {usc_output_path}",
    )

    hamburg_payload = build_stats_overview(
        output_path=hamburg_output_path,
        focus_team=HAMBURG_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Hamburg-Scouting-Übersicht aktualisiert:",
        f"{hamburg_payload['match_count']} Spiele verarbeitet",
        f"-> {hamburg_output_path}",
    )

    aachen_payload = build_stats_overview(
        output_path=aachen_output_path,
        focus_team=AACHEN_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Aachen-Scouting-Übersicht aktualisiert:",
        f"{aachen_payload['match_count']} Spiele verarbeitet",
        f"-> {aachen_output_path}",
    )

    schwerin_payload = build_stats_overview(
        output_path=schwerin_output_path,
        focus_team=SCHWERIN_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Schwerin-Scouting-Übersicht aktualisiert:",
        f"{schwerin_payload['match_count']} Spiele verarbeitet",
        f"-> {schwerin_output_path}",
    )

    dresden_payload = build_stats_overview(
        output_path=dresden_output_path,
        focus_team=DRESDEN_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Dresden-Scouting-Übersicht aktualisiert:",
        f"{dresden_payload['match_count']} Spiele verarbeitet",
        f"-> {dresden_output_path}",
    )

    wiesbaden_payload = build_stats_overview(
        output_path=wiesbaden_output_path,
        focus_team=WIESBADEN_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Wiesbaden-Scouting-Übersicht aktualisiert:",
        f"{wiesbaden_payload['match_count']} Spiele verarbeitet",
        f"-> {wiesbaden_output_path}",
    )

    erfurt_payload = build_stats_overview(
        output_path=erfurt_output_path,
        focus_team=ERFURT_CANONICAL_NAME,
        **build_kwargs,
    )

    print(
        "Erfurt-Scouting-Übersicht aktualisiert:",
        f"{erfurt_payload['match_count']} Spiele verarbeitet",
        f"-> {erfurt_output_path}",
    )

    league_payload = build_league_stats_overview(
        output_path=league_output_path,
        **build_kwargs,
    )

    print(
        "Liga-Scouting-Übersicht aktualisiert:",
        f"{league_payload['team_count']} Teams verarbeitet",
        f"-> {league_output_path}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manuelle Ausführung
    raise SystemExit(main())
