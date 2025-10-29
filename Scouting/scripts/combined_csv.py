"""Create a unified CSV export that merges the HTML dashboard data sources."""

from __future__ import annotations

import csv
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, Mapping, MutableMapping, Optional, Sequence

from zoneinfo import ZoneInfo

from .report2 import canonicalize_player_name, canonicalize_team_name


FIELD_ORDER = [
    "data_sources",
    "match_number",
    "match_id",
    "kickoff",
    "kickoff_comparison",
    "is_home",
    "team",
    "opponent",
    "opponent_comparison",
    "opponent_short",
    "host",
    "host_comparison",
    "location",
    "result_summary",
    "player_name",
    "jersey_number",
    "total_points",
    "break_points",
    "plus_minus",
    "serves_attempts",
    "serves_errors",
    "serves_points",
    "receptions_attempts",
    "receptions_errors",
    "receptions_positive",
    "receptions_perfect",
    "receptions_positive_pct",
    "receptions_perfect_pct",
    "attacks_attempts",
    "attacks_errors",
    "attacks_blocked",
    "attacks_points",
    "attacks_success_pct",
    "blocks_points",
    "stats_url",
    "csv_path",
]


SOURCE_PRIORITY = {"pdf": 1, "csv": 2}

SOURCE_LABELS = {"pdf": "PDF", "csv": "CSV"}

BERLIN_TZ = ZoneInfo("Europe/Berlin")


CSV_TOTAL_MARKER = "totals"


def export_combined_player_stats(
    *,
    league_payload: Mapping[str, object],
    csv_payload: Mapping[str, object],
    csv_data_dir: Path,
    output_path: Path,
) -> int:
    """Merge player level data from the PDF and CSV dashboards into one file."""

    rows: Dict[tuple[str, str, str, str, str], _RowState] = {}

    for entry in _iter_pdf_player_rows(league_payload):
        _merge_row(rows, entry, source="pdf")

    for entry in _iter_csv_player_rows(csv_payload, csv_data_dir):
        _merge_row(rows, entry, source="csv")

    ordered_rows = _serialise_rows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_ORDER)
        writer.writeheader()
        for row in ordered_rows:
            writer.writerow(row)

    return len(ordered_rows)


@dataclass
class _RowState:
    values: Dict[str, object]
    field_priorities: Dict[str, int]
    data_sources: set[str]
    field_values_by_source: Dict[str, Dict[str, object]]


def _make_base_row() -> Dict[str, object]:
    return {field: None for field in FIELD_ORDER if field != "data_sources"}


def _merge_row(
    rows: MutableMapping[tuple[str, str, str, str, str], _RowState],
    values: Dict[str, object],
    *,
    source: str,
) -> None:
    priority = SOURCE_PRIORITY[source]
    match_id = str(values.get("match_id") or "")
    match_number = str(values.get("match_number") or "")
    kickoff_value = str(values.get("kickoff") or "")
    if match_id or match_number:
        kickoff_key = ""
    else:
        kickoff_key = kickoff_value

    key = (
        match_id,
        match_number,
        kickoff_key,
        (values.get("team") or "").lower(),
        (values.get("player_name") or "").lower(),
    )

    if key not in rows:
        base = _make_base_row()
        base.update(values)
        rows[key] = _RowState(
            values=base,
            field_priorities={
                field: priority for field, value in values.items() if value is not None
            },
            data_sources={source},
            field_values_by_source={
                field: {source: value}
                for field, value in values.items()
                if value is not None
            },
        )
        return

    state = rows[key]
    state.data_sources.add(source)
    for field, value in values.items():
        if value is None:
            continue
        field_sources = state.field_values_by_source.setdefault(field, {})
        field_sources[source] = value
        current_priority = state.field_priorities.get(field, 0)
        if state.values.get(field) is None or priority > current_priority:
            state.values[field] = value
            state.field_priorities[field] = priority


