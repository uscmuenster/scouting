"""Aggregate USC Münster statistics from official VBL match PDFs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .report import (
    DEFAULT_SCHEDULE_URL,
    Match,
    MatchResult,
    MatchStatsMetrics,
    MatchStatsTotals,
    SCHEDULE_PAGE_URL,
    USC_CANONICAL_NAME,
    collect_match_stats_totals,
    enrich_matches,
    fetch_schedule,
    fetch_schedule_match_metadata,
    is_usc,
    load_schedule_from_file,
    pretty_name,
    resolve_match_stats_metrics,
)

DEFAULT_OUTPUT_PATH = Path("docs/data/usc_stats_overview.json")
# Backwards compatible alias so existing call sites continue to work.
STATS_OUTPUT_PATH = DEFAULT_OUTPUT_PATH


@dataclass(frozen=True)
class USCMatchStatsEntry:
    """A single finished USC match with parsed statistics."""

    match: Match
    opponent: str
    is_home: bool
    metrics: MatchStatsMetrics

    def to_dict(self) -> Dict[str, object]:
        result_payload: Optional[Dict[str, object]] = None
        if self.match.result:
            result_payload = _serialize_result(self.match.result)

        return {
            "match_number": self.match.match_number,
            "match_id": self.match.match_id,
            "kickoff": self.match.kickoff.isoformat(),
            "is_home": self.is_home,
            "opponent": self.opponent,
            "host": self.match.host,
            "location": self.match.location,
            "info_url": self.match.info_url,
            "stats_url": self.match.stats_url,
            "scoresheet_url": self.match.scoresheet_url,
            "attendance": self.match.attendance,
            "mvps": [
                {
                    "medal": selection.medal,
                    "name": selection.name,
                    "team": selection.team,
                }
                for selection in self.match.mvps
            ],
            "result": result_payload,
            "metrics": asdict(self.metrics),
        }


@dataclass(frozen=True)
class AggregatedMetrics:
    """Summed and weighted totals across multiple matches."""

    serves_attempts: int
    serves_errors: int
    serves_points: int
    receptions_attempts: int
    receptions_errors: int
    receptions_positive_pct: Optional[str]
    receptions_perfect_pct: Optional[str]
    attacks_attempts: int
    attacks_errors: int
    attacks_blocked: int
    attacks_points: int
    attacks_success_pct: Optional[str]
    blocks_points: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _serialize_result(result: MatchResult) -> Dict[str, object]:
    return {
        "score": result.score,
        "total_points": result.total_points,
        "sets": list(result.sets),
        "summary": result.summary,
    }


def _parse_percentage(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = value.strip().replace("%", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _weighted_percentage(
    entries: Iterable[MatchStatsMetrics],
    attempts_attr: str,
    pct_attr: str,
) -> Optional[str]:
    total_attempts = 0
    weighted_sum = 0.0
    for metrics in entries:
        attempts = getattr(metrics, attempts_attr)
        pct_value = _parse_percentage(getattr(metrics, pct_attr))
        if attempts and pct_value is not None:
            total_attempts += attempts
            weighted_sum += attempts * pct_value
    if total_attempts == 0:
        return None
    weighted_average = weighted_sum / total_attempts
    return f"{round(weighted_average)}%"


def summarize_metrics(entries: Sequence[MatchStatsMetrics]) -> Optional[AggregatedMetrics]:
    if not entries:
        return None

    return AggregatedMetrics(
        serves_attempts=sum(item.serves_attempts for item in entries),
        serves_errors=sum(item.serves_errors for item in entries),
        serves_points=sum(item.serves_points for item in entries),
        receptions_attempts=sum(item.receptions_attempts for item in entries),
        receptions_errors=sum(item.receptions_errors for item in entries),
        receptions_positive_pct=_weighted_percentage(
            entries, "receptions_attempts", "receptions_positive_pct"
        ),
        receptions_perfect_pct=_weighted_percentage(
            entries, "receptions_attempts", "receptions_perfect_pct"
        ),
        attacks_attempts=sum(item.attacks_attempts for item in entries),
        attacks_errors=sum(item.attacks_errors for item in entries),
        attacks_blocked=sum(item.attacks_blocked for item in entries),
        attacks_points=sum(item.attacks_points for item in entries),
        attacks_success_pct=_weighted_percentage(
            entries, "attacks_attempts", "attacks_success_pct"
        ),
        blocks_points=sum(item.blocks_points for item in entries),
    )


def collect_usc_match_stats(
    matches: Sequence[Match],
    *,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCMatchStatsEntry]:
    lookup = stats_lookup or collect_match_stats_totals(matches)
    entries: List[USCMatchStatsEntry] = []
    for match in matches:
        if not match.is_finished or not match.stats_url:
            continue
        summaries = lookup.get(match.stats_url)
        if not summaries:
            continue
        usc_summary: Optional[MatchStatsTotals] = None
        for summary in summaries:
            if is_usc(summary.team_name):
                usc_summary = summary
                break
        if usc_summary is None:
            continue
        metrics = resolve_match_stats_metrics(usc_summary)
        if metrics is None:
            continue
        is_home = is_usc(match.home_team)
        opponent = match.away_team if is_home else match.home_team
        entries.append(
            USCMatchStatsEntry(
                match=match,
                opponent=pretty_name(opponent),
                is_home=is_home,
                metrics=metrics,
            )
        )

    entries.sort(key=lambda entry: entry.match.kickoff)
    return entries


def _load_enriched_matches(
    *,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    schedule_path: Optional[Path] = None,
) -> List[Match]:
    if schedule_path is not None and not isinstance(schedule_path, Path):
        schedule_path = Path(schedule_path)
    schedule_csv_url = schedule_csv_url or DEFAULT_SCHEDULE_URL
    schedule_page_url = schedule_page_url or SCHEDULE_PAGE_URL
    if schedule_path and schedule_path.exists():
        matches = load_schedule_from_file(schedule_path)
    else:
        matches = fetch_schedule(schedule_csv_url)
    metadata = fetch_schedule_match_metadata(schedule_page_url)
    return enrich_matches(matches, metadata)


def build_stats_overview(
    *,
    matches: Optional[Sequence[Match]] = None,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    schedule_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, object]:
    if output_path is not None and not isinstance(output_path, Path):
        output_path = Path(output_path)

    if matches is None:
        matches = _load_enriched_matches(
            schedule_csv_url=schedule_csv_url,
            schedule_page_url=schedule_page_url,
            schedule_path=schedule_path,
        )

    stats_lookup = collect_match_stats_totals(matches)
    usc_entries = collect_usc_match_stats(matches, stats_lookup=stats_lookup)
    metrics_list = [entry.metrics for entry in usc_entries]
    totals = summarize_metrics(metrics_list)

    payload = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "team": USC_CANONICAL_NAME,
        "match_count": len(usc_entries),
        "matches": [entry.to_dict() for entry in usc_entries],
        "totals": totals.to_dict() if totals else None,
    }

    if output_path is None:
        output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload


__all__ = [
    "AggregatedMetrics",
    "DEFAULT_OUTPUT_PATH",
    "STATS_OUTPUT_PATH",
    "USCMatchStatsEntry",
    "build_stats_overview",
    "collect_usc_match_stats",
    "summarize_metrics",
]
