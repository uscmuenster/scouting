"""Aggregate USC Münster statistics from official VBL match PDFs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from .report import (
    DEFAULT_SCHEDULE_URL,
    Match,
    MatchResult,
    MatchPlayerStats,
    MatchStatsMetrics,
    MatchStatsTotals,
    SCHEDULE_PAGE_URL,
    TEAM_CANONICAL_LOOKUP,
    USC_CANONICAL_NAME,
    MANUAL_SCHEDULE_PATH,
    collect_match_stats_totals,
    enrich_matches,
    fetch_schedule,
    fetch_schedule_match_metadata,
    get_team_short_label,
    is_usc,
    load_schedule_from_file,
    normalize_name,
    pretty_name,
    resolve_match_stats_metrics,
)

DEFAULT_OUTPUT_PATH = Path("docs/data/usc_stats_overview.json")
# Backwards compatible alias so existing call sites continue to work.
STATS_OUTPUT_PATH = DEFAULT_OUTPUT_PATH

HAMBURG_CANONICAL_NAME = "ETV Hamburger Volksbank Volleys"
HAMBURG_OUTPUT_PATH = Path("docs/data/hamburg_stats_overview.json")

LEAGUE_STATS_OUTPUT_PATH = Path("docs/data/league_stats_overview.json")


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


def _ensure_path(path: Optional[Path | str]) -> Optional[Path]:
    if path is None or isinstance(path, Path):
        return path
    return Path(path)


def _resolve_focus_team_label(team_name: str) -> str:
    canonical = TEAM_CANONICAL_LOOKUP.get(normalize_name(team_name))
    if canonical:
        return canonical
    return pretty_name(team_name)


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


def collect_team_match_stats(
    matches: Sequence[Match],
    *,
    focus_team: str,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCMatchStatsEntry]:
    lookup = stats_lookup or collect_match_stats_totals(matches)
    focus_label = _resolve_focus_team_label(focus_team)
    focus_normalized = normalize_name(focus_label)
    focus_aliases = _build_focus_aliases(focus_team, focus_label, focus_normalized)
    entries: List[USCMatchStatsEntry] = []
    for match in matches:
        if not match.is_finished or not match.stats_url:
            continue
        summaries = lookup.get(match.stats_url)
        if not summaries:
            continue
        focus_summary: Optional[MatchStatsTotals] = None
        for summary in summaries:
            if _matches_focus_team(
                summary.team_name,
                focus_label=focus_label,
                focus_normalized=focus_normalized,
                focus_aliases=focus_aliases,
            ):
                focus_summary = summary
                break
        if focus_summary is None:
            continue
        metrics = resolve_match_stats_metrics(focus_summary)
        if metrics is None:
            continue
        is_home = _matches_focus_team(
            match.home_team,
            focus_label=focus_label,
            focus_normalized=focus_normalized,
            focus_aliases=focus_aliases,
        )
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


def collect_team_player_stats(
    matches: Sequence[Match],
    *,
    focus_team: str,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCPlayerMatchEntry]:
    lookup = stats_lookup or collect_match_stats_totals(matches)
    focus_label = _resolve_focus_team_label(focus_team)
    focus_normalized = normalize_name(focus_label)
    focus_aliases = _build_focus_aliases(focus_team, focus_label, focus_normalized)
    entries: List[USCPlayerMatchEntry] = []
    for match in matches:
        if not match.is_finished or not match.stats_url:
            continue
        summaries = lookup.get(match.stats_url)
        if not summaries:
            continue
        focus_summary: Optional[MatchStatsTotals] = None
        for summary in summaries:
            if _matches_focus_team(
                summary.team_name,
                focus_label=focus_label,
                focus_normalized=focus_normalized,
                focus_aliases=focus_aliases,
            ):
                focus_summary = summary
                break
        if focus_summary is None:
            continue
        is_home = _matches_focus_team(
            match.home_team,
            focus_label=focus_label,
            focus_normalized=focus_normalized,
            focus_aliases=focus_aliases,
        )
        opponent_raw = match.away_team if is_home else match.home_team
        opponent = pretty_name(opponent_raw)
        opponent_short = get_team_short_label(opponent)
        for player in focus_summary.players:
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


def collect_usc_match_stats(
    matches: Sequence[Match],
    *,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCMatchStatsEntry]:
    return collect_team_match_stats(
        matches,
        focus_team=USC_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )


def collect_usc_player_stats(
    matches: Sequence[Match],
    *,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> List[USCPlayerMatchEntry]:
    return collect_team_player_stats(
        matches,
        focus_team=USC_CANONICAL_NAME,
        stats_lookup=stats_lookup,
    )


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


def _prepare_matches_and_lookup(
    matches: Optional[Sequence[Match]],
    *,
    schedule_csv_url: str,
    schedule_page_url: str,
    schedule_path: Optional[Path],
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]],
) -> Tuple[Sequence[Match], Mapping[str, Sequence[MatchStatsTotals]]]:
    if matches is None:
        matches = _load_enriched_matches(
            schedule_csv_url=schedule_csv_url,
            schedule_page_url=schedule_page_url,
            schedule_path=schedule_path,
        )

    if stats_lookup is None:
        stats_lookup = collect_match_stats_totals(matches)

    return matches, stats_lookup


def _build_stats_payload(
    matches: Sequence[Match],
    *,
    focus_team: str,
    stats_lookup: Mapping[str, Sequence[MatchStatsTotals]],
    generated_at: Optional[datetime] = None,
) -> Dict[str, object]:
    focus_label = _resolve_focus_team_label(focus_team)
    usc_entries = collect_team_match_stats(
        matches,
        focus_team=focus_team,
        stats_lookup=stats_lookup,
    )
    player_entries = collect_team_player_stats(
        matches,
        focus_team=focus_team,
        stats_lookup=stats_lookup,
    )
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

    if generated_at is None:
        generated_at = datetime.now(tz=timezone.utc)

    return {
        "generated": generated_at.isoformat(),
        "team": focus_label,
        "match_count": len(usc_entries),
        "matches": [entry.to_dict() for entry in usc_entries],
        "totals": totals.to_dict() if totals else None,
        "player_count": len(players_payload),
        "players": players_payload,
    }


def build_stats_overview(
    *,
    matches: Optional[Sequence[Match]] = None,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    schedule_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    focus_team: str = USC_CANONICAL_NAME,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
) -> Dict[str, object]:
    output_path = _ensure_path(output_path)

    matches, stats_lookup = _prepare_matches_and_lookup(
        matches,
        schedule_csv_url=schedule_csv_url,
        schedule_page_url=schedule_page_url,
        schedule_path=schedule_path,
        stats_lookup=stats_lookup,
    )

    payload = _build_stats_payload(
        matches,
        focus_team=focus_team,
        stats_lookup=stats_lookup,
    )

    if output_path is None:
        output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload


def _collect_league_team_names(
    matches: Sequence[Match],
    *,
    team_names: Optional[Sequence[str]] = None,
) -> List[str]:
    normalized_to_label: Dict[str, str] = {}

    def _register(name: str) -> None:
        label = _resolve_focus_team_label(name)
        normalized = normalize_name(label)
        normalized_to_label.setdefault(normalized, label)

    if team_names:
        for name in team_names:
            _register(name)

    for match in matches:
        _register(match.home_team)
        _register(match.away_team)

    return sorted(normalized_to_label.values(), key=lambda value: value.lower())


def build_league_stats_overview(
    *,
    matches: Optional[Sequence[Match]] = None,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    schedule_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    stats_lookup: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
    team_names: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    output_path = _ensure_path(output_path)

    matches, stats_lookup = _prepare_matches_and_lookup(
        matches,
        schedule_csv_url=schedule_csv_url,
        schedule_page_url=schedule_page_url,
        schedule_path=schedule_path,
        stats_lookup=stats_lookup,
    )

    generated_at = datetime.now(tz=timezone.utc)
    league_team_names = _collect_league_team_names(matches, team_names=team_names)

    teams_payload = [
        _build_stats_payload(
            matches,
            focus_team=team_name,
            stats_lookup=stats_lookup,
            generated_at=generated_at,
        )
        for team_name in league_team_names
    ]

    payload = {
        "generated": generated_at.isoformat(),
        "team_count": len(teams_payload),
        "teams": teams_payload,
    }

    if output_path is None:
        output_path = LEAGUE_STATS_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload


def _build_focus_aliases(
    focus_team: str, focus_label: str, focus_normalized: str
) -> Set[str]:
    aliases: Set[str] = set()
    if focus_team:
        aliases.add(normalize_name(focus_team))
    aliases.add(focus_normalized)
    for alias_normalized, canonical in TEAM_CANONICAL_LOOKUP.items():
        if normalize_name(canonical) == focus_normalized:
            aliases.add(alias_normalized)
    return {alias for alias in aliases if alias}


def _matches_focus_team(
    name: str,
    *,
    focus_label: str,
    focus_normalized: str,
    focus_aliases: Set[str],
) -> bool:
    normalized = normalize_name(name)
    if normalized in focus_aliases:
        return True
    canonical = TEAM_CANONICAL_LOOKUP.get(normalized)
    if canonical and normalize_name(canonical) == focus_normalized:
        return True
    for alias in focus_aliases:
        if alias in normalized:
            return True
    if focus_label == USC_CANONICAL_NAME and is_usc(name):
        return True
    return False


__all__ = [
    "AggregatedMetrics",
    "DEFAULT_OUTPUT_PATH",
    "STATS_OUTPUT_PATH",
    "HAMBURG_CANONICAL_NAME",
    "HAMBURG_OUTPUT_PATH",
    "LEAGUE_STATS_OUTPUT_PATH",
    "USCMatchStatsEntry",
    "USCPlayerMatchEntry",
    "build_stats_overview",
    "build_league_stats_overview",
    "collect_team_match_stats",
    "collect_team_player_stats",
    "collect_usc_match_stats",
    "collect_usc_player_stats",
    "summarize_metrics",
]