def _serialise_rows(
    rows: Mapping[tuple[str, str, str, str, str], _RowState]
) -> list[Dict[str, object]]:
    ordered: list[Dict[str, object]] = []
    for state in rows.values():
        row = dict(state.values)
        row["data_sources"] = _format_data_sources(state)
        row["kickoff_comparison"] = _format_source_comparison(
            state, "kickoff", value_formatter=_format_kickoff_date
        )
        row["host_comparison"] = _format_source_comparison(state, "host")
        row["opponent_comparison"] = _format_source_comparison(state, "opponent")
        ordered.append(row)

    ordered.sort(
        key=lambda row: (
            row.get("kickoff") or "",
            row.get("match_number") or "",
            row.get("team") or "",
            row.get("player_name") or "",
        )
    )
    return ordered


def _format_data_sources(state: _RowState) -> str:
    sources = sorted(state.data_sources)
    if _sources_agree(state):
        return ";".join([*sources, "match"])
    return ";".join(sources)


def _sources_agree(state: _RowState) -> bool:
    if not {"csv", "pdf"}.issubset(state.data_sources):
        return False

    agreement_found = False
    for field_sources in state.field_values_by_source.values():
        if "csv" not in field_sources or "pdf" not in field_sources:
            continue
        agreement_found = True
        if field_sources["csv"] != field_sources["pdf"]:
            return False

    return agreement_found


def _format_source_comparison(
    state: _RowState,
    field: str,
    *,
    value_formatter: Optional[Callable[[object], str]] = None,
) -> str:
    values_by_source = state.field_values_by_source.get(field)
    if not values_by_source:
        value = state.values.get(field)
        return _format_comparison_value(value, value_formatter)

    items: list[tuple[int, str, str]] = []
    for source, raw_value in values_by_source.items():
        priority = SOURCE_PRIORITY.get(source, 99)
        label = SOURCE_LABELS.get(source, source.upper())
        formatted = _format_comparison_value(raw_value, value_formatter)
        items.append((priority, label, formatted))

    if not items:
        value = state.values.get(field)
        return _format_comparison_value(value, value_formatter)

    items.sort(key=lambda item: item[0])
    non_empty_values = {formatted for _, _, formatted in items if formatted}

    if non_empty_values and len(non_empty_values) == 1:
        shared_value = non_empty_values.pop()
        labels = ", ".join(label for _, label, _ in items)
        return f"{labels}: {shared_value}" if shared_value else labels

    parts = []
    for _, label, formatted in items:
        if formatted:
            parts.append(f"{label}: {formatted}")
        else:
            parts.append(label)
    return " / ".join(parts)


def _format_comparison_value(
    value: object, formatter: Optional[Callable[[object], str]] = None
) -> str:
    if value is None:
        return ""
    if formatter is not None:
        return formatter(value)
    text = str(value).strip()
    return text


def _format_kickoff_date(value: object) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return text
    if dt.tzinfo is not None:
        dt = dt.astimezone(BERLIN_TZ)
    return dt.strftime("%d.%m.%Y")


