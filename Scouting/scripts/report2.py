"""Generate an HTML/JSON report that is backed by the CSV exports.

This helper focuses on the pre-parsed CSV files that live under
``docs/data/csv``.  Unlike :mod:`Scouting.scripts.report`, which downloads
PDFs and extracts their statistics, this module keeps everything offline and
only works with the CSV data that already exists in the repository.

The script builds two artefacts:

``docs/data/index2_stats_overview.json``
    Aggregated metrics for every team that appears in the CSV directory.

``docs/index2.html``
    A lightweight dashboard similar to ``docs/index.html`` which consumes the
    JSON payload above.  The HTML is intentionally generated from within this
    module so the resulting page can easily be reproduced.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional

from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parents[2]
CSV_DIRECTORY = BASE_DIR / "docs" / "data" / "csv"
HTML_OUTPUT_PATH = BASE_DIR / "docs" / "index2.html"
JSON_OUTPUT_PATH = BASE_DIR / "docs" / "data" / "index2_stats_overview.json"


BERLIN_TZ = ZoneInfo("Europe/Berlin")


# -- Name handling --------------------------------------------------------

TEAM_NAME_OVERRIDES: Mapping[str, str] = {
    "usc münster": "USC Münster",
    "vc wiesbaden": "VC Wiesbaden",
    "ssc palmberg schwerin": "SSC Palmberg Schwerin",
    "etv hamburger volksbank volleys": "ETV Hamburger Volksbank Volleys",
    "ladies in black aachen": "Ladies in Black Aachen",
    "vfb suhl lotto thüringen": "VfB Suhl LOTTO Thüringen",
    "skurios volleys borken": "Skurios Volleys Borken",
    "binder blaubären tsv flacht": "Binder Blaubären TSV Flacht",
    "schwarz-weiß erfurt": "Schwarz-Weiß Erfurt",
    "allianz mtv stuttgart": "Allianz MTV Stuttgart",
}

TEAM_SHORT_NAME_OVERRIDES: Mapping[str, str] = {
    "Allianz MTV Stuttgart": "Stuttgart",
    "Binder Blaubären TSV Flacht": "Flacht",
    "Dresdner SC": "Dresden",
    "ETV Hamburger Volksbank Volleys": "Hamburg",
    "Ladies in Black Aachen": "Aachen",
    "SSC Palmberg Schwerin": "Schwerin",
    "Schwarz-Weiß Erfurt": "Erfurt",
    "Skurios Volleys Borken": "Borken",
    "USC Münster": "Münster",
    "VC Wiesbaden": "Wiesbaden",
    "VfB Suhl LOTTO Thüringen": "Suhl",
}

PLAYER_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _smart_capitalize(value: str) -> str:
    tokens = []
    for token in value.split():
        sub_tokens = [sub.capitalize() for sub in token.split("-")]
        tokens.append("-".join(sub_tokens))
    return " ".join(tokens)


def canonicalize_team_name(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "Unbekanntes Team"
    lower = value.lower()
    if lower in TEAM_NAME_OVERRIDES:
        return TEAM_NAME_OVERRIDES[lower]
    return _smart_capitalize(lower)


def short_team_label(name: str) -> str:
    canonical = canonicalize_team_name(name)
    return TEAM_SHORT_NAME_OVERRIDES.get(canonical, canonical)


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "team"


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = value.strip()
    if not text or text in {"-", ".", "na", "n/a"}:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text.replace(",", ".")))
        except ValueError:
            return None


def canonicalize_player_name(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "Unbekannte Spielerin"
    cleaned = PLAYER_SUFFIX_RE.sub("", value)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _smart_capitalize(cleaned.lower())


# -- Parsing helpers ------------------------------------------------------

def parse_int(value: Optional[str]) -> int:
    if value is None:
        return 0
    text = value.strip()
    if not text or text in {"-", ".", "na", "n/a"}:
        return 0
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return 0


def parse_percentage(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text.replace(",", ".")) / 100
    except ValueError:
        return None


def compute_count_from_percentage(
    percentage: Optional[float], attempts: int
) -> int:
    if percentage is None or attempts <= 0:
        return 0
    return int(round(attempts * percentage))


def format_percentage(numerator: int, denominator: int) -> Optional[str]:
    if denominator <= 0:
        return None
    ratio = numerator / denominator
    return f"{round(ratio * 100):d}%"


def resolve_field(row: Mapping[str, str], *candidates: str) -> str:
    for candidate in candidates:
        if candidate in row:
            return row[candidate]
    return ""


# -- Metrics accumulation -------------------------------------------------

@dataclass
class MetricsAccumulator:
    serves_attempts: int = 0
    serves_errors: int = 0
    serves_points: int = 0
    receptions_attempts: int = 0
    receptions_errors: int = 0
    receptions_positive: int = 0
    receptions_perfect: int = 0
    attacks_attempts: int = 0
    attacks_errors: int = 0
    attacks_blocked: int = 0
    attacks_points: int = 0
    blocks_points: int = 0

    def add(self, metrics: Mapping[str, int]) -> None:
        self.serves_attempts += metrics.get("serves_attempts", 0)
        self.serves_errors += metrics.get("serves_errors", 0)
        self.serves_points += metrics.get("serves_points", 0)
        self.receptions_attempts += metrics.get("receptions_attempts", 0)
        self.receptions_errors += metrics.get("receptions_errors", 0)
        self.receptions_positive += metrics.get("receptions_positive", 0)
        self.receptions_perfect += metrics.get("receptions_perfect", 0)
        self.attacks_attempts += metrics.get("attacks_attempts", 0)
        self.attacks_errors += metrics.get("attacks_errors", 0)
        self.attacks_blocked += metrics.get("attacks_blocked", 0)
        self.attacks_points += metrics.get("attacks_points", 0)
        self.blocks_points += metrics.get("blocks_points", 0)

    def to_payload(self) -> Dict[str, object]:
        return {
            "serves_attempts": self.serves_attempts,
            "serves_errors": self.serves_errors,
            "serves_points": self.serves_points,
            "receptions_attempts": self.receptions_attempts,
            "receptions_errors": self.receptions_errors,
            "receptions_positive": self.receptions_positive,
            "receptions_perfect": self.receptions_perfect,
            "receptions_positive_pct": format_percentage(
                self.receptions_positive, self.receptions_attempts
            ),
            "receptions_perfect_pct": format_percentage(
                self.receptions_perfect, self.receptions_attempts
            ),
            "attacks_attempts": self.attacks_attempts,
            "attacks_errors": self.attacks_errors,
            "attacks_blocked": self.attacks_blocked,
            "attacks_points": self.attacks_points,
            "attacks_success_pct": format_percentage(
                self.attacks_points, self.attacks_attempts
            ),
            "blocks_points": self.blocks_points,
        }


@dataclass
class PlayerAccumulator:
    name: str
    jersey_number: Optional[int]
    matches: List[Mapping[str, object]] = field(default_factory=list)
    totals: MetricsAccumulator = field(default_factory=MetricsAccumulator)
    total_points: int = 0
    break_points: int = 0
    plus_minus: int = 0

    def add_match(
        self,
        match_entry: Mapping[str, object],
        metrics: Mapping[str, int],
        *,
        total_points: int,
        break_points: int,
        plus_minus: int,
        jersey_number: Optional[int],
    ) -> None:
        self.matches.append(match_entry)
        self.totals.add(metrics)
        self.total_points += total_points
        self.break_points += break_points
        self.plus_minus += plus_minus
        if jersey_number is not None and self.jersey_number is None:
            self.jersey_number = jersey_number

    def to_payload(self) -> Dict[str, object]:
        matches_sorted = sorted(
            self.matches,
            key=lambda entry: entry.get("kickoff", ""),
            reverse=True,
        )
        totals_payload = self.totals.to_payload()
        return {
            "name": self.name,
            "jersey_number": self.jersey_number,
            "match_count": len(self.matches),
            "matches": matches_sorted,
            "totals": totals_payload,
            "total_points": self.total_points,
            "break_points_total": self.break_points,
            "plus_minus_total": self.plus_minus,
        }


@dataclass
class TeamAccumulator:
    team: str
    slug: str
    matches: List[Mapping[str, object]] = field(default_factory=list)
    totals: MetricsAccumulator = field(default_factory=MetricsAccumulator)
    total_points: int = 0
    break_points: int = 0
    plus_minus: int = 0
    players: Dict[str, PlayerAccumulator] = field(default_factory=dict)

    def add_match(
        self,
        match_entry: Mapping[str, object],
        metrics: Mapping[str, int],
        *,
        total_points: int,
        break_points: int,
        plus_minus: int,
    ) -> None:
        self.matches.append(match_entry)
        self.totals.add(metrics)
        self.total_points += total_points
        self.break_points += break_points
        self.plus_minus += plus_minus

    def add_player_match(
        self,
        key: str,
        player_name: str,
        jersey_number: Optional[int],
        match_entry: Mapping[str, object],
        metrics: Mapping[str, int],
        *,
        total_points: int,
        break_points: int,
        plus_minus: int,
    ) -> None:
        accumulator = self.players.setdefault(
            key, PlayerAccumulator(name=player_name, jersey_number=jersey_number)
        )
        accumulator.add_match(
            match_entry,
            metrics,
            total_points=total_points,
            break_points=break_points,
            plus_minus=plus_minus,
            jersey_number=jersey_number,
        )

    def to_payload(self) -> Dict[str, object]:
        matches_sorted = sorted(
            self.matches,
            key=lambda entry: entry.get("kickoff", ""),
            reverse=True,
        )
        totals_payload = self.totals.to_payload()
        totals_payload.update(
            {
                "total_points": self.total_points,
                "break_points": self.break_points,
                "plus_minus": self.plus_minus,
            }
        )
        players_sorted = sorted(
            self.players.values(),
            key=lambda player: (
                player.jersey_number is None,
                player.jersey_number if player.jersey_number is not None else 0,
                player.name,
            ),
        )
        return {
            "team": self.team,
            "team_slug": self.slug,
            "match_count": len(self.matches),
            "totals": totals_payload,
            "matches": matches_sorted,
            "players": [player.to_payload() for player in players_sorted],
        }


# -- Data loading ---------------------------------------------------------

def iter_schedule_rows(csv_dir: Path) -> Iterator[Mapping[str, str]]:
    for path in sorted(csv_dir.glob("*competition*matches*.csv")):
        if path.stat().st_size == 0:
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not row:
                    continue
                yield row


def load_competition_schedule(csv_dir: Path) -> Dict[str, Dict[str, object]]:
    schedule: Dict[str, Dict[str, object]] = {}
    for row in iter_schedule_rows(csv_dir):
        match_id = (row.get("Match ID") or "").strip()
        if not match_id:
            continue
        home_team_raw = row.get("Home Team") or ""
        guest_team_raw = row.get("Guest Team") or ""
        entry = schedule.setdefault(match_id, {})
        entry.update(
            {
                "match_id": match_id,
                "match_date": (row.get("Match Date") or "").strip(),
                "stadium": (row.get("Stadium") or "").strip(),
                "home_team_raw": home_team_raw,
                "guest_team_raw": guest_team_raw,
                "home_team": canonicalize_team_name(home_team_raw),
                "guest_team": canonicalize_team_name(guest_team_raw),
                "home_points": parse_int(row.get("Home Points")),
                "guest_points": parse_int(row.get("Guest Points")),
            }
        )
    return schedule


def parse_metrics_row(row: Mapping[str, str]) -> Dict[str, int | str | None]:
    serves_attempts = parse_int(resolve_field(row, "Total Serve", "Total Serves"))
    receptions_attempts = parse_int(resolve_field(row, "Total Receptions"))
    attacks_attempts = parse_int(resolve_field(row, "Total Attacks"))

    positive_pct = parse_percentage(
        resolve_field(
            row,
            "Positive Pass Percentage",
            "Positive Pass Percentage (Pos%)",
        )
    )
    perfect_pct = parse_percentage(
        resolve_field(
            row,
            "Excellent/ Perfect Pass Percentage",
            "Excellent/ Perfect Pass Percentage (Exc.%)",
        )
    )

    receptions_positive = compute_count_from_percentage(positive_pct, receptions_attempts)
    receptions_perfect = compute_count_from_percentage(perfect_pct, receptions_attempts)

    attacks_points = parse_int(resolve_field(row, "Attack Points (Exc.)", "Attack Points"))

    metrics: Dict[str, int | str | None] = {
        "serves_attempts": serves_attempts,
        "serves_errors": parse_int(resolve_field(row, "Serve Errors")),
        "serves_points": parse_int(resolve_field(row, "Ace", "Aces")),
        "receptions_attempts": receptions_attempts,
        "receptions_errors": parse_int(resolve_field(row, "Reception Erros", "Reception Errors")),
        "receptions_positive": receptions_positive,
        "receptions_perfect": receptions_perfect,
        "receptions_positive_pct": format_percentage(receptions_positive, receptions_attempts),
        "receptions_perfect_pct": format_percentage(receptions_perfect, receptions_attempts),
        "attacks_attempts": attacks_attempts,
        "attacks_errors": parse_int(resolve_field(row, "Attack Erros", "Attack Errors")),
        "attacks_blocked": parse_int(resolve_field(row, "Blocked Attack", "Blocked Attacks")),
        "attacks_points": attacks_points,
        "attacks_success_pct": format_percentage(attacks_points, attacks_attempts),
        "blocks_points": parse_int(resolve_field(row, "Block Points")),
        "total_points": parse_int(resolve_field(row, "Total Points")),
        "break_points": parse_int(resolve_field(row, "Break Points")),
        "plus_minus": parse_int(resolve_field(row, "W-L")),
    }
    return metrics


def build_match_entry(
    *,
    metrics: Mapping[str, int | str | None],
    schedule_entry: Optional[Mapping[str, object]],
    team_canonical: str,
    opponent_raw: str,
    is_home: bool,
    match_id: str,
    match_date: str,
    stadium_raw: str,
    csv_path: str,
    player_name: Optional[str] = None,
    jersey_number: Optional[int] = None,
) -> Dict[str, object]:
    opponent_canonical = canonicalize_team_name(opponent_raw)
    opponent_short = short_team_label(opponent_canonical)
    kickoff_iso = None
    if match_date:
        try:
            kickoff_dt = datetime.strptime(match_date, "%Y-%m-%d").replace(
                hour=18,
                minute=0,
                tzinfo=BERLIN_TZ,
            )
            kickoff_iso = kickoff_dt.isoformat()
        except ValueError:
            kickoff_iso = None

    result_summary = None
    if schedule_entry:
        home_points = schedule_entry.get("home_points")
        guest_points = schedule_entry.get("guest_points")
        if isinstance(home_points, int) and isinstance(guest_points, int):
            if is_home:
                result_summary = f"{home_points}:{guest_points}"
            else:
                result_summary = f"{guest_points}:{home_points}"

    location = (stadium_raw or "").strip()
    if not location and schedule_entry:
        location = str(schedule_entry.get("stadium") or "").strip()

    match_entry: Dict[str, object] = {
        "match_number": match_id,
        "match_id": match_id,
        "kickoff": kickoff_iso,
        "is_home": is_home,
        "opponent": opponent_canonical,
        "opponent_short": opponent_short,
        "host": schedule_entry.get("home_team") if schedule_entry else team_canonical,
        "location": location or None,
        "result": {"summary": result_summary} if result_summary else None,
        "metrics": {
            "serves_attempts": metrics["serves_attempts"],
            "serves_errors": metrics["serves_errors"],
            "serves_points": metrics["serves_points"],
            "receptions_attempts": metrics["receptions_attempts"],
            "receptions_errors": metrics["receptions_errors"],
            "receptions_positive_pct": metrics["receptions_positive_pct"],
            "receptions_perfect_pct": metrics["receptions_perfect_pct"],
            "attacks_attempts": metrics["attacks_attempts"],
            "attacks_errors": metrics["attacks_errors"],
            "attacks_blocked": metrics["attacks_blocked"],
            "attacks_points": metrics["attacks_points"],
            "attacks_success_pct": metrics["attacks_success_pct"],
            "blocks_points": metrics["blocks_points"],
            "receptions_positive": metrics["receptions_positive"],
            "receptions_perfect": metrics["receptions_perfect"],
        },
        "total_points": metrics["total_points"],
        "break_points": metrics["break_points"],
        "plus_minus": metrics["plus_minus"],
        "csv_path": csv_path,
    }

    if player_name:
        match_entry["player"] = player_name
    if jersey_number is not None:
        match_entry["jersey_number"] = jersey_number

    return match_entry


def collect_team_accumulators(csv_dir: Path, schedule: Mapping[str, Mapping[str, object]]) -> Dict[str, TeamAccumulator]:
    teams: Dict[str, TeamAccumulator] = {}
    for path in sorted(csv_dir.glob("vbl-*.csv")):
        if "competition" in path.name:
            continue
        if path.stat().st_size == 0:
            continue

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            team_field = None
            if reader.fieldnames:
                if "Home Team" in reader.fieldnames:
                    team_field = "Home Team"
                elif "Guest Team" in reader.fieldnames:
                    team_field = "Guest Team"

            rows: List[Mapping[str, str]] = [row for row in reader if row]

        totals_row: Optional[Mapping[str, str]] = None
        player_rows: List[Mapping[str, str]] = []
        for row in rows:
            name_raw = (row.get("Name") or "").strip()
            if not name_raw:
                continue
            if name_raw.lower() == "totals":
                totals_row = row
            else:
                player_rows.append(row)

        if not totals_row:
            continue

        match_id = (totals_row.get("Match ID") or "").strip()
        if not match_id:
            continue

        match_date = (totals_row.get("Match Date") or "").strip()
        stadium_raw = (totals_row.get("Stadium") or "").strip()

        if team_field is None:
            continue

        team_name_raw = totals_row.get(team_field) or ""
        team_canonical = canonicalize_team_name(team_name_raw)
        team_key = normalize_key(team_canonical)
        opponent_raw = ""
        schedule_entry = schedule.get(match_id)
        is_home = team_field == "Home Team"
        if schedule_entry:
            opponent_raw = (
                schedule_entry["guest_team_raw"]
                if is_home
                else schedule_entry["home_team_raw"]
            )

        metrics = parse_metrics_row(totals_row)
        match_entry = build_match_entry(
            metrics=metrics,
            schedule_entry=schedule_entry,
            team_canonical=team_canonical,
            opponent_raw=opponent_raw,
            is_home=is_home,
            match_id=match_id,
            match_date=match_date,
            stadium_raw=stadium_raw,
            csv_path=f"data/csv/{path.name}",
        )

        accumulator = teams.setdefault(
            team_key, TeamAccumulator(team=team_canonical, slug=slugify(team_canonical))
        )
        accumulator.add_match(
            match_entry,
            metrics,
            total_points=metrics["total_points"],
            break_points=metrics["break_points"],
            plus_minus=metrics["plus_minus"],
        )

        for player_row in player_rows:
            player_name_raw = (player_row.get("Name") or "").strip()
            if not player_name_raw:
                continue
            player_name = canonicalize_player_name(player_name_raw)
            jersey_number = parse_optional_int(player_row.get("Number"))
            player_metrics = parse_metrics_row(player_row)
            player_entry = build_match_entry(
                metrics=player_metrics,
                schedule_entry=schedule_entry,
                team_canonical=team_canonical,
                opponent_raw=opponent_raw,
                is_home=is_home,
                match_id=match_id,
                match_date=match_date,
                stadium_raw=stadium_raw,
                csv_path=f"data/csv/{path.name}",
                player_name=player_name,
                jersey_number=jersey_number,
            )
            player_key_source = f"{player_name}-{jersey_number or ''}"
            player_key = normalize_key(player_key_source) or slugify(player_key_source)
            accumulator.add_player_match(
                player_key,
                player_name,
                jersey_number,
                player_entry,
                player_metrics,
                total_points=player_metrics["total_points"],
                break_points=player_metrics["break_points"],
                plus_minus=player_metrics["plus_minus"],
            )

    return teams


def build_overview_payload(csv_dir: Path) -> Dict[str, object]:
    schedule = load_competition_schedule(csv_dir)
    teams = collect_team_accumulators(csv_dir, schedule)
    generated_at = datetime.now(tz=BERLIN_TZ)
    return {
        "generated": generated_at.isoformat(),
        "team_count": len(teams),
        "teams": [team.to_payload() for team in sorted(teams.values(), key=lambda item: item.team)],
    }


# -- HTML generation ------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Scouting Übersicht (CSV)</title>
  <link rel=\"icon\" type=\"image/png\" sizes=\"32x32\" href=\"favicon.png\">
  <link rel=\"manifest\" href=\"manifest.webmanifest\">
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f5f7f9;
      --fg: #0f172a;
      --accent: #0f766e;
      --card-bg: #ffffff;
      --card-border: rgba(15, 118, 110, 0.18);
      --muted: #475569;
      --shadow: 0 16px 34px rgba(15, 118, 110, 0.12);
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #0f1f24;
        --fg: #e2f1f4;
        --card-bg: #132a30;
        --card-border: rgba(94, 234, 212, 0.28);
        --muted: #cbd5f5;
        --shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
      }
    }

    body {
      margin: 0;
      font-family: \"Inter\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Arial, sans-serif;
      background: var(--bg);
      color: var(--fg);
      line-height: 1.6;
    }

    main {
      width: 100%;
      max-width: none;
      margin: 0;
      padding: clamp(1.2rem, 3vw, 2.8rem) clamp(1rem, 4vw, 3.2rem);
      display: grid;
      gap: clamp(1.8rem, 4vw, 3rem);
      box-sizing: border-box;
    }

    header.page-header {
      display: grid;
      gap: 0.75rem;
    }

    h1 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 2.8rem);
      letter-spacing: -0.01em;
    }

    p.page-intro {
      margin: 0;
      max-width: 42rem;
      font-size: clamp(1rem, 2.4vw, 1.15rem);
      color: var(--muted);
    }

    .team-selector {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      align-items: center;
    }

    .team-selector label {
      font-weight: 600;
    }

    .team-selector select {
      padding: 0.4rem 0.6rem;
      border-radius: 0.5rem;
      border: 1px solid rgba(15, 118, 110, 0.35);
      background: var(--card-bg);
      color: inherit;
      font-size: 1rem;
    }

    .update-note {
      margin: 0;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.8rem;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.12);
      color: var(--accent);
      font-weight: 600;
      font-size: 0.85rem;
      border: 1px solid rgba(15, 118, 110, 0.24);
    }

    section {
      display: grid;
      gap: clamp(1rem, 3vw, 1.8rem);
    }

    h2 {
      margin: 0;
      font-size: clamp(1.35rem, 3vw, 1.8rem);
    }

    .metric-card {
      background: var(--card-bg);
      border-radius: 0.9rem;
      border: 1px solid var(--card-border);
      padding: clamp(0.9rem, 3vw, 1.2rem);
      box-shadow: var(--shadow);
      display: grid;
      gap: 0.6rem;
    }

    .metric-card h3 {
      margin: 0;
      font-size: clamp(1rem, 2.4vw, 1.2rem);
      color: var(--accent);
    }

    .metric-card dl {
      margin: 0;
      display: grid;
      gap: 0.35rem;
    }

    .metric-card dt {
      font-weight: 600;
    }

    .metric-card dd {
      margin: 0;
      color: var(--muted);
    }

    .player-table-wrapper {
      overflow-x: auto;
      border-radius: 1rem;
      border: 1px solid var(--card-border);
      background: var(--card-bg);
      box-shadow: var(--shadow);
    }

    table.player-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
      min-width: 48rem;
    }

    table.player-table thead th {
      text-align: left;
      padding: 0.75rem 0.9rem;
      position: sticky;
      top: 0;
      background: var(--card-bg);
      color: var(--accent);
      font-weight: 600;
      border-bottom: 1px solid var(--card-border);
      z-index: 1;
    }

    table.player-table th.numeric,
    table.player-table td.numeric {
      text-align: right;
    }

    table.player-table tbody td {
      padding: 0.6rem 0.9rem;
      border-bottom: 1px solid rgba(15, 118, 110, 0.12);
      white-space: nowrap;
    }

    table.player-table tbody tr:last-child td {
      border-bottom: none;
    }

    table.player-table tbody tr:nth-child(odd) {
      background: rgba(15, 118, 110, 0.04);
    }

    .match-table-wrapper {
      background: var(--card-bg);
      border-radius: 0.9rem;
      border: 1px solid var(--card-border);
      padding: clamp(0.6rem, 2vw, 1rem);
      box-shadow: none;
      overflow-x: auto;
    }

    table.match-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 62rem;
      font-size: 0.9rem;
    }

    table.match-table thead th {
      text-align: left;
      padding: 0.6rem 0.75rem;
      background: rgba(15, 118, 110, 0.08);
      color: var(--muted);
      font-weight: 600;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border-bottom: 2px solid rgba(15, 118, 110, 0.2);
      white-space: nowrap;
    }

    table.match-table tbody td,
    table.match-table tbody th {
      padding: 0.55rem 0.75rem;
      border-bottom: 1px solid rgba(15, 118, 110, 0.12);
      vertical-align: middle;
    }

    table.match-table tbody tr:nth-child(even) {
      background: rgba(15, 118, 110, 0.05);
    }

    table.match-table tbody tr:last-child td,
    table.match-table tbody tr:last-child th {
      border-bottom: none;
    }

    table.match-table .numeric {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    table.match-table .match-summary {
      background: rgba(15, 118, 110, 0.12);
    }

    table.match-table .match-summary th {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--accent);
    }

    table.match-table .match-summary td {
      font-weight: 600;
      color: var(--accent);
    }

    .empty-state {
      margin: 0;
      color: var(--muted);
    }

    footer {
      font-size: 0.85rem;
      color: var(--muted);
      text-align: center;
    }

    @media (max-width: 40rem) {
      main {
        padding: 1.2rem;
      }
    }

    @media (prefers-color-scheme: dark) {
      .match-table-wrapper,
      .player-table-wrapper {
        background: rgba(19, 42, 48, 0.9);
        border-color: rgba(94, 234, 212, 0.22);
      }

      table.match-table tbody tr:nth-child(odd),
      table.player-table tbody tr:nth-child(odd) {
        background: rgba(94, 234, 212, 0.08);
      }
    }
  </style>
</head>
<body>
  <main>
    <header class=\"page-header\">
      <h1 data-team-heading>Scouting Übersicht (CSV)</h1>
      <p class=\"page-intro\">
        Übersicht über die Teamstatistiken aus den vorhandenen CSV-Dateien. Wähle eine Mannschaft,
        um die aggregierten Werte einzublenden.
      </p>
      <div class=\"team-selector\" data-selector hidden>
        <label for=\"team-select\">Mannschaft</label>
        <select id=\"team-select\" data-team-select></select>
      </div>
      <p class=\"update-note\" data-generated>Stand: wird geladen …</p>
    </header>

    <section aria-labelledby=\"matches-heading\" hidden data-section=\"matches\">
      <h2 id=\"matches-heading\">Spiele</h2>
      <div data-matches></div>
    </section>

    <section aria-labelledby=\"players-heading\" hidden data-section=\"players\">
      <h2 id=\"players-heading\">Spielerinnen</h2>
      <div class=\"player-table-wrapper\" data-player-table>
        <p class=\"empty-state\">Noch keine Spielerinnendaten verfügbar.</p>
      </div>
    </section>

    <footer>
      Datenquelle: CSV-Exporte aus ``docs/data/csv``
    </footer>
  </main>

  <script>
    const DATA_URL = "__JSON_PATH__";

    const MATCH_COLUMNS = [
      {
        label: 'Datum',
        resolver: entry => formatMatchDate(entry?.kickoff) || '–',
        totalsResolver: () => 'Summe'
      },
      {
        label: 'Gegner',
        resolver: entry => entry?.opponent_short || entry?.opponent || '–'
      },
      {
        label: 'Sätze',
        resolver: entry => entry?.result?.summary ?? '–'
      },
      {
        label: 'Auf-Ges',
        resolver: entry => resolveMatchMetric(entry, 'serves_attempts'),
        totalsKey: 'serves_attempts',
        numeric: true
      },
      {
        label: 'Auf-Fhl',
        resolver: entry => resolveMatchMetric(entry, 'serves_errors'),
        totalsKey: 'serves_errors',
        numeric: true
      },
      {
        label: 'Auf-Pkt',
        resolver: entry => resolveMatchMetric(entry, 'serves_points'),
        totalsKey: 'serves_points',
        numeric: true
      },
      {
        label: 'An-Ges',
        resolver: entry => resolveMatchMetric(entry, 'receptions_attempts'),
        totalsKey: 'receptions_attempts',
        numeric: true
      },
      {
        label: 'An-Fhl',
        resolver: entry => resolveMatchMetric(entry, 'receptions_errors'),
        totalsKey: 'receptions_errors',
        numeric: true
      },
      {
        label: 'An-Pos%',
        resolver: entry => resolveMatchMetric(entry, 'receptions_positive_pct'),
        totalsKey: 'receptions_positive_pct',
        numeric: true
      },
      {
        label: 'An-Prf%',
        resolver: entry => resolveMatchMetric(entry, 'receptions_perfect_pct'),
        totalsKey: 'receptions_perfect_pct',
        numeric: true
      },
      {
        label: 'Ag-Ges',
        resolver: entry => resolveMatchMetric(entry, 'attacks_attempts'),
        totalsKey: 'attacks_attempts',
        numeric: true
      },
      {
        label: 'Ag-Fhl',
        resolver: entry => resolveMatchMetric(entry, 'attacks_errors'),
        totalsKey: 'attacks_errors',
        numeric: true
      },
      {
        label: 'Ag-Blo',
        resolver: entry => resolveMatchMetric(entry, 'attacks_blocked'),
        totalsKey: 'attacks_blocked',
        numeric: true
      },
      {
        label: 'Ag-Pkt',
        resolver: entry => resolveMatchMetric(entry, 'attacks_points'),
        totalsKey: 'attacks_points',
        numeric: true
      },
      {
        label: 'Ag-%',
        resolver: entry => resolveMatchMetric(entry, 'attacks_success_pct'),
        totalsKey: 'attacks_success_pct',
        numeric: true
      },
      {
        label: 'Block',
        resolver: entry => resolveMatchMetric(entry, 'blocks_points'),
        totalsKey: 'blocks_points',
        numeric: true
      },
      {
        label: 'Pkt.',
        resolver: entry => resolveMatchMetric(entry, 'total_points'),
        totalsKey: 'total_points',
        numeric: true
      },
      {
        label: 'Breakpkt.',
        resolver: entry => entry?.break_points ?? null,
        totalsKey: 'break_points',
        numeric: true
      },
      {
        label: '+/-',
        resolver: entry => entry?.plus_minus ?? null,
        totalsKey: 'plus_minus',
        numeric: true
      }
    ];

    const PLAYER_COLUMNS = [
      { label: "#", getter: player => player?.jersey_number ?? null, numeric: true },
      { label: "Name", getter: player => player?.name || "Unbekannt" },
      { label: "Sp.", getter: player => player?.match_count ?? 0, numeric: true },
      {
        label: "Auf-Ges",
        getter: player => player?.totals?.serves_attempts ?? null,
        numeric: true
      },
      {
        label: "Auf-Fhl",
        getter: player => player?.totals?.serves_errors ?? null,
        numeric: true
      },
      {
        label: "Auf-Pkt",
        getter: player => player?.totals?.serves_points ?? null,
        numeric: true
      },
      {
        label: "An-Ges",
        getter: player => player?.totals?.receptions_attempts ?? null,
        numeric: true
      },
      {
        label: "An-Fhl",
        getter: player => player?.totals?.receptions_errors ?? null,
        numeric: true
      },
      {
        label: "An-Pos%",
        getter: player => player?.totals?.receptions_positive_pct ?? null,
        numeric: true
      },
      {
        label: "An-Prf%",
        getter: player => player?.totals?.receptions_perfect_pct ?? null,
        numeric: true
      },
      {
        label: "Ag-Ges",
        getter: player => player?.totals?.attacks_attempts ?? null,
        numeric: true
      },
      {
        label: "Ag-Fhl",
        getter: player => player?.totals?.attacks_errors ?? null,
        numeric: true
      },
      {
        label: "Ag-Blo",
        getter: player => player?.totals?.attacks_blocked ?? null,
        numeric: true
      },
      {
        label: "Ag-Pkt",
        getter: player => player?.totals?.attacks_points ?? null,
        numeric: true
      },
      {
        label: "Ag-%",
        getter: player => player?.totals?.attacks_success_pct ?? null,
        numeric: true
      },
      {
        label: "Block",
        getter: player => player?.totals?.blocks_points ?? null,
        numeric: true
      },
      {
        label: "Pkt.",
        getter: player => player?.total_points ?? null,
        numeric: true
      },
      {
        label: "Breakpkt.",
        getter: player => player?.break_points_total ?? null,
        numeric: true
      },
      {
        label: "+/-",
        getter: player => player?.plus_minus_total ?? null,
        numeric: true
      }
    ];

    let overviewPayload = null;

    async function loadOverview() {
      try {
        const response = await fetch(DATA_URL, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Fehler beim Laden der Daten: ${response.status}`);
        }
        overviewPayload = await response.json();
        setupTeams(overviewPayload);
      } catch (error) {
        console.error(error);
        showError();
      }
    }

    function setupTeams(payload) {
      updateGenerated(payload.generated);
      const teams = Array.isArray(payload.teams) ? payload.teams : [];
      const selectorWrapper = document.querySelector('[data-selector]');
      const select = document.querySelector('[data-team-select]');
      if (!selectorWrapper || !select) return;

      select.innerHTML = "";
      teams.forEach((team, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = team.team || `Team ${index + 1}`;
        select.append(option);
      });

      if (teams.length > 1) {
        selectorWrapper.hidden = false;
      }

      select.addEventListener('change', () => {
        const idx = Number.parseInt(select.value, 10);
        renderTeam(teams[idx] || null);
      });

      renderTeam(teams[0] || null);
    }

    function renderTeam(team) {
      const heading = document.querySelector('[data-team-heading]');
      if (heading) {
        heading.textContent = team?.team ? `Scouting ${team.team} (CSV)` : 'Scouting Übersicht (CSV)';
      }
      if (!team) {
        renderPlayers(null);
        renderMatches([], {});
        return;
      }
      const players = Array.isArray(team.players) ? team.players : [];
      renderPlayers(players);
      renderMatches(
        Array.isArray(team.matches) ? team.matches : [],
        {
          teamName: team.team || null,
          totals: team.totals || null
        }
      );
    }

    function updateGenerated(timestamp) {
      const target = document.querySelector('[data-generated]');
      if (!target) return;
      if (!timestamp) {
        target.textContent = 'Stand: keine Daten verfügbar';
        return;
      }
      const date = new Date(timestamp);
      const formatted = date.toLocaleString('de-DE', {
        dateStyle: 'full',
        timeStyle: 'short'
      });
      target.textContent = `Stand: ${formatted}`;
    }

    function renderPlayers(players) {
      const section = document.querySelector('[data-section="players"]');
      const container = document.querySelector('[data-player-table]');
      if (!section || !container) return;
      container.innerHTML = '';
      const entries = Array.isArray(players) ? players : [];
      if (!entries.length) {
        container.innerHTML = '<p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>';
        section.hidden = false;
        return;
      }
      container.append(buildPlayerTable(entries));
      section.hidden = false;
    }

    function buildPlayerTable(players) {
      const table = document.createElement('table');
      table.className = 'player-table';

      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      PLAYER_COLUMNS.forEach(column => {
        const th = document.createElement('th');
        th.scope = 'col';
        if (column.numeric) th.classList.add('numeric');
        th.textContent = column.label;
        headerRow.append(th);
      });
      thead.append(headerRow);
      table.append(thead);

      const tbody = document.createElement('tbody');
      players.forEach(player => {
        const row = document.createElement('tr');
        PLAYER_COLUMNS.forEach(column => {
          const td = document.createElement('td');
          if (column.numeric) td.classList.add('numeric');
          const value = typeof column.getter === 'function' ? column.getter(player) : null;
          td.textContent = formatMetricValue(value);
          row.append(td);
        });
        tbody.append(row);
      });
      table.append(tbody);
      return table;
    }

    function renderMatches(matches, context = {}) {
      const section = document.querySelector('[data-section="matches"]');
      const container = document.querySelector('[data-matches]');
      if (!section || !container) return;
      container.innerHTML = '';
      const entries = Array.isArray(matches) ? matches : [];
      if (!entries.length) {
        container.innerHTML = '<p class="empty-state">Es liegen noch keine Spiele mit Statistikdaten vor.</p>';
        section.hidden = false;
        return;
      }
      const tableWrapper = buildMatchTable(entries, context || {});
      container.append(tableWrapper);
      section.hidden = false;
    }

    function buildMatchTable(matches, context) {
      const wrapper = document.createElement('div');
      wrapper.className = 'match-table-wrapper';
      const table = document.createElement('table');
      table.className = 'match-table';
      table.append(buildMatchTableHead());
      table.append(buildMatchTableBody(matches, context));
      wrapper.append(table);
      return wrapper;
    }

    function buildMatchTableHead() {
      const thead = document.createElement('thead');
      const row = document.createElement('tr');
      MATCH_COLUMNS.forEach(column => {
        const th = document.createElement('th');
        th.scope = 'col';
        if (column.numeric) th.classList.add('numeric');
        th.textContent = column.label;
        row.append(th);
      });
      thead.append(row);
      return thead;
    }

    function buildMatchTableBody(matches, context) {
      const tbody = document.createElement('tbody');
      matches.forEach(entry => {
        const row = document.createElement('tr');
        MATCH_COLUMNS.forEach(column => {
          const td = document.createElement('td');
          if (column.numeric) td.classList.add('numeric');
          const value = typeof column.resolver === 'function' ? column.resolver(entry, context) : null;
          td.textContent = formatMetricValue(value);
          row.append(td);
        });
        tbody.append(row);
      });
      if (context && context.totals) {
        tbody.append(buildMatchTotalsRow(context.totals));
      }
      return tbody;
    }

    function resolveMatchMetric(entry, key) {
      if (!entry || typeof entry !== 'object' || !key) {
        return null;
      }
      if (entry.metrics && Object.prototype.hasOwnProperty.call(entry.metrics, key)) {
        return entry.metrics[key];
      }
      if (Object.prototype.hasOwnProperty.call(entry, key)) {
        return entry[key];
      }
      return null;
    }

    function buildMatchTotalsRow(totals) {
      const row = document.createElement('tr');
      row.className = 'match-summary';
      MATCH_COLUMNS.forEach((column, index) => {
        const cell = document.createElement(index === 0 ? 'th' : 'td');
        if (index === 0) {
          cell.scope = 'row';
        } else if (column.numeric) {
          cell.classList.add('numeric');
        }
        let value;
        if (typeof column.totalsResolver === 'function') {
          value = column.totalsResolver(totals, index);
        } else if (column.totalsKey && totals) {
          value = totals[column.totalsKey];
        } else if (index === 0) {
          value = 'Summe';
        } else {
          value = '';
        }
        if (value === null || value === undefined || value === '') {
          cell.textContent = '';
        } else {
          cell.textContent = formatMetricValue(value);
        }
        row.append(cell);
      });
      return row;
    }

    function formatMatchDate(input) {
      if (!input) {
        return '';
      }
      const date = new Date(input);
      if (Number.isNaN(date.getTime())) {
        return '';
      }
      return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      });
    }

    function formatMetricValue(value) {
      if (value === null || value === undefined) {
        return '–';
      }
      if (typeof value === 'number') {
        return Number.isFinite(value) ? value.toString() : '–';
      }
      const text = String(value).trim();
      return text ? text : '–';
    }

    function showError() {
      const heading = document.querySelector('[data-team-heading]');
      if (heading) {
        heading.textContent = 'Scouting Übersicht (CSV)';
      }
      renderPlayers([]);
      renderMatches([], {});
    }

    document.addEventListener('DOMContentLoaded', loadOverview);
  </script>
</body>
</html>
"""


# -- CLI ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the CSV-based scouting overview"
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=CSV_DIRECTORY,
        help="Directory containing the exported CSV files.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=JSON_OUTPUT_PATH,
        help="Target JSON path (default: docs/data/index2_stats_overview.json).",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=HTML_OUTPUT_PATH,
        help="Target HTML path (default: docs/index2.html).",
    )
    return parser


def render_html(*, json_path: Path) -> str:
    try:
        relative_path = json_path.relative_to(HTML_OUTPUT_PATH.parent)
    except ValueError:
        relative_path = json_path
    json_href = str(relative_path).replace('\\', '/')
    return HTML_TEMPLATE.replace("__JSON_PATH__", json_href)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    csv_dir = args.csv_dir
    json_output: Path = args.json_output
    html_output: Path = args.html_output

    payload = build_overview_payload(csv_dir)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    html_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.write_text(
        render_html(json_path=json_output),
        encoding="utf-8",
    )

    print(
        f"Generated CSV overview for {payload['team_count']} teams -> {json_output.relative_to(BASE_DIR)}"
    )
    print(f"HTML dashboard written to {html_output.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
