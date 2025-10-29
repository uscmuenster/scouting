import argparse
import json
from datetime import datetime
from pathlib import Path

from .combined_csv import export_combined_player_stats
from .report import (
    BERLIN_TZ,
    DEFAULT_SCHEDULE_URL,
    SCHEDULE_PAGE_URL,
    build_html_report,
    collect_match_stats_totals,
    download_schedule,
    enrich_matches,
    fetch_schedule_match_metadata,
    load_schedule_from_file,
)
from .report2 import (
    CSV_DIRECTORY,
    HTML_OUTPUT_PATH as CSV_HTML_OUTPUT_PATH,
    JSON_OUTPUT_PATH as CSV_JSON_OUTPUT_PATH,
    build_overview_payload as build_csv_overview_payload,
    render_html as render_csv_html,
)
from .stats import (
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
    build_league_stats_overview,
    build_stats_overview,
)

DEFAULT_OUTPUT_PATH = Path("docs/index.html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the USC Münster scouting overview"
    )
    parser.add_argument(
        "--schedule-url",
        default=DEFAULT_SCHEDULE_URL,
        help="CSV export URL of the Volleyball Bundesliga schedule.",
    )
    parser.add_argument(
        "--schedule-page-url",
        default=SCHEDULE_PAGE_URL,
        help="HTML page containing schedule metadata and statistics links.",
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=Path("data/schedule.csv"),
        help="Local cache file for the downloaded schedule CSV.",
    )
    parser.add_argument(
        "--skip-schedule-download",
        action="store_true",
        help=(
            "Reuse an existing schedule CSV without downloading it again. "
            "If the file is missing, a download is attempted regardless."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Target HTML output path (default: docs/index.html).",
    )
    parser.add_argument(
        "--data-output",
        type=Path,
        default=STATS_OUTPUT_PATH,
        help="Target JSON output for aggregated statistics (default: docs/data/usc_stats_overview.json).",
    )
    parser.add_argument(
        "--skip-html",
        action="store_true",
        help=(
            "Skip generating the HTML report and manifest so only the JSON overviews are updated."
        ),
    )
    parser.add_argument(
        "--skip-csv-report",
        action="store_true",
        help="Skip generating the CSV-based scouting overview (index2).",
    )
    parser.add_argument(
        "--csv-data-dir",
        type=Path,
        default=CSV_DIRECTORY,
        help="Directory containing exported CSV statistics (default: docs/data/csv).",
    )
    parser.add_argument(
        "--csv-json-output",
        type=Path,
        default=CSV_JSON_OUTPUT_PATH,
        help="Target JSON output for the CSV-based overview (default: docs/data/index2_stats_overview.json).",
    )
    parser.add_argument(
        "--csv-html-output",
        type=Path,
        default=CSV_HTML_OUTPUT_PATH,
        help="Target HTML output for the CSV-based overview (default: docs/index2.html).",
    )
    parser.add_argument(
        "--combined-player-csv-output",
        type=Path,
        default=Path("docs/data/combined_player_stats.csv"),
        help=(
            "Target CSV path for the merged player statistics overview (default: "
            "docs/data/combined_player_stats.csv)."
        ),
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    schedule_path = args.schedule_path
    should_download = True
    if args.skip_schedule_download and schedule_path and schedule_path.exists():
        should_download = False

    if should_download:
        download_schedule(schedule_path, url=args.schedule_url)

    matches = load_schedule_from_file(schedule_path)
    metadata = fetch_schedule_match_metadata(args.schedule_page_url)
    detail_cache: dict[str, dict[str, object]] = {}
    enriched_matches = enrich_matches(matches, metadata, detail_cache)

    stats_lookup = collect_match_stats_totals(enriched_matches)

    stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=args.data_output,
        stats_lookup=stats_lookup,
    )

    hamburg_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=HAMBURG_OUTPUT_PATH,
        focus_team=HAMBURG_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    aachen_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=AACHEN_OUTPUT_PATH,
        focus_team=AACHEN_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    schwerin_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=SCHWERIN_OUTPUT_PATH,
        focus_team=SCHWERIN_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    dresden_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=DRESDEN_OUTPUT_PATH,
        focus_team=DRESDEN_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    print(
        "USC scouting overview updated:",
        f"{stats_payload['match_count']} matches processed -> {args.data_output}",
    )

    print(
        "Hamburg scouting overview updated:",
        f"{hamburg_stats_payload['match_count']} matches processed -> {HAMBURG_OUTPUT_PATH}",
    )

    print(
        "Aachen scouting overview updated:",
        f"{aachen_stats_payload['match_count']} matches processed -> {AACHEN_OUTPUT_PATH}",
    )

    print(
        "Schwerin scouting overview updated:",
        f"{schwerin_stats_payload['match_count']} matches processed -> {SCHWERIN_OUTPUT_PATH}",
    )

    print(
        "Dresden scouting overview updated:",
        f"{dresden_stats_payload['match_count']} matches processed -> {DRESDEN_OUTPUT_PATH}",
    )

    wiesbaden_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=WIESBADEN_OUTPUT_PATH,
        focus_team=WIESBADEN_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    print(
        "Wiesbaden scouting overview updated:",
        f"{wiesbaden_stats_payload['match_count']} matches processed -> {WIESBADEN_OUTPUT_PATH}",
    )

    erfurt_stats_payload = build_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=ERFURT_OUTPUT_PATH,
        focus_team=ERFURT_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )

    print(
        "Erfurt scouting overview updated:",
        f"{erfurt_stats_payload['match_count']} matches processed -> {ERFURT_OUTPUT_PATH}",
    )

    league_payload = build_league_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=LEAGUE_STATS_OUTPUT_PATH,
        stats_lookup=stats_lookup,
    )

    print(
        "League scouting overview updated:",
        f"{league_payload['team_count']} teams processed -> {LEAGUE_STATS_OUTPUT_PATH}",
    )

    if not args.skip_csv_report:
        csv_payload = build_csv_overview_payload(args.csv_data_dir)

        csv_json_output = args.csv_json_output
        csv_json_output.parent.mkdir(parents=True, exist_ok=True)
        csv_json_output.write_text(
            json.dumps(csv_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        try:
            csv_json_relative = csv_json_output.relative_to(Path.cwd())
        except ValueError:
            csv_json_relative = csv_json_output

        print(
            "CSV scouting overview updated:",
            f"{csv_payload['team_count']} teams processed -> {csv_json_relative}",
        )

        combined_output = args.combined_player_csv_output
        combined_count = export_combined_player_stats(
            league_payload=league_payload,
            csv_payload=csv_payload,
            csv_data_dir=args.csv_data_dir,
            output_path=combined_output,
        )

        try:
            combined_relative = combined_output.relative_to(Path.cwd())
        except ValueError:
            combined_relative = combined_output

        print(
            "Combined player CSV generated:",
            f"{combined_count} rows -> {combined_relative}",
        )

        if not args.skip_html:
            csv_html_output = args.csv_html_output
            csv_html_output.parent.mkdir(parents=True, exist_ok=True)
            csv_html_output.write_text(
                render_csv_html(json_path=csv_json_output),
                encoding="utf-8",
            )

            try:
                csv_html_relative = csv_html_output.relative_to(Path.cwd())
            except ValueError:
                csv_html_relative = csv_html_output

            print("CSV HTML dashboard generated:", csv_html_relative)
        else:
            print("CSV HTML dashboard generation skipped via --skip-html")
    else:
        print("CSV scouting overview generation skipped via --skip-csv-report")

    if args.skip_html:
        return 0

    html = build_html_report(
        generated_at=datetime.now(tz=BERLIN_TZ),
        usc_scouting=stats_payload,
        hamburg_scouting=hamburg_stats_payload,
        aachen_scouting=aachen_stats_payload,
        schwerin_scouting=schwerin_stats_payload,
        dresden_scouting=dresden_stats_payload,
        wiesbaden_scouting=wiesbaden_stats_payload,
        erfurt_scouting=erfurt_stats_payload,
        league_scouting=league_payload,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    manifest_payload = {
        "name": "Scouting USC Münster",
        "short_name": "USC Scouting",
        "description": "Aggregierte Spielerinnen-Statistiken des USC Münster aus den offiziellen VBL-PDFs.",
        "lang": "de",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#0f766e",
        "theme_color": "#0f766e",
        "icons": [
            {"src": "favicon.png", "sizes": "192x192", "type": "image/png"},
            {
                "src": "favicon.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    manifest_path = args.output.parent / "manifest.webmanifest"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("HTML report generated:", args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
