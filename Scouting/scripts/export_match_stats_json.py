"""Export Volleyball Bundesliga match statistics PDFs as structured JSON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


def _add_package_root_to_path() -> None:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lädt eine Statistik-PDF der Volleyball Bundesliga, extrahiert die "
            "Team- und Spielerinnenwerte und speichert alles als JSON-Datei."
        ),
    )
    parser.add_argument(
        "--stats-url",
        required=True,
        help="Vollständige URL zur Statistik-PDF der Volleyball Bundesliga.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Zielpfad für die JSON-Datei. Wird kein Pfad angegeben, landet die Datei "
            "unter docs/data/match_stats/<pdf-id>.json."
        ),
    )
    return parser


def _default_output_path(stats_url: str) -> Path:
    parsed = urlparse(stats_url)
    slug = Path(parsed.path).name or "match_stats"
    return Path("docs/data/match_stats") / f"{slug}.json"


def _serialize_player(player) -> Dict[str, object]:
    metrics_payload = asdict(player.metrics)
    if player.break_points is not None:
        metrics_payload.setdefault("break_points", player.break_points)
    if player.plus_minus is not None:
        metrics_payload.setdefault("plus_minus", player.plus_minus)

    return {
        "name": player.player_name,
        "jersey_number": player.jersey_number,
        "total_points": player.total_points,
        "break_points": player.break_points,
        "plus_minus": player.plus_minus,
        "metrics": metrics_payload,
    }


def _ensure_metrics(summary, report_module):
    metrics = summary.metrics
    if metrics is not None:
        return metrics
    resolved = report_module.resolve_match_stats_metrics(summary)
    if resolved is not None:
        return resolved
    return report_module.MatchStatsMetrics(
        serves_attempts=0,
        serves_errors=0,
        serves_points=0,
        receptions_attempts=0,
        receptions_errors=0,
        receptions_positive_pct="0%",
        receptions_perfect_pct="0%",
        attacks_attempts=0,
        attacks_errors=0,
        attacks_blocked=0,
        attacks_points=0,
        attacks_success_pct="0%",
        blocks_points=0,
        receptions_positive=0,
        receptions_perfect=0,
    )


def _serialize_team(summary, report_module) -> Dict[str, object]:
    metrics = _ensure_metrics(summary, report_module)
    reception_positive = getattr(metrics, "receptions_positive", 0)
    reception_perfect = getattr(metrics, "receptions_perfect", 0)

    players = [_serialize_player(player) for player in summary.players]

    return {
        "team": report_module.pretty_name(summary.team_name),
        "team_raw": summary.team_name,
        "team_slug": report_module.normalize_name(summary.team_name),
        "serve": {
            "attempts": metrics.serves_attempts,
            "errors": metrics.serves_errors,
            "points": metrics.serves_points,
        },
        "reception": {
            "attempts": metrics.receptions_attempts,
            "errors": metrics.receptions_errors,
            "positive_pct": metrics.receptions_positive_pct,
            "perfect_pct": metrics.receptions_perfect_pct,
            "positive": reception_positive,
            "perfect": reception_perfect,
        },
        "attack": {
            "attempts": metrics.attacks_attempts,
            "errors": metrics.attacks_errors,
            "blocked": metrics.attacks_blocked,
            "points": metrics.attacks_points,
            "success_pct": metrics.attacks_success_pct,
        },
        "block": {
            "points": metrics.blocks_points,
        },
        "players": players,
        "player_count": len(players),
        "header_lines": list(summary.header_lines),
        "totals_line": summary.totals_line,
    }


def export_match_stats(stats_url: str, *, output_path: Optional[Path] = None) -> Dict[str, object]:
    _add_package_root_to_path()
    from scripts import report

    summaries = report.fetch_match_stats_totals(stats_url)
    if not summaries:
        raise RuntimeError(
            "Konnte keine Statistikdaten für die angegebene URL extrahieren."
        )

    teams: List[Dict[str, object]] = []
    for summary in summaries:
        teams.append(_serialize_team(summary, report))

    payload: Dict[str, object] = {
        "stats_url": stats_url,
        "team_count": len(teams),
        "teams": teams,
    }

    target_path = output_path or _default_output_path(stats_url)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = export_match_stats(args.stats_url, output_path=args.output)
    except Exception as exc:  # pragma: no cover - CLI safeguard
        print(f"Fehler beim Extrahieren der Statistikdaten: {exc}", file=sys.stderr)
        return 1

    output = args.output or _default_output_path(args.stats_url)
    print(
        "Match-Statistiken exportiert:",
        f"{payload['team_count']} Teams verarbeitet",
        f"-> {output}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution only
    raise SystemExit(main())
