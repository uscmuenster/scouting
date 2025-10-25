import argparse
import json
from datetime import datetime
from pathlib import Path

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
from .stats import (
    HAMBURG_CANONICAL_NAME,
    HAMBURG_OUTPUT_PATH,
    LEAGUE_STATS_OUTPUT_PATH,
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    download_schedule(args.schedule_path, url=args.schedule_url)
    matches = load_schedule_from_file(args.schedule_path)
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

    build_league_stats_overview(
        matches=enriched_matches,
        schedule_csv_url=args.schedule_url,
        schedule_page_url=args.schedule_page_url,
        schedule_path=args.schedule_path,
        output_path=LEAGUE_STATS_OUTPUT_PATH,
        stats_lookup=stats_lookup,
    )

    html = build_html_report(
        generated_at=datetime.now(tz=BERLIN_TZ),
        usc_scouting=stats_payload,
        hamburg_scouting=hamburg_stats_payload,
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
