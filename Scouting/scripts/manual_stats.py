"""Helpers for loading manual match statistics stored as JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

__all__ = [
    "DEFAULT_MANUAL_STATS_DIR",
    "DEFAULT_MANUAL_STATS_OVERVIEW_PATH",
    "ManualPlayerPayload",
    "ManualTeamStats",
    "ManualTeamFile",
    "build_manual_stats_overview",
    "load_manual_stats_directory",
    "load_manual_team_files",
]

DEFAULT_MANUAL_STATS_DIR = (
    Path(__file__).resolve().parents[2] / "docs" / "data" / "manual_stats"
)
DEFAULT_MANUAL_STATS_OVERVIEW_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "data" / "manual_stats_overview.json"
)


@dataclass(frozen=True)
class ManualPlayerPayload:
    """Raw manual statistics for a single player in a match."""

    name: str
    jersey_number: Optional[int]
    total_points: Optional[int]
    break_points: Optional[int]
    plus_minus: Optional[int]
    metrics: Mapping[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "jersey_number": self.jersey_number,
            "total_points": self.total_points,
            "break_points": self.break_points,
            "plus_minus": self.plus_minus,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class ManualTeamStats:
    """Manual statistics for one team in a match."""

    name: str
    aliases: Sequence[str]
    stats_url: str
    serve: Mapping[str, object]
    reception: Mapping[str, object]
    attack: Mapping[str, object]
    block: Mapping[str, object]
    players: Sequence[ManualPlayerPayload]

    def to_dict(self) -> Dict[str, object]:
        return {
            "team": self.name,
            "stats_url": self.stats_url,
            "serve": dict(self.serve),
            "reception": dict(self.reception),
            "attack": dict(self.attack),
            "block": dict(self.block),
            "players": [player.to_dict() for player in self.players],
        }


@dataclass(frozen=True)
class ManualTeamFile:
    """Manual statistics for a team aggregated across matches."""

    team: str
    aliases: Sequence[str]
    matches: Sequence[ManualTeamStats]

    def to_dict(self) -> Dict[str, object]:
        return {
            "team": self.team,
            "aliases": list(self.aliases),
            "match_count": len(self.matches),
            "matches": [match.to_dict() for match in self.matches],
        }


def _coerce_optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _load_manual_players(entries: Sequence[Mapping[str, object]]) -> List[ManualPlayerPayload]:
    players: List[ManualPlayerPayload] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        metrics = entry.get("metrics")
        if not isinstance(metrics, Mapping):
            metrics = {}
        players.append(
            ManualPlayerPayload(
                name=name,
                jersey_number=_coerce_optional_int(entry.get("jersey_number")),
                total_points=_coerce_optional_int(entry.get("total_points")),
                break_points=_coerce_optional_int(entry.get("break_points")),
                plus_minus=_coerce_optional_int(entry.get("plus_minus")),
                metrics=dict(metrics),
            )
        )
    return players


def _normalize_aliases(values: Sequence[object]) -> List[str]:
    aliases: List[str] = []
    for value in values:
        alias = str(value).strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def _normalize_percentage_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _percentage_count(attempts: int, pct: Optional[str]) -> int:
    if attempts <= 0 or not pct:
        return 0
    cleaned = pct.strip().replace("%", "").replace(",", ".")
    if not cleaned:
        return 0
    try:
        value = float(cleaned)
    except ValueError:
        return 0
    return int(round(attempts * (value / 100)))


def _format_percentage(numerator: int, denominator: int) -> Optional[str]:
    if denominator <= 0:
        return None
    return f"{int(round((numerator / denominator) * 100))}%"


def _load_manual_file(path: Path) -> Optional[ManualTeamFile]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    team_name = str(payload.get("team") or "").strip()
    if not team_name:
        return None
    raw_aliases = payload.get("aliases")
    if isinstance(raw_aliases, (str, bytes)):
        aliases = _normalize_aliases([raw_aliases])
    elif isinstance(raw_aliases, Sequence):
        aliases = _normalize_aliases(raw_aliases)
    else:
        aliases = []
    matches_payload = payload.get("matches")
    if not isinstance(matches_payload, Sequence) or isinstance(matches_payload, (str, bytes)):
        return None
    matches: List[ManualTeamStats] = []
    for match_entry in matches_payload:
        if not isinstance(match_entry, Mapping):
            continue
        stats_url = str(match_entry.get("stats_url") or "").strip()
        if not stats_url:
            continue
        serve_payload = match_entry.get("serve")
        reception_payload = match_entry.get("reception")
        attack_payload = match_entry.get("attack")
        block_payload = match_entry.get("block")
        if not all(
            isinstance(item, Mapping)
            for item in (serve_payload, reception_payload, attack_payload, block_payload)
        ):
            continue
        serve_attempts = _coerce_optional_int(serve_payload.get("attempts"))
        serve_errors = _coerce_optional_int(serve_payload.get("errors"))
        serve_points = _coerce_optional_int(serve_payload.get("points"))
        reception_attempts = _coerce_optional_int(reception_payload.get("attempts"))
        reception_errors = _coerce_optional_int(reception_payload.get("errors"))
        attack_attempts = _coerce_optional_int(attack_payload.get("attempts"))
        attack_errors = _coerce_optional_int(attack_payload.get("errors"))
        attack_blocked = _coerce_optional_int(attack_payload.get("blocked"))
        attack_points = _coerce_optional_int(attack_payload.get("points"))
        block_points = _coerce_optional_int(block_payload.get("points"))
        if None in {
            serve_attempts,
            serve_errors,
            serve_points,
            reception_attempts,
            reception_errors,
            attack_attempts,
            attack_errors,
            attack_blocked,
            attack_points,
            block_points,
        }:
            continue
        reception_positive_pct = _normalize_percentage_string(
            reception_payload.get("positive_pct")
        )
        reception_perfect_pct = _normalize_percentage_string(
            reception_payload.get("perfect_pct")
        )
        attack_success_pct = _normalize_percentage_string(attack_payload.get("success_pct"))
        serve = {
            "attempts": serve_attempts,
            "errors": serve_errors,
            "points": serve_points,
        }
        reception = {
            "attempts": reception_attempts,
            "errors": reception_errors,
            "positive_pct": reception_positive_pct or "0%",
            "perfect_pct": reception_perfect_pct or "0%",
        }
        attack = {
            "attempts": attack_attempts,
            "errors": attack_errors,
            "blocked": attack_blocked,
            "points": attack_points,
            "success_pct": attack_success_pct or "0%",
        }
        block = {"points": block_points}
        players_payload = match_entry.get("players")
        if not isinstance(players_payload, Sequence):
            players_payload = []
        players = _load_manual_players(players_payload) if players_payload else []
        matches.append(
            ManualTeamStats(
                name=team_name,
                aliases=tuple(aliases),
                stats_url=stats_url,
                serve=serve,
                reception=reception,
                attack=attack,
                block=block,
                players=tuple(players),
            )
        )
    if not matches:
        return None
    return ManualTeamFile(team=team_name, aliases=tuple(aliases), matches=tuple(matches))


def load_manual_team_files(directory: Optional[Path] = None) -> List[ManualTeamFile]:
    if directory is None:
        directory = DEFAULT_MANUAL_STATS_DIR
    else:
        directory = Path(directory)

    if not directory.exists():
        return []

    entries: List[ManualTeamFile] = []
    for path in sorted(directory.glob("*.json")):
        loaded = _load_manual_file(path)
        if loaded is not None:
            entries.append(loaded)
    return entries


def load_manual_stats_directory(
    directory: Optional[Path] = None,
) -> Dict[str, List[ManualTeamStats]]:
    """Load manual stats grouped by ``stats_url`` from JSON files."""

    grouped: Dict[str, List[ManualTeamStats]] = {}
    for team_file in load_manual_team_files(directory):
        for match_entry in team_file.matches:
            grouped.setdefault(match_entry.stats_url, []).append(match_entry)
    return grouped


def _build_match_reception_payload(match: ManualTeamStats) -> Dict[str, object]:
    reception = dict(match.reception)
    attempts = int(reception.get("attempts", 0) or 0)
    positive_pct = reception.get("positive_pct")
    perfect_pct = reception.get("perfect_pct")
    reception["positive"] = _percentage_count(attempts, positive_pct)
    reception["perfect"] = _percentage_count(attempts, perfect_pct)
    return reception


def _build_match_payload(match: ManualTeamStats) -> Dict[str, object]:
    return {
        "stats_url": match.stats_url,
        "serve": dict(match.serve),
        "reception": _build_match_reception_payload(match),
        "attack": dict(match.attack),
        "block": dict(match.block),
        "players": [player.to_dict() for player in match.players],
    }


def build_manual_stats_overview(
    *,
    directory: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, object]:
    team_files = load_manual_team_files(directory)

    teams_payload: List[Dict[str, object]] = []
    for team_file in team_files:
        serve_attempts_total = 0
        serve_errors_total = 0
        serve_points_total = 0
        reception_attempts_total = 0
        reception_errors_total = 0
        reception_positive_total = 0
        reception_perfect_total = 0
        attack_attempts_total = 0
        attack_errors_total = 0
        attack_blocked_total = 0
        attack_points_total = 0
        block_points_total = 0
        matches_payload: List[Dict[str, object]] = []
        for match in team_file.matches:
            matches_payload.append(_build_match_payload(match))
            serve_attempts_total += int(match.serve.get("attempts", 0) or 0)
            serve_errors_total += int(match.serve.get("errors", 0) or 0)
            serve_points_total += int(match.serve.get("points", 0) or 0)
            reception_attempts = int(match.reception.get("attempts", 0) or 0)
            reception_attempts_total += reception_attempts
            reception_errors_total += int(match.reception.get("errors", 0) or 0)
            reception_positive_total += _percentage_count(
                reception_attempts, match.reception.get("positive_pct")
            )
            reception_perfect_total += _percentage_count(
                reception_attempts, match.reception.get("perfect_pct")
            )
            attack_attempts = int(match.attack.get("attempts", 0) or 0)
            attack_attempts_total += attack_attempts
            attack_errors_total += int(match.attack.get("errors", 0) or 0)
            attack_blocked_total += int(match.attack.get("blocked", 0) or 0)
            attack_points_total += int(match.attack.get("points", 0) or 0)
            block_points_total += int(match.block.get("points", 0) or 0)

        totals_payload = {
            "serve": {
                "attempts": serve_attempts_total,
                "errors": serve_errors_total,
                "points": serve_points_total,
            },
            "reception": {
                "attempts": reception_attempts_total,
                "errors": reception_errors_total,
                "positive": reception_positive_total,
                "perfect": reception_perfect_total,
                "positive_pct": _format_percentage(
                    reception_positive_total, reception_attempts_total
                ),
                "perfect_pct": _format_percentage(
                    reception_perfect_total, reception_attempts_total
                ),
            },
            "attack": {
                "attempts": attack_attempts_total,
                "errors": attack_errors_total,
                "blocked": attack_blocked_total,
                "points": attack_points_total,
                "success_pct": _format_percentage(
                    attack_points_total, attack_attempts_total
                ),
            },
            "block": {"points": block_points_total},
        }

        teams_payload.append(
            {
                "team": team_file.team,
                "aliases": list(team_file.aliases),
                "match_count": len(team_file.matches),
                "matches": matches_payload,
                "totals": totals_payload,
            }
        )

    teams_payload.sort(key=lambda item: item["team"].lower())

    payload = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "team_count": len(teams_payload),
        "teams": teams_payload,
    }

    if output_path is None:
        output_path = DEFAULT_MANUAL_STATS_OVERVIEW_PATH
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload
