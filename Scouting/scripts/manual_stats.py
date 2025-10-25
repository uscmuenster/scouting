"""Helpers for loading manual match statistics stored as JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

__all__ = [
    "DEFAULT_MANUAL_STATS_DIR",
    "ManualPlayerPayload",
    "ManualTeamStats",
    "load_manual_stats_directory",
]


DEFAULT_MANUAL_STATS_DIR = (
    Path(__file__).resolve().parents[2] / "docs" / "data" / "manual_stats"
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


def load_manual_stats_directory(
    directory: Optional[Path] = None,
) -> Dict[str, List[ManualTeamStats]]:
    """Load manual stats grouped by ``stats_url`` from JSON files."""

    if directory is None:
        directory = DEFAULT_MANUAL_STATS_DIR
    else:
        directory = Path(directory)

    grouped: Dict[str, List[ManualTeamStats]] = {}
    if not directory.exists():
        return grouped

    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        team_name = str(payload.get("team") or "").strip()
        if not team_name:
            continue
        raw_aliases = payload.get("aliases")
        if isinstance(raw_aliases, (str, bytes)):
            aliases = _normalize_aliases([raw_aliases])
        elif isinstance(raw_aliases, Sequence):
            aliases = _normalize_aliases(raw_aliases)
        else:
            aliases = []
        matches = payload.get("matches")
        if not isinstance(matches, Sequence) or isinstance(matches, (str, bytes)):
            continue
        for match_entry in matches:
            if not isinstance(match_entry, Mapping):
                continue
            stats_url = str(match_entry.get("stats_url") or "").strip()
            if not stats_url:
                continue
            serve = match_entry.get("serve")
            reception = match_entry.get("reception")
            attack = match_entry.get("attack")
            block = match_entry.get("block")
            players_payload = match_entry.get("players")
            if not isinstance(serve, Mapping):
                serve = {}
            if not isinstance(reception, Mapping):
                reception = {}
            if not isinstance(attack, Mapping):
                attack = {}
            if not isinstance(block, Mapping):
                block = {}
            if not isinstance(players_payload, Sequence):
                players_payload = []
            players = _load_manual_players(players_payload) if players_payload else []
            grouped.setdefault(stats_url, []).append(
                ManualTeamStats(
                    name=team_name,
                    aliases=tuple(aliases),
                    stats_url=stats_url,
                    serve=dict(serve),
                    reception=dict(reception),
                    attack=dict(attack),
                    block=dict(block),
                    players=tuple(players),
                )
            )
    return grouped