def _iter_pdf_player_rows(payload: Mapping[str, object]) -> Iterator[Dict[str, object]]:
    teams = payload.get("teams", [])
    if not isinstance(teams, Sequence):
        return

    for team_entry in teams:
        if not isinstance(team_entry, Mapping):
            continue
        team_name = canonicalize_team_name(team_entry.get("team", ""))
        match_lookup = _build_match_lookup(team_entry.get("matches", []))

        players = team_entry.get("players", [])
        if not isinstance(players, Sequence):
            continue
        for player_entry in players:
            if not isinstance(player_entry, Mapping):
                continue
            player_name = canonicalize_player_name(player_entry.get("name", ""))
            jersey_number = _parse_int(player_entry.get("jersey_number"))

            for match in player_entry.get("matches", []) or []:
                if not isinstance(match, Mapping):
                    continue
                match_number = _string_or_none(match.get("match_number"))
                match_id = _string_or_none(match.get("match_id"))
                kickoff = match.get("kickoff")
                opponent = canonicalize_team_name(match.get("opponent", ""))
                metrics = match.get("metrics") or {}
                totals = {
                    "total_points": _parse_int(match.get("total_points")),
                    "break_points": _parse_int(match.get("break_points")),
                    "plus_minus": _parse_int(match.get("plus_minus")),
                }

                lookup_key = _match_key(match_id, match_number)
                metadata = match_lookup.get(lookup_key, {})
                if not isinstance(metadata, Mapping):
                    metadata = {}

                host_value = metadata.get("host")
                if host_value:
                    host_name = canonicalize_team_name(host_value)
                elif match.get("is_home"):
                    host_name = team_name
                else:
                    host_name = opponent if opponent else None

                yield {
                    "match_number": match_number,
                    "match_id": match_id,
                    "kickoff": kickoff,
                    "is_home": bool(match.get("is_home")),
                    "team": team_name,
                    "opponent": opponent,
                    "opponent_short": metadata.get("opponent_short")
                    or match.get("opponent_short"),
                    "host": host_name,
                    "location": metadata.get("location"),
                    "result_summary": _extract_result_summary(match, metadata),
                    "player_name": player_name,
                    "jersey_number": jersey_number,
                    "serves_attempts": _parse_int(metrics.get("serves_attempts")),
                    "serves_errors": _parse_int(metrics.get("serves_errors")),
                    "serves_points": _parse_int(metrics.get("serves_points")),
                    "receptions_attempts": _parse_int(
                        metrics.get("receptions_attempts")
                    ),
                    "receptions_errors": _parse_int(
                        metrics.get("receptions_errors")
                    ),
                    "receptions_positive": _parse_int(
                        metrics.get("receptions_positive")
                    ),
                    "receptions_perfect": _parse_int(
                        metrics.get("receptions_perfect")
                    ),
                    "receptions_positive_pct": _parse_percentage(
                        metrics.get("receptions_positive_pct")
                    ),
                    "receptions_perfect_pct": _parse_percentage(
                        metrics.get("receptions_perfect_pct")
                    ),
                    "attacks_attempts": _parse_int(metrics.get("attacks_attempts")),
                    "attacks_errors": _parse_int(metrics.get("attacks_errors")),
                    "attacks_blocked": _parse_int(metrics.get("attacks_blocked")),
                    "attacks_points": _parse_int(metrics.get("attacks_points")),
                    "attacks_success_pct": _parse_percentage(
                        metrics.get("attacks_success_pct")
                    ),
                    "blocks_points": _parse_int(metrics.get("blocks_points")),
                    "stats_url": metadata.get("stats_url") or match.get("stats_url"),
                    "csv_path": None,
                    **totals,
                }


