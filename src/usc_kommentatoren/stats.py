"""Aggregate USC Münster statistics from official VBL match PDFs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import requests

from .report import (
    DEFAULT_SCHEDULE_URL,
    Match,
    MatchResult,
    MatchPlayerStats,
    MatchStatsMetrics,
    MatchStatsTotals,
    SCHEDULE_PAGE_URL,
    USC_CANONICAL_NAME,
    MANUAL_SCHEDULE_PATH,
    get_team_short_label,
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
    opponent_short: str
    is_home: bool
    metrics: MatchStatsMetrics

    def to_dict(self) -> Dict[str, object]:
        result_payload: Optional[Dict[str, object]] = None
        if self.match.result:
            result_payload = _serialize_result(self.match.result, is_home=self.is_home)

        return {
            "match_number": self.match.match_number,
            "match_id": self.match.match_id,
            "kickoff": self.match.kickoff.isoformat(),
            "is_home": self.is_home,
            "opponent": self.opponent,
            "opponent_short": self.opponent_short,
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
class USCPlayerMatchEntry:
    """Per-match scouting metrics for an individual USC player."""

    player_name: str
    jersey_number: Optional[int]
    match: Match
    opponent: str
    opponent_short: str
    is_home: bool
    metrics: MatchStatsMetrics
    total_points: Optional[int]
    break_points: Optional[int]
    plus_minus: Optional[int]

    def to_dict(self) -> Dict[str, object]:
        result_payload: Optional[Dict[str, object]] = None
        if self.match.result:
            result_payload = _serialize_result(self.match.result, is_home=self.is_home)

        return {
            "player": self.player_name,
            "jersey_number": self.jersey_number,
            "match_number": self.match.match_number,
            "match_id": self.match.match_id,
            "kickoff": self.match.kickoff.isoformat(),
            "is_home": self.is_home,
            "opponent": self.opponent,
            "opponent_short": self.opponent_short,
            "info_url": self.match.info_url,
            "stats_url": self.match.stats_url,
            "result": result_payload,
            "metrics": asdict(self.metrics),
            "total_points": self.total_points,
            "break_points": self.break_points,
            "plus_minus": self.plus_minus,
        }


@dataclass(frozen=True)
class AggregatedMetrics:
    """Summed and weighted totals across multiple matches."""

    serves_attempts: int
    serves_errors: int
    serves_points: int
    receptions_attempts: int
    receptions_errors: int
    receptions_positive: int
    receptions_perfect: int
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


def _flip_scoreline(value: str) -> str:
    parts = value.split(":", 1)
    if len(parts) != 2:
        return value
    left, right = parts
    return f"{right.strip()}:{left.strip()}"


def _build_result_summary(
    score: Optional[str], total_points: Optional[str], sets: Sequence[str]
) -> str:
    segments: List[str] = []
    if score:
        segments.append(score)
    if total_points:
        if segments:
            segments.append(f"/ {total_points}")
        else:
            segments.append(total_points)
    if sets:
        joined_sets = " ".join(sets)
        segments.append(f"({joined_sets})")
    return " ".join(segments) if segments else "Ergebnis offen"


def _serialize_result(result: MatchResult, *, is_home: bool) -> Dict[str, object]:
    score_value: Optional[str] = result.score
    total_points_value: Optional[str] = result.total_points
    set_values: List[str] = list(result.sets)

    if not is_home:
        if score_value:
            score_value = _flip_scoreline(score_value)
        if total_points_value:
            total_points_value = _flip_scoreline(total_points_value)
        set_values = [
            _flip_scoreline(item) if ":" in item else item for item in set_values
        ]

    summary_value = _build_result_summary(score_value, total_points_value, set_values)

    return {
        "score": score_value,
        "total_points": total_points_value,
        "sets": set_values,
        "summary": summary_value,
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
        receptions_positive=sum(getattr(item, "receptions_positive", 0) for item in entries),
        receptions_perfect=sum(getattr(item, "receptions_perfect", 0) for item in entries),
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
        opponent_raw = match.away_team if is_home else match.home_team
        opponent_pretty = pretty_name(opponent_raw)
        opponent_short = get_team_short_label(opponent_pretty)
        entries.append(
            USCMatchStatsEntry(
                match=match,
                opponent=opponent_pretty,
                opponent_short=opponent_short,
                is_home=is_home,
                metrics=metrics,
            )
        )

    entries.sort(key=lambda entry: entry.match.kickoff)
    return entries


def collect_usc_player_stats(
    matches: Sequence[Match],
    *,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCPlayerMatchEntry]:
    lookup = stats_lookup or collect_match_stats_totals(matches)
    entries: List[USCPlayerMatchEntry] = []
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
        is_home = is_usc(match.home_team)
        opponent_raw = match.away_team if is_home else match.home_team
        opponent = pretty_name(opponent_raw)
        opponent_short = get_team_short_label(opponent)
        for player in usc_summary.players:
            entries.append(
                USCPlayerMatchEntry(
                    player_name=player.player_name,
                    jersey_number=player.jersey_number,
                    match=match,
                    opponent=opponent,
                    opponent_short=opponent_short,
                    is_home=is_home,
                    metrics=player.metrics,
                    total_points=player.total_points,
                    break_points=player.break_points,
                    plus_minus=player.plus_minus,
                )
            )
    entries.sort(key=lambda entry: (entry.player_name.lower(), entry.match.kickoff))
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
    manual_schedule_path = MANUAL_SCHEDULE_PATH if MANUAL_SCHEDULE_PATH.exists() else None
    if schedule_path and schedule_path.exists():
        matches = load_schedule_from_file(schedule_path)
    else:
        try:
            matches = fetch_schedule(schedule_csv_url)
        except requests.RequestException:
            if manual_schedule_path:
                matches = load_schedule_from_file(manual_schedule_path)
            else:
                matches = []
    metadata = fetch_schedule_match_metadata(schedule_page_url)
    if not matches and manual_schedule_path:
        matches = load_schedule_from_file(manual_schedule_path)
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
    player_entries = collect_usc_player_stats(matches, stats_lookup=stats_lookup)
    metrics_list = [entry.metrics for entry in usc_entries]
    totals = summarize_metrics(metrics_list)

    player_groups: Dict[str, List[USCPlayerMatchEntry]] = {}
    for entry in player_entries:
        player_groups.setdefault(entry.player_name, []).append(entry)

    players_payload: List[Dict[str, object]] = []
    for player_name, entries_list in player_groups.items():
        entries_list.sort(key=lambda item: item.match.kickoff)
        player_metrics = [item.metrics for item in entries_list]
        player_totals = summarize_metrics(player_metrics)
        total_points_values = [
            item.total_points for item in entries_list if item.total_points is not None
        ]
        break_point_values = [
            item.break_points for item in entries_list if item.break_points is not None
        ]
        plus_minus_values = [
            item.plus_minus for item in entries_list if item.plus_minus is not None
        ]
        jersey_number = entries_list[0].jersey_number
        players_payload.append(
            {
                "name": player_name,
                "jersey_number": jersey_number,
                "match_count": len(entries_list),
                "matches": [item.to_dict() for item in entries_list],
                "totals": player_totals.to_dict() if player_totals else None,
                "total_points": sum(total_points_values)
                if total_points_values
                else None,
                "break_points_total": sum(break_point_values)
                if break_point_values
                else None,
                "plus_minus_total": sum(plus_minus_values)
                if plus_minus_values
                else None,
            }
        )

    players_payload.sort(
        key=lambda item: (
            item.get("jersey_number") is None,
            item.get("jersey_number") or 0,
            str(item.get("name", "")).lower(),
        )
    )

    payload = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "team": USC_CANONICAL_NAME,
        "match_count": len(usc_entries),
        "matches": [entry.to_dict() for entry in usc_entries],
        "totals": totals.to_dict() if totals else None,
        "player_count": len(players_payload),
        "players": players_payload,
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
    "USCPlayerMatchEntry",
    "build_stats_overview",
    "collect_usc_match_stats",
    "collect_usc_player_stats",
    "summarize_metrics",
]