def _iter_csv_player_rows(
    payload: Mapping[str, object], csv_data_dir: Path
) -> Iterator[Dict[str, object]]:
    teams = payload.get("teams", [])
    if not isinstance(teams, Sequence):
        return

    for team_entry in teams:
        if not isinstance(team_entry, Mapping):
            continue
        team_name = canonicalize_team_name(team_entry.get("team", ""))
        matches = team_entry.get("matches", [])
        if not isinstance(matches, Sequence):
            continue

        for match in matches:
            if not isinstance(match, Mapping):
                continue

            match_number = _string_or_none(match.get("match_number"))
            match_id = _string_or_none(match.get("match_id"))
            kickoff = match.get("kickoff")
            opponent = canonicalize_team_name(match.get("opponent", ""))
            host = canonicalize_team_name(match.get("host")) if match.get("host") else None
            result_summary = _extract_result_summary(match, match)
            csv_path = match.get("csv_path")
            if not csv_path:
                continue

            csv_file = csv_data_dir / Path(csv_path).name
            if not csv_file.exists():
                continue

            for row in _read_match_csv(csv_file):
                raw_name = row.get("Name", "")
                if not raw_name:
                    continue
                if raw_name.strip().lower() == CSV_TOTAL_MARKER:
                    continue
                player_name = canonicalize_player_name(raw_name)

                jersey_number = _parse_int(row.get("Number"))
                receptions_attempts = _parse_int(row.get("Total Receptions"))
                receptions_positive_pct = _parse_percentage(
                    row.get("Positive Pass Percentage")
                )
                receptions_perfect_pct = _parse_percentage(
                    row.get("Excellent/ Perfect Pass Percentage")
                )

                host_value = match.get("host")
                if host_value:
                    host_name = canonicalize_team_name(host_value)
                elif match.get("is_home"):
                    host_name = team_name
                else:
                    host_name = opponent if opponent else None

                yield {
                    "match_number": match_number,
                    "match_id": match_id,
                    "kickoff": kickoff,
                    "is_home": bool(match.get("is_home")),
                    "team": team_name,
                    "opponent": opponent,
                    "opponent_short": match.get("opponent_short"),
                    "host": host_name,
                    "location": match.get("location"),
                    "result_summary": result_summary,
                    "player_name": player_name,
                    "jersey_number": jersey_number,
                    "total_points": _parse_int(row.get("Total Points")),
                    "break_points": _parse_int(row.get("Break Points")),
                    "plus_minus": None,
                    "serves_attempts": _parse_int(row.get("Total Serve")),
                    "serves_errors": _parse_int(row.get("Serve Errors")),
                    "serves_points": _parse_int(row.get("Ace")),
                    "receptions_attempts": receptions_attempts,
                    "receptions_errors": _parse_int(row.get("Reception Erros")),
                    "receptions_positive": _estimate_attempts(
                        receptions_attempts, receptions_positive_pct
                    ),
                    "receptions_perfect": _estimate_attempts(
                        receptions_attempts, receptions_perfect_pct
                    ),
                    "receptions_positive_pct": receptions_positive_pct,
                    "receptions_perfect_pct": receptions_perfect_pct,
                    "attacks_attempts": _parse_int(row.get("Total Attacks")),
                    "attacks_errors": _parse_int(row.get("Attack Erros")),
                    "attacks_blocked": _parse_int(row.get("Blocked Attack")),
                    "attacks_points": _parse_int(row.get("Attack Points (Exc.)")),
                    "attacks_success_pct": _parse_percentage(
                        row.get("Attack Points Percentage (Exc.%)")
                    ),
                    "blocks_points": _parse_int(row.get("Block Points")),
                    "stats_url": None,
                    "csv_path": str(csv_path),
                }


def _read_match_csv(path: Path) -> Iterable[Mapping[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row:
                continue
            yield row


def _estimate_attempts(attempts: Optional[int], percentage: Optional[float]) -> Optional[int]:
    if attempts is None or percentage is None:
        return None
    return int(round(attempts * percentage))


def _parse_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except ValueError:
            return None
    text = str(value).strip()
    if not text or text in {"-", ".", "na", "n/a"}:
        return None
    text = text.replace(",", ".")
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_percentage(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    if not text or text in {"-", "."}:
        return None
    text = text.replace(",", ".")
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def _extract_result_summary(
    primary: Mapping[str, object], fallback: Mapping[str, object]
) -> Optional[str]:
    for match in (primary, fallback):
        result = match.get("result")
        if isinstance(result, Mapping):
            summary = result.get("summary")
            if summary:
                return str(summary)
    return None


def _build_match_lookup(matches: object) -> Dict[str, Mapping[str, object]]:
    lookup: Dict[str, Mapping[str, object]] = {}
    if not isinstance(matches, Sequence):
        return lookup
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        key = _match_key(
            _string_or_none(match.get("match_id")),
            _string_or_none(match.get("match_number")),
        )
        lookup[key] = match
    return lookup


def _match_key(match_id: Optional[str], match_number: Optional[str]) -> str:
    return match_id or match_number or ""


def _string_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

