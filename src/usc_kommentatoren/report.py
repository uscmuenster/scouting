from __future__ import annotations

import base64
import csv
import json
import time
from dataclasses import dataclass, replace
import re
from datetime import date, datetime, timedelta
from pathlib import Path
import mimetypes
from html import escape
from io import BytesIO, StringIO
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urljoin, urlparse
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_SCHEDULE_URL = "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171"
SCHEDULE_PAGE_URL = (
    "https://www.volleyball-bundesliga.de/cms/home/"
    "1_bundesliga_frauen/statistik/hauptrunde/spielplan.xhtml?playingScheduleMode=full"
)
TABLE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/statistik/hauptrunde/tabelle_hauptrunde.xhtml"
VBL_NEWS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/news.xhtml"
VBL_BASE_URL = "https://www.volleyball-bundesliga.de/"
VBL_PRESS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/pressespiegel.xhtml"
WECHSELBOERSE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/teams_spielerinnen/wechselboerse.xhtml"
TEAM_PAGE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/teams_spielerinnen/mannschaften.xhtml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
USC_CANONICAL_NAME = "USC Münster"
USC_HOMEPAGE = "https://www.usc-muenster.de/"

MANUAL_SCHEDULE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "data" / "manual_schedule.csv"
)
_MANUAL_SCHEDULE_METADATA: Dict[str, Dict[str, Optional[str]]] = {
    "2005": {
        "match_id": "777479976",
        "info_url": (
            "https://www.volleyball-bundesliga.de/popup/matchSeries/matchDetails.xhtml"
            "?matchId=777479976&hideHistoryBackButton=true"
        ),
        "stats_url": "https://www.volleyball-bundesliga.de/uploads/70a7c2ba-97bc-4478-8e8e-e55ec764d2e6",
        "scoresheet_url": None,
    },
    "2011": {
        "match_id": "777479989",
        "info_url": (
            "https://www.volleyball-bundesliga.de/popup/matchSeries/matchDetails.xhtml"
            "?matchId=777479989&hideHistoryBackButton=true"
        ),
        "stats_url": "https://www.volleyball-bundesliga.de/uploads/19bb6c96-f1cc-4867-9058-0864849ec964",
        "scoresheet_url": "https://distributor.sams-score.de/scoresheet/pdf/ab4891bf-921b-4fe1-8aaa-97f2b9acb6d9/2011",
    },
}


def _merge_manual_schedule_metadata(
    metadata: Dict[str, Dict[str, Optional[str]]]
) -> Dict[str, Dict[str, Optional[str]]]:
    for match_number, manual_entry in _MANUAL_SCHEDULE_METADATA.items():
        entry = metadata.setdefault(
            match_number,
            {
                "match_id": None,
                "info_url": None,
                "stats_url": None,
                "scoresheet_url": None,
            },
        )
        for key, value in manual_entry.items():
            if value and not entry.get(key):
                entry[key] = value
    return metadata

# Farbkonfiguration für Hervorhebungen von USC und Gegner.
# Werte können bei Bedarf angepasst werden, um die farbliche Darstellung global zu ändern.
HIGHLIGHT_COLORS: Dict[str, Dict[str, str]] = {
    "usc": {
        "row_bg": "#dcfce7",
        "row_text": "#047857",
        "legend_dot": "#16a34a",
        "accordion_bg": "#dcfce7",
        "accordion_shadow": "rgba(22, 163, 74, 0.08)",
        "card_border": "rgba(45, 212, 191, 0.55)",
        "card_shadow": "rgba(45, 212, 191, 0.16)",
        "mvp_bg": "rgba(16, 185, 129, 0.12)",
        "mvp_border": "rgba(5, 150, 105, 0.24)",
        "mvp_score": "#047857",
        "dark_row_bg": "rgba(22, 163, 74, 0.25)",
        "dark_row_text": "#bbf7d0",
        "dark_accordion_bg": "#1a4f3a",
        "dark_accordion_shadow": "rgba(74, 222, 128, 0.26)",
    },
    "opponent": {
        "row_bg": "#e0f2fe",
        "row_text": "#1d4ed8",
        "legend_dot": "#2563eb",
        "accordion_bg": "#e0f2fe",
        "accordion_shadow": "rgba(30, 64, 175, 0.08)",
        "card_border": "rgba(59, 130, 246, 0.35)",
        "card_shadow": "rgba(59, 130, 246, 0.18)",
        "mvp_bg": "rgba(59, 130, 246, 0.12)",
        "mvp_border": "rgba(37, 99, 235, 0.22)",
        "mvp_score": "#1d4ed8",
        "dark_row_bg": "rgba(59, 130, 246, 0.18)",
        "dark_row_text": "#bfdbfe",
        "dark_accordion_bg": "#1c3f5f",
        "dark_accordion_shadow": "rgba(56, 189, 248, 0.28)",
    },
}

THEME_COLORS: Dict[str, str] = {
    "mvp_overview_summary_bg": "#0f766e",
    "dark_mvp_overview_summary_bg": "rgba(253, 186, 116, 0.35)",
}

INTERNATIONAL_MATCHES_LINK: tuple[str, str] = (
    "internationale_spiele.html",
    "Internationale Spiele 2025/26",
)

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; usc-kommentatoren/1.0; +https://github.com/)"
}
HTML_ACCEPT_HEADER = {"Accept": "text/html,application/xhtml+xml"}
RSS_ACCEPT_HEADER = {"Accept": "application/rss+xml,text/xml"}
NEWS_LOOKBACK_DAYS = 14
INSTAGRAM_SEARCH_URL = "https://duckduckgo.com/html/"

GERMAN_STOPWORDS = {
    "aber",
    "als",
    "am",
    "auch",
    "auf",
    "aus",
    "bei",
    "bin",
    "bis",
    "da",
    "damit",
    "dann",
    "der",
    "die",
    "das",
    "dass",
    "den",
    "des",
    "dem",
    "ein",
    "eine",
    "einen",
    "einem",
    "er",
    "es",
    "für",
    "hat",
    "haben",
    "ich",
    "im",
    "in",
    "ist",
    "mit",
    "nach",
    "nicht",
    "noch",
    "oder",
    "sein",
    "sind",
    "so",
    "und",
    "vom",
    "von",
    "vor",
    "war",
    "wie",
    "wir",
    "zu",
}

SEARCH_TRANSLATION = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "ae",
        "Ö": "oe",
        "Ü": "ue",
        "ß": "ss",
    }
)


@dataclass(frozen=True)
class MatchResult:
    score: str
    total_points: Optional[str]
    sets: tuple[str, ...]

    @property
    def summary(self) -> str:
        segments: list[str] = [self.score]
        if self.total_points:
            segments.append(f"/ {self.total_points}")
        if self.sets:
            segments.append(f"({' '.join(self.sets)})")
        return " ".join(segments)


@dataclass(frozen=True)
class MVPSelection:
    medal: Optional[str]
    name: str
    team: Optional[str] = None


@dataclass(frozen=True)
class Match:
    kickoff: datetime
    home_team: str
    away_team: str
    host: str
    location: str
    result: Optional[MatchResult]
    match_number: Optional[str] = None
    match_id: Optional[str] = None
    info_url: Optional[str] = None
    stats_url: Optional[str] = None
    scoresheet_url: Optional[str] = None
    referees: Tuple[str, ...] = ()
    attendance: Optional[str] = None
    mvps: Tuple[MVPSelection, ...] = ()

    @property
    def is_finished(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class RosterMember:
    number_label: Optional[str]
    number_value: Optional[int]
    name: str
    role: str
    is_official: bool
    height: Optional[str]
    birthdate_label: Optional[str]
    nationality: Optional[str]


    @property
    def formatted_birthdate(self) -> Optional[str]:
        parsed = self.birthdate_value
        if parsed:
            return parsed.strftime("%d.%m.%Y")
        if not self.birthdate_label:
            return None
        value = self.birthdate_label.strip()
        return value or None

    @property
    def birthdate_value(self) -> Optional[date]:
        if not self.birthdate_label:
            return None
        value = self.birthdate_label.strip()
        if not value:
            return None
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed.date()
        return None


@dataclass(frozen=True)
class MatchStatsTotals:
    team_name: str
    header_lines: Tuple[str, ...]
    totals_line: str
    metrics: Optional["MatchStatsMetrics"] = None
    players: Tuple["MatchPlayerStats", ...] = ()


@dataclass(frozen=True)
class MatchStatsMetrics:
    serves_attempts: int
    serves_errors: int
    serves_points: int
    receptions_attempts: int
    receptions_errors: int
    receptions_positive_pct: str
    receptions_perfect_pct: str
    attacks_attempts: int
    attacks_errors: int
    attacks_blocked: int
    attacks_points: int
    attacks_success_pct: str
    blocks_points: int
    receptions_positive: int = 0
    receptions_perfect: int = 0


@dataclass(frozen=True)
class MatchPlayerStats:
    team_name: str
    player_name: str
    jersey_number: Optional[int]
    metrics: MatchStatsMetrics
    total_points: Optional[int] = None
    break_points: Optional[int] = None
    plus_minus: Optional[int] = None


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: Optional[datetime]
    search_text: str = ""

    @property
    def formatted_date(self) -> Optional[str]:
        if not self.published:
            return None
        return self.published.astimezone(BERLIN_TZ).strftime("%d.%m.%Y %H:%M")


@dataclass(frozen=True)
class TransferItem:
    date: Optional[datetime]
    date_label: str
    category: Optional[str]
    type_code: str
    name: str
    url: Optional[str]
    nationality: str
    info: str
    related_club: str

    @property
    def formatted_date(self) -> str:
        if self.date:
            return self.date.strftime("%d.%m.%Y")
        return self.date_label

@dataclass(frozen=True)
class KeywordSet:
    keywords: Tuple[str, ...]
    strong: Tuple[str, ...]


def simplify_text(value: str) -> str:
    simplified = value.translate(SEARCH_TRANSLATION).lower()
    simplified = re.sub(r"\s+", " ", simplified)
    return simplified.strip()


def build_keywords(*names: str) -> KeywordSet:
    keywords: set[str] = set()
    strong: set[str] = set()
    for name in names:
        simplified = simplify_text(name)
        if not simplified:
            continue
        keywords.add(simplified)
        strong.add(simplified)
        condensed = simplified.replace(" ", "")
        if condensed:
            keywords.add(condensed)
            if condensed != simplified:
                strong.add(condensed)
        tokens = [token for token in re.split(r"[^a-z0-9]+", simplified) if token]
        keywords.update(tokens)
    return KeywordSet(tuple(sorted(keywords)), tuple(sorted(strong)))


def matches_keywords(text: str, keyword_set: KeywordSet) -> bool:
    keywords = keyword_set.keywords
    strong_keywords = keyword_set.strong
    haystack = simplify_text(text)
    if not haystack or not keywords:
        return False

    phrase_keywords = [keyword for keyword in keywords if " " in keyword]
    for keyword in phrase_keywords:
        if keyword and keyword in haystack:
            return True

    hits = {keyword for keyword in keywords if keyword and keyword in haystack}
    if not hits:
        return False

    if len(hits) >= 2:
        return True

    # Accept single matches only when they correspond to the condensed team
    # name (e.g. ``uscmunster``), not generic tokens like "Volleys".
    return any(keyword in hits for keyword in strong_keywords if keyword)


def _http_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> requests.Response:
    last_error: Optional[Exception] = None
    merged_headers = dict(REQUEST_HEADERS)
    if headers:
        merged_headers.update(headers)
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                timeout=30,
                headers=merged_headers,
                params=params,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:  # pragma: no cover - network errors
            last_error = exc
            if isinstance(exc, (requests.exceptions.ProxyError, requests.exceptions.ConnectionError)):
                raise
            if attempt == retries - 1:
                raise
            backoff = delay_seconds * (2 ** attempt)
            time.sleep(backoff)
    else:  # pragma: no cover
        if last_error:
            raise last_error
        raise RuntimeError("Unbekannter Fehler beim Abrufen von Daten.")


def fetch_html(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
) -> str:
    response = _http_get(
        url,
        headers={**HTML_ACCEPT_HEADER, **(headers or {})},
        params=params,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


def fetch_rss(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        headers=RSS_ACCEPT_HEADER,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})(?:,\s*(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
)


def parse_date_label(value: str) -> Optional[datetime]:
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = int(match.group("year"))
    if year < 100:
        year += 2000
    hour = int(match.group("hour")) if match.group("hour") else 0
    minute = int(match.group("minute")) if match.group("minute") else 0
    try:
        return datetime(year, month, day, hour, minute, tzinfo=BERLIN_TZ)
    except ValueError:
        return None


def _download_schedule_text(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


def fetch_schedule(
    url: str = DEFAULT_SCHEDULE_URL,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> List[Match]:
    csv_text = _download_schedule_text(url, retries=retries, delay_seconds=delay_seconds)
    return parse_schedule(csv_text)


def download_schedule(
    destination: Path,
    *,
    url: str = DEFAULT_SCHEDULE_URL,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Path:
    csv_text = _download_schedule_text(url, retries=retries, delay_seconds=delay_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(csv_text, encoding="utf-8")
    return destination


def fetch_schedule_match_metadata(
    url: str = SCHEDULE_PAGE_URL,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Dict[str, Dict[str, Optional[str]]]:
    try:
        response = _http_get(
            url,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except requests.RequestException:
        return _merge_manual_schedule_metadata({})
    soup = BeautifulSoup(response.text, "html.parser")
    metadata: Dict[str, Dict[str, Optional[str]]] = {}
    current_match_id: Optional[str] = None

    rows = soup.select("table tr")
    for row in rows:
        id_cell = row.find("td", id=re.compile(r"^match_(\d+)$"))
        if id_cell and id_cell.has_attr("id"):
            match = re.search(r"match_(\d+)", id_cell["id"])
            if match:
                current_match_id = match.group(1)

        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        number_text = cells[1].get_text(strip=True)
        if not number_text or not number_text.isdigit():
            continue

        match_number = number_text
        entry = metadata.setdefault(
            match_number,
            {
                "match_id": None,
                "info_url": None,
                "stats_url": None,
                "scoresheet_url": None,
            },
        )
        if current_match_id:
            entry["match_id"] = current_match_id

        for anchor in row.select("a[href]"):
            href = anchor["href"]
            full_href = urljoin(VBL_BASE_URL, href)
            title = (anchor.get("title") or "").lower()
            if "matchdetails" in href.lower():
                entry["info_url"] = full_href
            elif "scoresheet" in href.lower():
                entry["scoresheet_url"] = full_href
            elif "statistik" in title or "uploads" in href.lower():
                entry["stats_url"] = full_href

    return _merge_manual_schedule_metadata(metadata)


def build_match_details_url(match_id: str) -> str:
    return (
        "https://www.volleyball-bundesliga.de/popup/matchSeries/matchDetails.xhtml"
        f"?matchId={match_id}&hideHistoryBackButton=true"
    )


MVP_NAME_PART = r"[A-ZÄÖÜÀ-ÖØ-Þ][A-Za-zÄÖÜÖÄÜà-öø-ÿß'`´\-]*"
MVP_PAREN_PATTERN = re.compile(
    rf"({MVP_NAME_PART}(?:\s+{MVP_NAME_PART})*)\s*\((Gold|Silber|Silver)\)",
    re.IGNORECASE,
)
MVP_COLON_PATTERN = re.compile(
    r"MVP\s*(Gold|Silber|Silver)\s*[:\-]\s*([^,;.()]+)",
    re.IGNORECASE,
)
MVP_SUFFIX_PATTERN = re.compile(
    r"(Gold|Silber|Silver)[-\s]*MVP\s*[:\-]?\s*([^,;.()]+)",
    re.IGNORECASE,
)
MVP_KEYWORD_PATTERN = re.compile(r"MVP", re.IGNORECASE)
MVP_LOWERCASE_PARTS = {
    "de",
    "da",
    "del",
    "van",
    "von",
    "der",
    "den",
    "la",
    "le",
    "di",
    "dos",
    "das",
    "du",
}


def _normalize_medal_label(label: str) -> Optional[str]:
    normalized = label.strip().lower()
    if not normalized:
        return None
    if normalized == "silver":
        normalized = "silber"
    if normalized == "gold":
        return "Gold"
    if normalized == "silber":
        return "Silber"
    return None


def _clean_mvp_name(value: str) -> Optional[str]:
    tokens = [token for token in re.split(r"\s+", value.strip()) if token]
    if not tokens:
        return None
    collected: List[str] = []
    for token in reversed(tokens):
        cleaned = token.strip(",;:-")
        if not cleaned:
            continue
        lower = cleaned.lower()
        if not collected:
            collected.append(cleaned)
            continue
        if cleaned[0].isupper() or lower in MVP_LOWERCASE_PARTS:
            collected.append(cleaned)
        else:
            break
    collected.reverse()
    if not collected:
        return None
    return " ".join(collected)


def _extract_mvp_entries_from_text(text: str) -> Dict[str, str]:
    compact = " ".join(text.split())
    if not compact or "mvp" not in compact.lower():
        return {}
    winners: Dict[str, str] = {}
    for pattern in (MVP_PAREN_PATTERN,):
        for match in pattern.finditer(compact):
            medal = _normalize_medal_label(match.group(2))
            name = _clean_mvp_name(match.group(1))
            if medal and name and medal not in winners:
                winners[medal] = name
    for pattern in (MVP_COLON_PATTERN, MVP_SUFFIX_PATTERN):
        for match in pattern.finditer(compact):
            medal = _normalize_medal_label(match.group(1))
            name = _clean_mvp_name(match.group(2))
            if medal and name and medal not in winners:
                winners[medal] = name
    return winners


def _parse_match_mvps_from_text(soup: BeautifulSoup) -> Tuple[MVPSelection, ...]:
    collected: Dict[str, str] = {}
    seen_texts: set[str] = set()
    candidates: List[str] = []

    for element in soup.select(".hint"):
        text = element.get_text(" ", strip=True)
        compact = " ".join(text.split())
        if compact and compact not in seen_texts and MVP_KEYWORD_PATTERN.search(compact):
            candidates.append(compact)
            seen_texts.add(compact)

    for node in soup.find_all(string=MVP_KEYWORD_PATTERN):
        text = str(node)
        compact = " ".join(text.split())
        if compact and compact not in seen_texts:
            candidates.append(compact)
            seen_texts.add(compact)

    for text in candidates:
        entries = _extract_mvp_entries_from_text(text)
        for medal in ("Gold", "Silber"):
            if medal in entries and medal not in collected:
                collected[medal] = entries[medal]
        for medal, name in entries.items():
            if medal not in collected:
                collected[medal] = name
        if len(collected) >= 2:
            break

    if not collected:
        return ()

    ordered: List[MVPSelection] = []
    for medal in ("Gold", "Silber"):
        name = collected.get(medal)
        if name:
            ordered.append(MVPSelection(medal=medal, name=name, team=None))
    for medal, name in collected.items():
        if medal not in {"Gold", "Silber"}:
            ordered.append(MVPSelection(medal=medal, name=name, team=None))
    return tuple(ordered)


def _parse_match_mvps_from_table(soup: BeautifulSoup) -> List[MVPSelection]:
    header = soup.select_one(
        ".samsContentBoxHeader:-soup-contains(\"Most Valuable Player\")"
    )
    if not header:
        return []
    container = header.find_next(class_="samsContentBoxContent")
    if not container:
        return []

    team_names = [
        cell.get_text(" ", strip=True)
        for cell in soup.select(".samsMatchDetailsTeamName")
        if cell.get_text(strip=True)
    ]
    teams_by_id: Dict[str, str] = {}
    if team_names:
        teams_by_id["mvpTeam1"] = team_names[0]
        if len(team_names) > 1:
            teams_by_id["mvpTeam2"] = team_names[1]

    raw_entries: List[Dict[str, Optional[str]]] = []
    for index, cell in enumerate(container.select("td")):
        block = cell.select_one(".samsOutputMvp")
        if not block:
            continue
        name_anchor = block.select_one(".samsOutputMvpPlayerName a")
        if not name_anchor:
            continue
        name = name_anchor.get_text(strip=True)
        if not name:
            continue

        medal: Optional[str] = None
        medal_image = block.select_one(".samsOutputMvpMedalImage img[src]")
        if medal_image:
            source = medal_image["src"].lower()
            if "gold" in source:
                medal = "Gold"
            elif "silber" in source or "silver" in source:
                medal = "Silber"
        if not medal:
            extracted = _extract_mvp_entries_from_text(block.get_text(" ", strip=True))
            if "Gold" in extracted:
                medal = "Gold"
            elif "Silber" in extracted:
                medal = "Silber"
            elif extracted:
                medal = next(iter(extracted.keys()))

        team: Optional[str] = None
        cell_id = cell.get("id")
        if cell_id and cell_id in teams_by_id:
            team = teams_by_id[cell_id]
        elif team_names and index < len(team_names):
            team = team_names[index]

        raw_entries.append({"medal": medal, "name": name, "team": team})

    if not raw_entries:
        return []

    used_medals = {entry["medal"] for entry in raw_entries if entry.get("medal")}
    for entry in raw_entries:
        if entry.get("medal"):
            continue
        for candidate in ("Gold", "Silber"):
            if candidate not in used_medals:
                entry["medal"] = candidate
                used_medals.add(candidate)
                break

    selections: List[MVPSelection] = []
    for entry in raw_entries:
        name = entry.get("name")
        if not name:
            continue
        medal = entry.get("medal")
        team = entry.get("team")
        team_value = team.strip() if isinstance(team, str) and team.strip() else None
        selections.append(MVPSelection(medal=medal, name=name, team=team_value))
    return selections


def _parse_match_mvps(soup: BeautifulSoup) -> Tuple[MVPSelection, ...]:
    table_entries = _parse_match_mvps_from_table(soup)
    if table_entries:
        return tuple(table_entries)
    return _parse_match_mvps_from_text(soup)


def fetch_match_details(
    match_id: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Dict[str, object]:
    url = build_match_details_url(match_id)
    response = _http_get(
        url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    referees: List[str] = []
    attendance: Optional[str] = None

    for table in soup.select("table"):
        for row in table.select("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["th", "td"])
            ]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            value = _normalize_schedule_field(cells[1])
            if not value:
                continue
            if "schiedsrichter" in label and "linienrichter" not in label:
                referees.append(value)
            elif "zuschauer" in label:
                attendance = value

    mvps = _parse_match_mvps(soup)

    return {
        "referees": tuple(referees),
        "attendance": attendance,
        "mvps": mvps,
    }


def enrich_match(
    match: Match,
    metadata: Dict[str, Dict[str, Optional[str]]],
    detail_cache: Dict[str, Dict[str, object]],
) -> Match:
    match_number = match.match_number
    meta = metadata.get(match_number) if match_number else None

    match_id = match.match_id or (meta.get("match_id") if meta else None)
    info_url = match.info_url or (meta.get("info_url") if meta else None)
    stats_url = match.stats_url or (meta.get("stats_url") if meta else None)
    scoresheet_url = match.scoresheet_url or (meta.get("scoresheet_url") if meta else None)

    referees = tuple(match.referees) if match.referees else ()
    attendance = match.attendance
    mvps = tuple(match.mvps) if match.mvps else ()

    if match_id:
        detail = detail_cache.get(match_id)
        if detail is None:
            try:
                detail = fetch_match_details(match_id)
            except requests.RequestException:
                detail = {}
            detail_cache[match_id] = detail
        fetched_referees = detail.get("referees") or ()
        if fetched_referees:
            referees = tuple(fetched_referees)
        fetched_attendance = detail.get("attendance")
        if fetched_attendance:
            attendance = fetched_attendance
        fetched_mvps = detail.get("mvps") or ()
        if fetched_mvps:
            normalized: List[MVPSelection] = []
            for entry in fetched_mvps:
                if isinstance(entry, MVPSelection):
                    normalized.append(entry)
                elif isinstance(entry, (tuple, list)) and len(entry) >= 2:
                    medal = entry[0] if entry[0] is not None else None
                    name = str(entry[1])
                    team = entry[2] if len(entry) > 2 else None
                    normalized.append(
                        MVPSelection(
                            medal=str(medal) if medal not in {None, ""} else None,
                            name=name,
                            team=str(team) if team not in {None, ""} else None,
                        )
                    )
            if normalized:
                mvps = tuple(normalized)

    return replace(
        match,
        match_number=match_number,
        match_id=match_id,
        info_url=info_url,
        stats_url=stats_url,
        scoresheet_url=scoresheet_url,
        referees=referees,
        attendance=attendance,
        mvps=mvps,
    )


def enrich_matches(
    matches: Sequence[Match],
    metadata: Dict[str, Dict[str, Optional[str]]],
    detail_cache: Optional[Dict[str, Dict[str, object]]] = None,
) -> List[Match]:
    cache = detail_cache if detail_cache is not None else {}
    return [enrich_match(match, metadata, cache) for match in matches]


def _download_roster_text(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        headers={"Accept": "text/csv"},
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.content.decode("latin-1")

OFFICIAL_ROLE_PRIORITY: Tuple[str, ...] = (
    "Trainer",
    "Co-Trainer",
    "Co-Trainer (Scout)",
    "Statistiker",
    "Physiotherapeut",
    "Arzt",
)


def _official_sort_key(member: RosterMember) -> Tuple[int, str, str]:
    role = (member.role or "").strip()
    normalized = role.lower()
    order = len(OFFICIAL_ROLE_PRIORITY)
    for index, label in enumerate(OFFICIAL_ROLE_PRIORITY):
        if normalized == label.lower():
            order = index
            break
    return (order, normalized, member.name.lower())


def parse_roster(csv_text: str) -> List[RosterMember]:
    buffer = StringIO(csv_text)
    reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
    players: List[RosterMember] = []
    officials: List[RosterMember] = []
    for row in reader:
        name = (row.get("Titel Vorname Nachname") or "").strip()
        if not name:
            continue
        number_raw = (row.get("Trikot") or "").strip()
        role = (row.get("Position/Funktion Offizieller") or "").strip()
        height = (row.get("Größe") or "").strip()
        birthdate = (row.get("Geburtsdatum") or "").strip()
        nationality = (row.get("Staatsangehörigkeit") or "").strip()
        number_value: Optional[int] = None
        is_official = True
        if number_raw:
            compact = number_raw.replace(" ", "")
            if compact.isdigit():
                number_value = int(compact)
                is_official = False
        member = RosterMember(
            number_label=number_raw or None,
            number_value=number_value,
            name=name,
            role=role,
            is_official=is_official,
            height=height or None,
            birthdate_label=birthdate or None,
            nationality=nationality or None,
        )
        if member.is_official:
            officials.append(member)
        else:
            players.append(member)

    players.sort(
        key=lambda member: (
            member.number_value if member.number_value is not None else 10_000,
            member.name.lower(),
        )
    )
    officials.sort(key=_official_sort_key)
    return players + officials


def collect_team_roster(
    team_name: str,
    directory: Path,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> List[RosterMember]:
    url = get_team_roster_url(team_name)
    if not url:
        return []
    csv_text = _download_roster_text(url, retries=retries, delay_seconds=delay_seconds)
    directory.mkdir(parents=True, exist_ok=True)
    slug = slugify_team_name(team_name) or "team"
    destination = directory / f"{slug}.csv"
    destination.write_text(csv_text, encoding="utf-8")
    return parse_roster(csv_text)


def load_schedule_from_file(path: Path) -> List[Match]:
    csv_text = path.read_text(encoding="utf-8")
    return parse_schedule(csv_text)


def parse_schedule(csv_text: str) -> List[Match]:
    buffer = StringIO(csv_text)
    reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
    matches: List[Match] = []
    for row in reader:
        try:
            kickoff = parse_kickoff(row["Datum"], row["Uhrzeit"])
        except (KeyError, ValueError):
            continue

        home_team = row.get("Mannschaft 1", "").strip()
        away_team = row.get("Mannschaft 2", "").strip()
        host = row.get("Gastgeber", "").strip()
        location = row.get("Austragungsort", "").strip()
        result = build_match_result(row)
        match_number = (row.get("#") or "").strip() or None
        attendance = _normalize_schedule_field(row.get("Zuschauerzahl"))
        referee_entries = _parse_referee_field(row.get("Schiedsgericht"))

        matches.append(
            Match(
                kickoff=kickoff,
                home_team=home_team,
                away_team=away_team,
                host=host,
                location=location,
                result=result,
                match_number=match_number,
                referees=referee_entries,
                attendance=attendance,
            )
        )
    return matches


def _normalize_schedule_field(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    if not value or value in {"-", "–"}:
        return None
    return value


def _parse_referee_field(raw: Optional[str]) -> Tuple[str, ...]:
    value = _normalize_schedule_field(raw)
    if not value:
        return ()
    parts = [segment.strip() for segment in re.split(r"[;,/]", value) if segment.strip()]
    return tuple(parts)


def parse_kickoff(date_str: str, time_str: str) -> datetime:
    combined = f"{date_str.strip()} {time_str.strip()}"
    kickoff = datetime.strptime(combined, "%d.%m.%Y %H:%M:%S")
    return kickoff.replace(tzinfo=BERLIN_TZ)


RESULT_PATTERN = re.compile(
    r"\s*(?P<score>\d+:\d+)"
    r"(?:\s*/\s*(?P<points>\d+:\d+))?"
    r"(?:\s*\((?P<sets>[^)]+)\))?"
)


def _parse_result_text(raw: str | None) -> Optional[MatchResult]:
    if not raw:
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned in {"-", "–"}:
        return None

    match = RESULT_PATTERN.match(cleaned)
    if not match:
        return MatchResult(score=cleaned, total_points=None, sets=())

    score = match.group("score")
    points = match.group("points")
    sets_raw = match.group("sets")
    sets: tuple[str, ...] = ()
    if sets_raw:
        normalized = sets_raw.replace(",", " ")
        split_sets = [segment.strip() for segment in normalized.split() if segment.strip()]
        sets = tuple(split_sets)

    return MatchResult(score=score, total_points=points, sets=sets)


def build_match_result(row: Dict[str, str]) -> Optional[MatchResult]:
    fallback = _parse_result_text(row.get("Ergebnis"))

    score = (row.get("Satzpunkte") or "").strip()
    total_points = (row.get("Ballpunkte") or "").strip()

    sets_list: list[str] = []
    for index in range(1, 6):
        home_key = f"Satz {index} - Ballpunkte 1"
        away_key = f"Satz {index} - Ballpunkte 2"
        home_points = (row.get(home_key) or "").strip()
        away_points = (row.get(away_key) or "").strip()
        if home_points and away_points:
            sets_list.append(f"{home_points}:{away_points}")

    if score or total_points or sets_list:
        if not score and fallback:
            score = fallback.score
        if not total_points and fallback and fallback.total_points:
            total_points = fallback.total_points
        sets: tuple[str, ...]
        if sets_list:
            sets = tuple(sets_list)
        elif fallback:
            sets = fallback.sets
        else:
            sets = ()

        cleaned_total = total_points or None
        if score:
            return MatchResult(score=score, total_points=cleaned_total, sets=sets)
        if fallback:
            return MatchResult(score=fallback.score, total_points=cleaned_total, sets=sets)
        return None

    return fallback


def normalize_name(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "á": "a",
        "à": "a",
        "â": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "ú": "u",
        "ù": "u",
        "û": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("muenster", "munster")
    normalized = normalized.replace("mnster", "munster")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def slugify_team_name(value: str) -> str:
    simplified = simplify_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", simplified)
    return slug.strip("-")


def is_usc(name: str) -> bool:
    normalized = normalize_name(name)
    return "usc" in normalized and "munster" in normalized


def _build_team_homepages() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "https://www.stuttgarts-schoenster-sport.de/",
        "Binder Blaubären TSV Flacht": "https://binderblaubaeren.de/",
        "Dresdner SC": "https://www.dscvolley.de/",
        "ETV Hamburger Volksbank Volleys": "https://www.etv-hamburg.de/de/etv-hamburger-volksbank-volleys/",
        "Ladies in Black Aachen": "https://ladies-in-black.de/",
        "SSC Palmberg Schwerin": "https://www.schweriner-sc.com/",
        "Schwarz-Weiß Erfurt": "https://schwarz-weiss-erfurt.de/",
        "Skurios Volleys Borken": "https://www.skurios-volleys-borken.de/",
        "USC Münster": USC_HOMEPAGE,
        "VC Wiesbaden": "https://www.vc-wiesbaden.de/",
        "VfB Suhl LOTTO Thüringen": "https://volleyball-suhl.de/",
    }
    return {normalize_name(name): url for name, url in pairs.items()}


TEAM_HOMEPAGES = _build_team_homepages()


_MANUAL_STATS_TOTALS_DATA: Dict[str, Any] = {
    "matches": [
        {
            "stats_url": "https://www.volleyball-bundesliga.de/uploads/831866c1-9e16-46f8-827c-4b0dd011928b",
            "teams": [
                {
                    "name": "SSC Palmberg Schwerin",
                    "serve": {
                        "attempts": 74,
                        "errors": 6,
                        "points": 10,
                    },
                    "reception": {
                        "attempts": 37,
                        "errors": 3,
                        "positive_pct": "51%",
                        "perfect_pct": "24%",
                    },
                    "attack": {
                        "attempts": 78,
                        "errors": 10,
                        "blocked": 3,
                        "points": 37,
                        "success_pct": "47%",
                    },
                    "block": {
                        "points": 11,
                    },
                },
                {
                    "name": "ETV Hamburger Volksbank Volleys",
                    "aliases": [
                        "ETV Hamburger Volksbank V.",
                    ],
                    "serve": {
                        "attempts": 42,
                        "errors": 5,
                        "points": 3,
                    },
                    "reception": {
                        "attempts": 68,
                        "errors": 10,
                        "positive_pct": "29%",
                        "perfect_pct": "12%",
                    },
                    "attack": {
                        "attempts": 81,
                        "errors": 9,
                        "blocked": 11,
                        "points": 19,
                        "success_pct": "23%",
                    },
                    "block": {
                        "points": 3,
                    },
                },
            ],
        },
        {
            "stats_url": "https://www.volleyball-bundesliga.de/uploads/70a7c2ba-97bc-4478-8e8e-e55ec764d2e6",
            "teams": [
                {
                    "name": "USC Münster",
                    "serve": {
                        "attempts": 105,
                        "errors": 19,
                        "points": 14,
                    },
                    "reception": {
                        "attempts": 88,
                        "errors": 15,
                        "positive_pct": "30%",
                        "perfect_pct": "15%",
                    },
                    "attack": {
                        "attempts": 132,
                        "errors": 10,
                        "blocked": 8,
                        "points": 52,
                        "success_pct": "39%",
                    },
                    "block": {
                        "points": 9,
                    },
                    "players": [
                        {
                            "name": "MOLENAAR Pippa",
                            "jersey_number": 1,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 1,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 32,
                                "receptions_errors": 5,
                                "receptions_positive_pct": "34%",
                                "receptions_perfect_pct": "19%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 2,
                            },
                        },
                        {
                            "name": "SCHAEFER Lara-Marie",
                            "jersey_number": 2,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 12,
                                "receptions_errors": 3,
                                "receptions_positive_pct": "33%",
                                "receptions_perfect_pct": "17%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 1,
                            },
                        },
                        {
                            "name": "SPÖLER Esther",
                            "jersey_number": 3,
                            "total_points": 7,
                            "break_points": 3,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 10,
                                "serves_errors": 2,
                                "serves_points": 1,
                                "receptions_attempts": 18,
                                "receptions_errors": 3,
                                "receptions_positive_pct": "22%",
                                "receptions_perfect_pct": "11%",
                                "attacks_attempts": 23,
                                "attacks_errors": 2,
                                "attacks_blocked": 1,
                                "attacks_points": 8,
                                "attacks_success_pct": "35%",
                                "blocks_points": 1,
                                "break_points": 3,
                                "plus_minus": 1,
                            },
                        },
                        {
                            "name": "MALM Cecilia",
                            "jersey_number": 5,
                            "total_points": 8,
                            "break_points": 3,
                            "plus_minus": 4,
                            "metrics": {
                                "serves_attempts": 12,
                                "serves_errors": 3,
                                "serves_points": 2,
                                "receptions_attempts": 16,
                                "receptions_errors": 3,
                                "receptions_positive_pct": "25%",
                                "receptions_perfect_pct": "13%",
                                "attacks_attempts": 24,
                                "attacks_errors": 2,
                                "attacks_blocked": 2,
                                "attacks_points": 9,
                                "attacks_success_pct": "38%",
                                "blocks_points": 2,
                                "break_points": 3,
                                "plus_minus": 4,
                            },
                        },
                        {
                            "name": "KÖMMLING Elena",
                            "jersey_number": 7,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "LIU Yina",
                            "jersey_number": 8,
                            "total_points": 2,
                            "break_points": 1,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 12,
                                "serves_errors": 2,
                                "serves_points": 1,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 2,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 1,
                                "attacks_success_pct": "50%",
                                "blocks_points": 1,
                                "break_points": 1,
                                "plus_minus": 1,
                            },
                        },
                        {
                            "name": "JORDAN Emilia",
                            "jersey_number": 9,
                            "total_points": 1,
                            "break_points": 1,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 25,
                                "serves_errors": 5,
                                "serves_points": 4,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 2,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 1,
                                "attacks_success_pct": "50%",
                                "blocks_points": 0,
                                "break_points": 1,
                                "plus_minus": 1,
                            },
                        },
                        {
                            "name": "STROTHOFF Amelie",
                            "jersey_number": 10,
                            "total_points": 6,
                            "break_points": 2,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 5,
                                "serves_errors": 1,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 10,
                                "attacks_errors": 0,
                                "attacks_blocked": 1,
                                "attacks_points": 4,
                                "attacks_success_pct": "40%",
                                "blocks_points": 1,
                                "break_points": 2,
                                "plus_minus": 1,
                            },
                        },
                        {
                            "name": "HEIL Franziska",
                            "jersey_number": 11,
                            "total_points": 1,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 1,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 1,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "WAELKENS Anke",
                            "jersey_number": 12,
                            "total_points": 9,
                            "break_points": 4,
                            "plus_minus": 3,
                            "metrics": {
                                "serves_attempts": 6,
                                "serves_errors": 1,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 8,
                                "attacks_errors": 1,
                                "attacks_blocked": 1,
                                "attacks_points": 3,
                                "attacks_success_pct": "38%",
                                "blocks_points": 2,
                                "break_points": 4,
                                "plus_minus": 3,
                            },
                        },
                        {
                            "name": "FORD Brianna",
                            "jersey_number": 14,
                            "total_points": 24,
                            "break_points": 12,
                            "plus_minus": 5,
                            "metrics": {
                                "serves_attempts": 18,
                                "serves_errors": 3,
                                "serves_points": 4,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 38,
                                "attacks_errors": 4,
                                "attacks_blocked": 2,
                                "attacks_points": 17,
                                "attacks_success_pct": "45%",
                                "blocks_points": 1,
                                "break_points": 12,
                                "plus_minus": 5,
                            },
                        },
                        {
                            "name": "SCHULTZE Lena",
                            "jersey_number": 16,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 2,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "MARTIN Isabel Rebecca",
                            "jersey_number": 17,
                            "total_points": 12,
                            "break_points": 4,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 9,
                                "serves_errors": 2,
                                "serves_points": 1,
                                "receptions_attempts": 10,
                                "receptions_errors": 1,
                                "receptions_positive_pct": "30%",
                                "receptions_perfect_pct": "10%",
                                "attacks_attempts": 18,
                                "attacks_errors": 1,
                                "attacks_blocked": 1,
                                "attacks_points": 7,
                                "attacks_success_pct": "39%",
                                "blocks_points": 1,
                                "break_points": 4,
                                "plus_minus": 2,
                            },
                        },
                        {
                            "name": "SEYBERING Diane",
                            "jersey_number": 18,
                            "total_points": 5,
                            "break_points": 3,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 4,
                                "serves_errors": 0,
                                "serves_points": 1,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 6,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 2,
                                "attacks_success_pct": "33%",
                                "blocks_points": 0,
                                "break_points": 3,
                                "plus_minus": 2,
                            },
                        },
                    ],
                },
                {
                    "name": "SSC Palmberg Schwerin",
                    "serve": {
                        "attempts": 107,
                        "errors": 19,
                        "points": 15,
                    },
                    "reception": {
                        "attempts": 86,
                        "errors": 14,
                        "positive_pct": "33%",
                        "perfect_pct": "15%",
                    },
                    "attack": {
                        "attempts": 129,
                        "errors": 10,
                        "blocked": 9,
                        "points": 50,
                        "success_pct": "39%",
                    },
                    "block": {
                        "points": 8,
                    },
                },
            ],
        },
        {
            "stats_url": "https://www.volleyball-bundesliga.de/uploads/19bb6c96-f1cc-4867-9058-0864849ec964",
            "teams": [
                {
                    "name": "Binder Blaubären TSV Flacht",
                    "aliases": [
                        "Binder Blaubären Flacht",
                    ],
                    "serve": {
                        "attempts": 50,
                        "errors": 13,
                        "points": 2,
                    },
                    "reception": {
                        "attempts": 61,
                        "errors": 5,
                        "positive_pct": "21%",
                        "perfect_pct": "8%",
                    },
                    "attack": {
                        "attempts": 72,
                        "errors": 9,
                        "blocked": 7,
                        "points": 19,
                        "success_pct": "26%",
                    },
                    "block": {
                        "points": 6,
                    },
                },
                {
                    "name": "USC Münster",
                    "serve": {
                        "attempts": 74,
                        "errors": 13,
                        "points": 5,
                    },
                    "reception": {
                        "attempts": 37,
                        "errors": 2,
                        "positive_pct": "35%",
                        "perfect_pct": "14%",
                    },
                    "attack": {
                        "attempts": 82,
                        "errors": 7,
                        "blocked": 6,
                        "points": 40,
                        "success_pct": "49%",
                    },
                    "block": {
                        "points": 7,
                    },
                    "players": [
                        {
                            "name": "MOLENAAR Pippa",
                            "jersey_number": 1,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 3,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "67%",
                                "receptions_perfect_pct": "33%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "SCHAEFER Lara-Marie",
                            "jersey_number": 2,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 5,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "20%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "SPÖLER Esther",
                            "jersey_number": 3,
                            "total_points": 10,
                            "break_points": 4,
                            "plus_minus": 7,
                            "metrics": {
                                "serves_attempts": 9,
                                "serves_errors": 1,
                                "serves_points": 1,
                                "receptions_attempts": 2,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "100%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 11,
                                "attacks_errors": 1,
                                "attacks_blocked": 1,
                                "attacks_points": 7,
                                "attacks_success_pct": "64%",
                                "blocks_points": 2,
                                "break_points": 4,
                                "plus_minus": 7,
                            },
                        },
                        {
                            "name": "MALM Cecilia",
                            "jersey_number": 5,
                            "total_points": 6,
                            "break_points": 4,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 13,
                                "serves_errors": 1,
                                "serves_points": 2,
                                "receptions_attempts": 10,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "40%",
                                "receptions_perfect_pct": "20%",
                                "attacks_attempts": 12,
                                "attacks_errors": 3,
                                "attacks_blocked": 0,
                                "attacks_points": 4,
                                "attacks_success_pct": "33%",
                                "blocks_points": 0,
                                "break_points": 4,
                                "plus_minus": 2,
                            },
                        },
                        {
                            "name": "KÖMMLING Elena",
                            "jersey_number": 7,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "LIU Yina",
                            "jersey_number": 8,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 1,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "JORDAN Emilia",
                            "jersey_number": 9,
                            "total_points": 1,
                            "break_points": 1,
                            "plus_minus": -3,
                            "metrics": {
                                "serves_attempts": 13,
                                "serves_errors": 3,
                                "serves_points": 0,
                                "receptions_attempts": 1,
                                "receptions_errors": 1,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 2,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 1,
                                "attacks_success_pct": "50%",
                                "blocks_points": 0,
                                "break_points": 1,
                                "plus_minus": -3,
                            },
                        },
                        {
                            "name": "STROTHOFF Amelie",
                            "jersey_number": 10,
                            "total_points": 2,
                            "break_points": 1,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 5,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 10,
                                "receptions_errors": 1,
                                "receptions_positive_pct": "20%",
                                "receptions_perfect_pct": "20%",
                                "attacks_attempts": 4,
                                "attacks_errors": 0,
                                "attacks_blocked": 1,
                                "attacks_points": 2,
                                "attacks_success_pct": "50%",
                                "blocks_points": 0,
                                "break_points": 1,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "HEIL Franziska",
                            "jersey_number": 11,
                            "total_points": 0,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 0,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "WAELKENS Anke",
                            "jersey_number": 12,
                            "total_points": 3,
                            "break_points": 3,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 8,
                                "serves_errors": 1,
                                "serves_points": 1,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 1,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 0,
                                "attacks_success_pct": "0%",
                                "blocks_points": 2,
                                "break_points": 3,
                                "plus_minus": 2,
                            },
                        },
                        {
                            "name": "FORD Brianna",
                            "jersey_number": 14,
                            "total_points": 17,
                            "break_points": 10,
                            "plus_minus": 13,
                            "metrics": {
                                "serves_attempts": 10,
                                "serves_errors": 2,
                                "serves_points": 1,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 29,
                                "attacks_errors": 1,
                                "attacks_blocked": 1,
                                "attacks_points": 16,
                                "attacks_success_pct": "55%",
                                "blocks_points": 0,
                                "break_points": 10,
                                "plus_minus": 13,
                            },
                        },
                        {
                            "name": "SCHULTZE Lena",
                            "jersey_number": 16,
                            "total_points": 1,
                            "break_points": 0,
                            "plus_minus": 0,
                            "metrics": {
                                "serves_attempts": 0,
                                "serves_errors": 0,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 4,
                                "attacks_errors": 1,
                                "attacks_blocked": 0,
                                "attacks_points": 1,
                                "attacks_success_pct": "25%",
                                "blocks_points": 0,
                                "break_points": 0,
                                "plus_minus": 0,
                            },
                        },
                        {
                            "name": "MARTIN Isabel Rebecca",
                            "jersey_number": 17,
                            "total_points": 8,
                            "break_points": 6,
                            "plus_minus": 2,
                            "metrics": {
                                "serves_attempts": 9,
                                "serves_errors": 2,
                                "serves_points": 0,
                                "receptions_attempts": 6,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "33%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 16,
                                "attacks_errors": 1,
                                "attacks_blocked": 3,
                                "attacks_points": 7,
                                "attacks_success_pct": "44%",
                                "blocks_points": 1,
                                "break_points": 6,
                                "plus_minus": 2,
                            },
                        },
                        {
                            "name": "SEYBERING Diane",
                            "jersey_number": 18,
                            "total_points": 4,
                            "break_points": 3,
                            "plus_minus": 1,
                            "metrics": {
                                "serves_attempts": 6,
                                "serves_errors": 3,
                                "serves_points": 0,
                                "receptions_attempts": 0,
                                "receptions_errors": 0,
                                "receptions_positive_pct": "0%",
                                "receptions_perfect_pct": "0%",
                                "attacks_attempts": 3,
                                "attacks_errors": 0,
                                "attacks_blocked": 0,
                                "attacks_points": 2,
                                "attacks_success_pct": "67%",
                                "blocks_points": 2,
                                "break_points": 3,
                                "plus_minus": 1,
                            },
                        },
                    ],
                },
            ],
        },
    ],
}


_MANUAL_STATS_TOTALS: Optional[
    Dict[
        str,
        List[
            Tuple[Tuple[str, ...], str, MatchStatsMetrics, Tuple[MatchPlayerStats, ...]]
        ],
    ]
] = None


def _load_manual_stats_totals() -> Dict[
    str,
    List[Tuple[Tuple[str, ...], str, MatchStatsMetrics, Tuple[MatchPlayerStats, ...]]],
]:
    global _MANUAL_STATS_TOTALS
    if _MANUAL_STATS_TOTALS is not None:
        return _MANUAL_STATS_TOTALS

    payload = _MANUAL_STATS_TOTALS_DATA
    manual: Dict[
        str,
        List[Tuple[Tuple[str, ...], str, MatchStatsMetrics, Tuple[MatchPlayerStats, ...]]],
    ] = {}
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    for match_entry in matches:
        if not isinstance(match_entry, dict):
            continue
        stats_url = match_entry.get("stats_url")
        if not stats_url:
            continue
        teams_entries: List[
            Tuple[Tuple[str, ...], str, MatchStatsMetrics, Tuple[MatchPlayerStats, ...]]
        ] = []
        for team_entry in match_entry.get("teams", []) or []:
            if not isinstance(team_entry, dict):
                continue
            name = team_entry.get("name")
            if not name:
                continue
            serve = team_entry.get("serve") or {}
            reception = team_entry.get("reception") or {}
            attack = team_entry.get("attack") or {}
            block = team_entry.get("block") or {}
            try:
                serve_attempts = int(serve["attempts"])
                serve_errors = int(serve["errors"])
                serve_points = int(serve["points"])
                reception_attempts = int(reception["attempts"])
                reception_errors = int(reception["errors"])
                reception_positive_pct = str(reception["positive_pct"])
                reception_perfect_pct = str(reception["perfect_pct"])
                reception_positive = _compute_percentage_count(
                    reception_attempts, reception_positive_pct
                )
                reception_perfect = _compute_percentage_count(
                    reception_attempts, reception_perfect_pct
                )
                attack_attempts = int(attack["attempts"])
                attack_errors = int(attack["errors"])
                attack_blocked = int(attack["blocked"])
                attack_points = int(attack["points"])
                attack_success_pct = str(attack["success_pct"])
                block_points = int(block["points"])
                metrics = MatchStatsMetrics(
                    serves_attempts=serve_attempts,
                    serves_errors=serve_errors,
                    serves_points=serve_points,
                    receptions_attempts=reception_attempts,
                    receptions_errors=reception_errors,
                    receptions_positive_pct=reception_positive_pct,
                    receptions_perfect_pct=reception_perfect_pct,
                    attacks_attempts=attack_attempts,
                    attacks_errors=attack_errors,
                    attacks_blocked=attack_blocked,
                    attacks_points=attack_points,
                    attacks_success_pct=attack_success_pct,
                    blocks_points=block_points,
                    receptions_positive=reception_positive,
                    receptions_perfect=reception_perfect,
                )
            except (KeyError, TypeError, ValueError):
                continue
            players: List[MatchPlayerStats] = []
            for player_entry in team_entry.get("players", []) or []:
                if not isinstance(player_entry, dict):
                    continue
                player_name = player_entry.get("name")
                if not player_name:
                    continue
                metrics_payload = player_entry.get("metrics") or {}
                try:
                    reception_attempts = int(
                        metrics_payload.get("receptions_attempts", 0)
                    )
                    reception_positive_pct = str(
                        metrics_payload.get("receptions_positive_pct", "0%")
                    )
                    reception_perfect_pct = str(
                        metrics_payload.get("receptions_perfect_pct", "0%")
                    )
                    reception_positive = _compute_percentage_count(
                        reception_attempts, reception_positive_pct
                    )
                    reception_perfect = _compute_percentage_count(
                        reception_attempts, reception_perfect_pct
                    )
                    player_metrics = MatchStatsMetrics(
                        serves_attempts=int(metrics_payload.get("serves_attempts", 0)),
                        serves_errors=int(metrics_payload.get("serves_errors", 0)),
                        serves_points=int(metrics_payload.get("serves_points", 0)),
                        receptions_attempts=reception_attempts,
                        receptions_errors=int(
                            metrics_payload.get("receptions_errors", 0)
                        ),
                        receptions_positive_pct=reception_positive_pct,
                        receptions_perfect_pct=reception_perfect_pct,
                        attacks_attempts=int(metrics_payload.get("attacks_attempts", 0)),
                        attacks_errors=int(metrics_payload.get("attacks_errors", 0)),
                        attacks_blocked=int(metrics_payload.get("attacks_blocked", 0)),
                        attacks_points=int(metrics_payload.get("attacks_points", 0)),
                        attacks_success_pct=str(
                            metrics_payload.get("attacks_success_pct", "0%")
                        ),
                        blocks_points=int(metrics_payload.get("blocks_points", 0)),
                        receptions_positive=reception_positive,
                        receptions_perfect=reception_perfect,
                    )
                except (TypeError, ValueError):
                    continue
                try:
                    jersey_number = (
                        int(player_entry.get("jersey_number"))
                        if player_entry.get("jersey_number") is not None
                        else None
                    )
                except (TypeError, ValueError):
                    jersey_number = None
                total_points_value = player_entry.get("total_points")
                try:
                    total_points = (
                        int(total_points_value)
                        if total_points_value is not None
                        else None
                    )
                except (TypeError, ValueError):
                    total_points = None
                players.append(
                    MatchPlayerStats(
                        team_name=name,
                        player_name=pretty_name(str(player_name)),
                        jersey_number=jersey_number,
                        metrics=player_metrics,
                        total_points=total_points,
                        break_points=_parse_optional_int_token(
                            str(metrics_payload.get("break_points", "0"))
                        ),
                        plus_minus=_parse_optional_int_token(
                            str(metrics_payload.get("plus_minus", "0"))
                        ),
                    )
                )
            normalized_keys: List[str] = []
            primary_key = normalize_name(name)
            normalized_keys.append(primary_key)
            for alias in team_entry.get("aliases", []) or []:
                alias_name = str(alias).strip()
                if not alias_name:
                    continue
                normalized_alias = normalize_name(alias_name)
                if normalized_alias not in normalized_keys:
                    normalized_keys.append(normalized_alias)
            teams_entries.append((tuple(normalized_keys), name, metrics, tuple(players)))
        if teams_entries:
            manual[stats_url] = teams_entries

    _MANUAL_STATS_TOTALS = manual
    return manual


def get_team_homepage(team_name: str) -> Optional[str]:
    return TEAM_HOMEPAGES.get(normalize_name(team_name))


def _build_team_roster_ids() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "776311283",
        "Binder Blaubären TSV Flacht": "776308950",
        "Dresdner SC": "776311462",
        "ETV Hamburger Volksbank Volleys": "776308974",
        "Ladies in Black Aachen": "776311428",
        "SSC Palmberg Schwerin": "776311399",
        "Schwarz-Weiß Erfurt": "776311376",
        "Skurios Volleys Borken": "776309053",
        "USC Münster": "776311313",
        "VC Wiesbaden": "776311253",
        "VfB Suhl LOTTO Thüringen": "776311348",
    }
    return {normalize_name(name): team_id for name, team_id in pairs.items()}


TEAM_ROSTER_IDS = _build_team_roster_ids()


ROSTER_EXPORT_URL = (
    "https://www.volleyball-bundesliga.de/servlet/sportsclub/TeamMemberCsvExport"
)


def get_team_roster_url(team_name: str) -> Optional[str]:
    team_id = TEAM_ROSTER_IDS.get(normalize_name(team_name))
    if not team_id:
        return None
    return f"{ROSTER_EXPORT_URL}?teamId={team_id}"


def get_team_page_url(team_name: str) -> Optional[str]:
    team_id = TEAM_ROSTER_IDS.get(normalize_name(team_name))
    if not team_id:
        return None
    return f"{TEAM_PAGE_URL}?c.teamId={team_id}&c.view=teamMain"


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _iter_cached_photos(directory: Path, slug: str) -> Iterable[Path]:
    for extension in PHOTO_EXTENSIONS:
        candidate = directory / f"{slug}{extension}"
        if candidate.exists():
            yield candidate


def _encode_photo_data_uri(path: Path, *, mime_type: Optional[str] = None) -> str:
    mime = mime_type or mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def collect_team_photo(
    team_name: str,
    directory: Path,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Optional[str]:
    slug = slugify_team_name(team_name)
    if not slug:
        return None

    directory.mkdir(parents=True, exist_ok=True)

    for cached_path in _iter_cached_photos(directory, slug):
        try:
            return _encode_photo_data_uri(cached_path)
        except OSError:
            try:
                cached_path.unlink()
            except OSError:
                pass

    page_url = get_team_page_url(team_name)
    if not page_url:
        return None

    html = fetch_html(page_url, retries=retries, delay_seconds=delay_seconds)
    soup = BeautifulSoup(html, "html.parser")
    photo_tag = None
    for img in soup.find_all("img"):
        classes = {cls.lower() for cls in (img.get("class") or [])}
        if "teamphoto" in classes:
            photo_tag = img
            break

    if not photo_tag:
        return None

    src = photo_tag.get("src") or ""
    if not src:
        return None

    photo_url = urljoin(page_url, src)
    response = _http_get(
        photo_url,
        headers={"Accept": "image/*"},
        retries=retries,
        delay_seconds=delay_seconds,
    )
    content = response.content
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or None

    suffix = Path(urlparse(photo_url).path).suffix.lower()
    if suffix not in PHOTO_EXTENSIONS:
        guessed = ""
        if content_type:
            guessed = (mimetypes.guess_extension(content_type) or "").lower()
        if guessed in PHOTO_EXTENSIONS:
            suffix = guessed
        else:
            suffix = ".jpg"

    filename = f"{slug}{suffix}"
    path = directory / filename
    path.write_bytes(content)
    return _encode_photo_data_uri(path, mime_type=content_type)


def _build_team_instagram() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "https://www.instagram.com/allianzmtvstuttgart/",
        "Binder Blaubären TSV Flacht": "https://www.instagram.com/binderblaubaerenflacht/",
        "Dresdner SC": "https://www.instagram.com/dsc1898/",
        "ETV Hamburger Volksbank Volleys": "https://www.instagram.com/etv.hamburgervolksbank.volleys/",
        "Ladies in Black Aachen": "https://www.instagram.com/ladiesinblackaachen/",
        "SSC Palmberg Schwerin": "https://www.instagram.com/sscpalmbergschwerin/",
        "Schwarz-Weiß Erfurt": "https://www.instagram.com/schwarzweisserfurt/",
        "Skurios Volleys Borken": "https://www.instagram.com/skurios_volleys_borken/",
        "USC Münster": "https://www.instagram.com/uscmuenster/",
        "VC Wiesbaden": "https://www.instagram.com/vc_wiesbaden/",
        "VfB Suhl LOTTO Thüringen": "https://www.instagram.com/vfbsuhl_lottothueringen/",
    }
    return {normalize_name(name): url for name, url in pairs.items()}


TEAM_INSTAGRAM = _build_team_instagram()


def get_team_instagram(team_name: str) -> Optional[str]:
    return TEAM_INSTAGRAM.get(normalize_name(team_name))


def _build_team_keyword_synonyms() -> Dict[str, Sequence[str]]:
    pairs: Dict[str, Sequence[str]] = {
        "Allianz MTV Stuttgart": ("MTV Stuttgart",),
        "Binder Blaubären TSV Flacht": (
            "Binder Blaubären",
            "TSV Flacht",
            "Binder Blaubären Flacht",
        ),
        "Dresdner SC": ("DSC Volleys",),
        "ETV Hamburger Volksbank Volleys": (
            "ETV Hamburg",
            "Hamburg Volleys",
            "ETV Hamburger Volksbank V.",
        ),
        "Ladies in Black Aachen": ("Ladies in Black", "Aachen Ladies"),
        "SSC Palmberg Schwerin": ("SSC Schwerin", "Palmberg Schwerin"),
        "Schwarz-Weiß Erfurt": ("Schwarz Weiss Erfurt",),
        "Skurios Volleys Borken": ("Skurios Borken",),
        "USC Münster": ("USC Muenster",),
        "VC Wiesbaden": ("VCW Wiesbaden",),
        "VfB Suhl LOTTO Thüringen": ("VfB Suhl",),
    }
    return {normalize_name(name): synonyms for name, synonyms in pairs.items()}


TEAM_KEYWORD_SYNONYMS = _build_team_keyword_synonyms()


TEAM_SHORT_NAMES: Mapping[str, str] = {
    normalize_name("Allianz MTV Stuttgart"): "Stuttgart",
    normalize_name("Binder Blaubären TSV Flacht"): "Flacht",
    normalize_name("Dresdner SC"): "Dresden",
    normalize_name("ETV Hamburger Volksbank Volleys"): "Hamburg",
    normalize_name("Ladies in Black Aachen"): "Aachen",
    normalize_name("SSC Palmberg Schwerin"): "Schwerin",
    normalize_name("Schwarz-Weiß Erfurt"): "Erfurt",
    normalize_name("Skurios Volleys Borken"): "Borken",
    normalize_name("USC Münster"): "Münster",
    normalize_name("VC Wiesbaden"): "Wiesbaden",
    normalize_name("VfB Suhl LOTTO Thüringen"): "Suhl",
}


def _build_team_short_name_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = dict(TEAM_SHORT_NAMES)
    for canonical, synonyms in TEAM_KEYWORD_SYNONYMS.items():
        short = TEAM_SHORT_NAMES.get(canonical)
        if not short:
            continue
        for alias in synonyms:
            lookup[normalize_name(alias)] = short
    return lookup


TEAM_SHORT_NAME_LOOKUP = _build_team_short_name_lookup()


TEAM_CANONICAL_NAMES: Mapping[str, str] = {
    normalize_name("Allianz MTV Stuttgart"): "Allianz MTV Stuttgart",
    normalize_name("Binder Blaubären TSV Flacht"): "Binder Blaubären TSV Flacht",
    normalize_name("Dresdner SC"): "Dresdner SC",
    normalize_name("ETV Hamburger Volksbank Volleys"): "ETV Hamburger Volksbank Volleys",
    normalize_name("Ladies in Black Aachen"): "Ladies in Black Aachen",
    normalize_name("SSC Palmberg Schwerin"): "SSC Palmberg Schwerin",
    normalize_name("Schwarz-Weiß Erfurt"): "Schwarz-Weiß Erfurt",
    normalize_name("Skurios Volleys Borken"): "Skurios Volleys Borken",
    normalize_name("USC Münster"): USC_CANONICAL_NAME,
    normalize_name("VC Wiesbaden"): "VC Wiesbaden",
    normalize_name("VfB Suhl LOTTO Thüringen"): "VfB Suhl LOTTO Thüringen",
}


def _build_team_canonical_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = dict(TEAM_CANONICAL_NAMES)
    for normalized_name, synonyms in TEAM_KEYWORD_SYNONYMS.items():
        canonical = TEAM_CANONICAL_NAMES.get(normalized_name)
        if not canonical:
            continue
        for alias in synonyms:
            lookup[normalize_name(alias)] = canonical
    for normalized_name, short_label in TEAM_SHORT_NAMES.items():
        canonical = TEAM_CANONICAL_NAMES.get(normalized_name)
        if not canonical:
            continue
        lookup[normalize_name(short_label)] = canonical
    return lookup


TEAM_CANONICAL_LOOKUP = _build_team_canonical_lookup()


def get_team_keywords(team_name: str) -> KeywordSet:
    synonyms = TEAM_KEYWORD_SYNONYMS.get(normalize_name(team_name), ())
    return build_keywords(team_name, *synonyms)


def _build_team_news_config() -> Dict[str, Dict[str, str]]:
    return {
        normalize_name(USC_CANONICAL_NAME): {
            "type": "rss",
            "url": "https://www.usc-muenster.de/feed/",
            "label": "Homepage USC Münster",
        },
        normalize_name("ETV Hamburger Volksbank Volleys"): {
            "type": "etv",
            "url": "https://www.etv-hamburg.de/de/etv-hamburger-volksbank-volleys/",
            "label": "Homepage ETV Hamburger Volksbank Volleys",
        },
    }


TEAM_NEWS_CONFIG = _build_team_news_config()


def _deduplicate_news(items: Sequence[NewsItem]) -> List[NewsItem]:
    seen: set[str] = set()
    deduped: List[NewsItem] = []
    for item in items:
        key = item.url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_by_keywords(items: Sequence[NewsItem], keyword_set: KeywordSet) -> List[NewsItem]:
    return [
        item
        for item in items
        if matches_keywords(item.search_text or item.title, keyword_set)
    ]


def _extract_best_candidate(soup: BeautifulSoup) -> Optional[str]:
    best_text = ""
    for element in soup.find_all(["article", "section", "div", "main"], limit=200):
        text = element.get_text(" ", strip=True)
        if len(text) > len(best_text):
            best_text = text
    if not best_text and soup.body:
        best_text = soup.body.get_text(" ", strip=True)
    return best_text or None


def extract_article_text(url: str) -> Optional[str]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()

    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()

    prioritized_selectors: List[str] = []
    if "volleyball-bundesliga.de" in hostname:
        prioritized_selectors.extend(
            [
                ".samsCmsComponentContent",
                ".samsArticleBody",
                "article",
            ]
        )
    elif "usc-muenster.de" in hostname:
        prioritized_selectors.extend([
            "article",
            "div.entry-content",
        ])
    elif "etv-hamburg" in hostname:
        prioritized_selectors.extend([
            "div.article",
            "div.text-wrapper",
        ])

    for selector in prioritized_selectors:
        candidate = soup.select_one(selector)
        if candidate:
            text = candidate.get_text(" ", strip=True)
            if len(text) >= 80:
                return text

    return _extract_best_candidate(soup)


def collect_instagram_links(team_name: str, *, limit: int = 6) -> List[str]:
    links: List[str] = []
    base = get_team_instagram(team_name)
    base_slug: Optional[str] = None
    if base:
        normalized_base = base.rstrip("/")
        links.append(normalized_base)
        base_path = urlparse(normalized_base).path.strip("/")
        if base_path:
            base_slug = base_path

    query = f"{team_name} instagram"
    try:
        html = fetch_html(
            INSTAGRAM_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": REQUEST_HEADERS["User-Agent"]},
        )
    except requests.RequestException:
        return links

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "instagram.com" not in href:
            continue
        target = href
        if href.startswith("//"):
            parsed = urlparse("https:" + href)
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                target = uddg
        if "instagram.com" not in target:
            continue
        normalized = target.split("?")[0].rstrip("/")
        if not normalized or normalized in links:
            continue
        parsed = urlparse(normalized)
        path = parsed.path.strip("/")
        if not path:
            continue
        if base_slug:
            if path != base_slug and not path.startswith(f"{base_slug}/"):
                if not (path.startswith("p/") or path.startswith("reel/")):
                    continue
        else:
            keywords = get_team_keywords(team_name)
            if not matches_keywords(path, keywords):
                continue
        links.append(normalized)
        if len(links) >= limit:
            break

    return links


def _within_lookback(published: Optional[datetime], *, reference: datetime, lookback_days: int) -> bool:
    if not published:
        return False
    cutoff = reference - timedelta(days=lookback_days)
    return published >= cutoff


def _fetch_rss_news(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        rss_text = fetch_rss(url)
    except requests.RequestException:
        return []

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError:
        return []

    items: List[NewsItem] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date_raw = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        published: Optional[datetime] = None
        if pub_date_raw:
            try:
                parsed = parsedate_to_datetime(pub_date_raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=BERLIN_TZ)
                published = parsed.astimezone(BERLIN_TZ)
            except (TypeError, ValueError):
                published = None
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        search_text = f"{title} {description}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def _fetch_etv_news(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[NewsItem] = []
    seen_ids: set[str] = set()
    for block in soup.select("div[id^=news-]"):
        block_id = block.get("id") or ""
        if block_id in seen_ids:
            continue
        seen_ids.add(block_id)
        date_elem = block.select_one(".newsDate .date")
        title_elem = block.select_one(".headline2")
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)
        if not title:
            continue
        link_elem = title_elem.find("a")
        if link_elem and link_elem.has_attr("href"):
            href = link_elem["href"]
            link = urljoin(url, href)
        else:
            link = f"{url.rstrip('/') }#{block_id}"
        date_text = date_elem.get_text(strip=True) if date_elem else ""
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        summary_elem = block.select_one(".text-wrapper")
        summary = summary_elem.get_text(" ", strip=True) if summary_elem else ""
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=f"{title} {summary}",
            )
        )
    return _deduplicate_news(items)


def _fetch_vbl_articles(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[NewsItem] = []
    for article in soup.select("div.samsArticle"):
        header_link = article.select_one(".samsArticleHeader a")
        if not header_link or not header_link.has_attr("href"):
            continue
        title = header_link.get_text(strip=True)
        if not title:
            continue
        link = urljoin(url, header_link["href"])
        info = article.select_one(".samsArticleInfo")
        date_text = info.get_text(strip=True) if info else ""
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        summary_elem = article.select_one(".samsCmsComponentContent")
        summary = summary_elem.get_text(" ", strip=True) if summary_elem else ""
        category = article.select_one(".samsArticleCategory")
        category_text = category.get_text(" ", strip=True) if category else ""
        search_text = f"{title} {summary} {category_text}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def _fetch_vbl_press(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.samsDataTable tbody tr")
    items: List[NewsItem] = []
    for row in rows:
        columns = row.find_all("td")
        if len(columns) < 3:
            continue
        link_elem = columns[0].find("a")
        source_elem = columns[1].get_text(strip=True)
        date_text = columns[2].get_text(strip=True)
        if not link_elem or not link_elem.has_attr("href"):
            continue
        title = link_elem.get_text(strip=True)
        if not title:
            continue
        link = link_elem["href"]
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        search_text = f"{title} {source_elem}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=f"{source_elem} via VBL Pressespiegel",
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def fetch_team_news(
    team_name: str,
    *,
    now: Optional[datetime] = None,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> List[NewsItem]:
    config = TEAM_NEWS_CONFIG.get(normalize_name(team_name))
    if not config:
        return []
    now = now or datetime.now(tz=BERLIN_TZ)
    label = config.get("label", team_name)
    fetch_type = config.get("type")
    url = config.get("url", "")
    if not url:
        return []
    if fetch_type == "rss":
        return _fetch_rss_news(url, label=label, now=now, lookback_days=lookback_days)
    if fetch_type == "etv":
        return _fetch_etv_news(url, label=label, now=now, lookback_days=lookback_days)
    return []


def collect_team_news(
    next_home: Match,
    *,
    now: Optional[datetime] = None,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> Tuple[List[NewsItem], List[NewsItem]]:
    now = now or datetime.now(tz=BERLIN_TZ)
    usc_news = fetch_team_news(USC_CANONICAL_NAME, now=now, lookback_days=lookback_days)
    opponent_news = fetch_team_news(next_home.away_team, now=now, lookback_days=lookback_days)

    vbl_articles = _fetch_vbl_articles(
        VBL_NEWS_URL,
        label="Volleyball Bundesliga",
        now=now,
        lookback_days=lookback_days,
    )
    vbl_press = _fetch_vbl_press(
        VBL_PRESS_URL,
        label="Volleyball Bundesliga",
        now=now,
        lookback_days=lookback_days,
    )

    combined_vbl = _deduplicate_news(vbl_articles + vbl_press)

    usc_keywords = get_team_keywords(USC_CANONICAL_NAME)
    opponent_keywords = get_team_keywords(next_home.away_team)

    usc_vbl = _filter_by_keywords(combined_vbl, usc_keywords)
    opponent_vbl = _filter_by_keywords(combined_vbl, opponent_keywords)

    usc_combined = _deduplicate_news([*usc_news, *usc_vbl])
    opponent_combined = _deduplicate_news([*opponent_news, *opponent_vbl])

    return usc_combined, opponent_combined


def _parse_transfer_table(table: "BeautifulSoup") -> List[TransferItem]:
    rows = table.find_all("tr")
    items: List[TransferItem] = []
    current_category: Optional[str] = None
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            headers = row.find_all("th")
            if headers:
                label = headers[0].get_text(strip=True)
                if label:
                    current_category = label
            continue
        texts = [cell.get_text(strip=True) for cell in cells]
        if not any(texts):
            continue
        first = texts[0]
        parsed_date = parse_date_label(first)
        if not parsed_date and not DATE_PATTERN.match(first):
            label = first or None
            if label:
                current_category = label
            continue
        name_cell = cells[2] if len(cells) > 2 else None
        name = name_cell.get_text(strip=True) if name_cell else ""
        if not name:
            continue
        link = None
        if name_cell:
            anchor = name_cell.find("a")
            if anchor and anchor.has_attr("href"):
                link = urljoin(WECHSELBOERSE_URL, anchor["href"])
        type_code = texts[1] if len(texts) > 1 else ""
        nationality = texts[3] if len(texts) > 3 else ""
        info = texts[4] if len(texts) > 4 else ""
        related = texts[5] if len(texts) > 5 else ""
        items.append(
            TransferItem(
                date=parsed_date,
                date_label=first,
                category=current_category,
                type_code=type_code,
                name=name,
                url=link,
                nationality=nationality,
                info=info,
                related_club=related,
            )
        )
    return items


_TRANSFER_CACHE: Optional[Dict[str, List[TransferItem]]] = None


def _load_transfer_cache() -> Dict[str, List[TransferItem]]:
    global _TRANSFER_CACHE
    if _TRANSFER_CACHE is not None:
        return _TRANSFER_CACHE
    try:
        html = fetch_html(WECHSELBOERSE_URL, headers=REQUEST_HEADERS)
    except requests.RequestException:
        _TRANSFER_CACHE = {}
        return _TRANSFER_CACHE
    soup = BeautifulSoup(html, "html.parser")
    mapping: Dict[str, List[TransferItem]] = {}
    for heading in soup.find_all("h2"):
        team_name = heading.get_text(strip=True)
        if not team_name:
            continue
        collected: List[TransferItem] = []
        sibling = heading.next_sibling
        while sibling:
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
                    break
                if sibling.name == "table":
                    collected.extend(_parse_transfer_table(sibling))
            sibling = sibling.next_sibling
        if collected:
            mapping[normalize_name(team_name)] = collected
    _TRANSFER_CACHE = mapping
    return mapping


def collect_team_transfers(team_name: str) -> List[TransferItem]:
    cache = _load_transfer_cache()
    return list(cache.get(normalize_name(team_name), ()))


_STATS_TOTALS_CACHE: Dict[str, Tuple[MatchStatsTotals, ...]] = {}


def _normalize_stats_header_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    if "Satz" in stripped:
        stripped = stripped[stripped.index("Satz") :]
    return re.sub(r"\s+", " ", stripped)


def _normalize_stats_totals_line(line: str) -> str:
    stripped = re.sub(r"-\s+", "-", line.strip())
    stripped = re.sub(r"\(\s*", "(", stripped)
    stripped = re.sub(r"\s*\)", ")", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    stripped = re.sub(r"(\d+\+\d{1,2})(\d+)", r"\1 \2", stripped)
    stripped = stripped.replace("%(", "% (")
    stripped = re.sub(r"%(?=\d)", "% ", stripped)
    return stripped


_MATCH_STATS_LINE_PATTERN = re.compile(
    r"(?P<serve_attempts>\d+)\s+"
    r"(?P<serve_combo>\d+)\s+"
    r"(?P<reception_attempts>\d+)\s+"
    r"(?P<reception_errors>\d+)\s+"
    r"(?P<reception_pos>\d+%)\s+\("
    r"(?P<reception_perf>\d+%)\)\s+"
    r"(?P<attack_attempts>\d+)\s+"
    r"(?P<attack_errors>\d+)\s+"
    r"(?P<attack_combo>\d+)\s+"
    r"(?P<attack_pct>\d+%)\s+"
    r"(?P<block_points>\d+)"
)

_TOTALS_LABEL_PATTERN = re.compile(
    r"\b(Aufschlag|Annahme|Angriff|Block|Punkte)\b",
    re.IGNORECASE,
)


def _split_compound_value(
    value: str,
    *,
    first_max: int,
    second_max: int,
) -> Optional[Tuple[int, int]]:
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return None
    max_second_len = min(3, len(digits))
    for second_len in range(1, max_second_len + 1):
        first_digits = digits[:-second_len]
        second_digits = digits[-second_len:]
        if not second_digits:
            continue
        first_value = int(first_digits) if first_digits else 0
        second_value = int(second_digits)
        if first_value <= first_max and second_value <= second_max:
            return first_value, second_value
    return None


def _parse_match_stats_metrics(line: str) -> Optional[MatchStatsMetrics]:
    normalized_line = _normalize_stats_totals_line(line)
    normalized_line = _TOTALS_LABEL_PATTERN.sub(" ", normalized_line)
    compact_result = _extract_compact_value_tokens(
        _tokenize_compact_stats_text(normalized_line)
    )
    if compact_result:
        tokens, _ = compact_result
        return _build_metrics_from_compact_tokens(tokens)
    match = _MATCH_STATS_LINE_PATTERN.search(normalized_line)
    if not match:
        tokens = re.findall(r"\d+%|\d+\+\d+|\d+", normalized_line)
        if len(tokens) > 13 and "+" in tokens[1]:
            prefix, suffix = tokens[1].split("+", 1)
            if suffix.isdigit() and len(suffix) == 1 and tokens[2].isdigit():
                tokens[1] = f"{tokens[1]}{tokens[2]}"
                tokens.pop(2)
        if len(tokens) < 13 or "+" not in tokens[1]:
            return None
        serve_split = _split_compound_value(tokens[3], first_max=60, second_max=60)
        attack_split = _split_compound_value(tokens[10], first_max=40, second_max=150)
        if not serve_split or not attack_split:
            return None
        try:
            reception_attempts = int(tokens[4])
            reception_positive_pct = tokens[6]
            reception_perfect_pct = tokens[7]
            reception_positive = _compute_percentage_count(
                reception_attempts, reception_positive_pct
            )
            reception_perfect = _compute_percentage_count(
                reception_attempts, reception_perfect_pct
            )
            return MatchStatsMetrics(
                serves_attempts=int(tokens[2]),
                serves_errors=serve_split[0],
                serves_points=serve_split[1],
                receptions_attempts=reception_attempts,
                receptions_errors=int(tokens[5]),
                receptions_positive_pct=reception_positive_pct,
                receptions_perfect_pct=reception_perfect_pct,
                attacks_attempts=int(tokens[8]),
                attacks_errors=int(tokens[9]),
                attacks_blocked=attack_split[0],
                attacks_points=attack_split[1],
                attacks_success_pct=tokens[11],
                blocks_points=int(tokens[12]),
                receptions_positive=reception_positive,
                receptions_perfect=reception_perfect,
            )
        except ValueError:
            return None
    groups = match.groupdict()
    serve_split = _split_compound_value(
        groups["serve_combo"], first_max=150, second_max=60
    )
    attack_split = _split_compound_value(
        groups["attack_combo"], first_max=60, second_max=150
    )
    if not serve_split or not attack_split:
        return None
    serves_errors, serves_points = serve_split
    attacks_blocked, attacks_points = attack_split
    try:
        reception_attempts = int(groups["reception_attempts"])
        reception_positive_pct = groups["reception_pos"]
        reception_perfect_pct = groups["reception_perf"]
        reception_positive = _compute_percentage_count(
            reception_attempts, reception_positive_pct
        )
        reception_perfect = _compute_percentage_count(
            reception_attempts, reception_perfect_pct
        )
        return MatchStatsMetrics(
            serves_attempts=int(groups["serve_attempts"]),
            serves_errors=serves_errors,
            serves_points=serves_points,
            receptions_attempts=reception_attempts,
            receptions_errors=int(groups["reception_errors"]),
            receptions_positive_pct=reception_positive_pct,
            receptions_perfect_pct=reception_perfect_pct,
            attacks_attempts=int(groups["attack_attempts"]),
            attacks_errors=int(groups["attack_errors"]),
            attacks_blocked=attacks_blocked,
            attacks_points=attacks_points,
            attacks_success_pct=groups["attack_pct"],
            blocks_points=int(groups["block_points"]),
            receptions_positive=reception_positive,
            receptions_perfect=reception_perfect,
        )
    except ValueError:
        return None


def resolve_match_stats_metrics(entry: MatchStatsTotals) -> Optional[MatchStatsMetrics]:
    """Return structured statistics for a ``MatchStatsTotals`` entry.

    The PDF-Auswertungen der VBL liefern die Gesamtwerte in einer einzigen
    Textzeile. Für manche Spiele liegen die bereits als ``MatchStatsMetrics``
    im ``metrics``-Attribut vor (z. B. aus manuellen Korrekturen). Falls nicht,
    wird die Zahlenzeile erneut mit ``_parse_match_stats_metrics`` analysiert.
    """

    if entry.metrics is not None:
        return entry.metrics
    if not entry.totals_line:
        return None
    return _parse_match_stats_metrics(entry.totals_line)


_PLAYER_VALUE_PATTERN = re.compile(r"-?\d{1,4}(?:[.,]\d+)?%?|-")
_COMPACT_VALUE_PATTERN = re.compile(r"^(?:[+\-\u2212]?\d+(?:[.,]\d+)?%?|\.)$")


def _tokenize_compact_stats_text(text: str) -> List[str]:
    sanitized = text.replace("\u00a0", " ")
    sanitized = sanitized.replace("·", " ")
    sanitized = sanitized.replace("\u2212", "-")
    sanitized = re.sub(r"[()]+", " ", sanitized)
    parts = [part for part in sanitized.split() if part and part != "*"]
    return parts


def _extract_compact_value_tokens(parts: Sequence[str]) -> Optional[Tuple[List[str], int]]:
    values: List[str] = []
    consumed = 0
    for token in reversed(parts):
        if not token:
            continue
        normalized = token.strip()
        if _COMPACT_VALUE_PATTERN.match(normalized):
            values.append(normalized)
            consumed += 1
            if len(values) == 16:
                break
        elif values:
            break
    if not values:
        return None
    values.reverse()
    if len(values) < 16:
        values.extend(["."] * (16 - len(values)))
    return values, consumed


def _build_metrics_from_compact_tokens(tokens: Sequence[str]) -> MatchStatsMetrics:
    serves_attempts = _parse_int_token(tokens[3])
    serves_errors = _parse_int_token(tokens[4])
    serves_points = _parse_int_token(tokens[5])
    receptions_attempts = _parse_int_token(tokens[6])
    receptions_errors = _parse_int_token(tokens[7])
    receptions_positive_pct = _parse_percentage_token(tokens[8])
    receptions_perfect_pct = _parse_percentage_token(tokens[9])
    receptions_positive = _compute_percentage_count(
        receptions_attempts, receptions_positive_pct
    )
    receptions_perfect = _compute_percentage_count(
        receptions_attempts, receptions_perfect_pct
    )
    attacks_attempts = _parse_int_token(tokens[10])
    attacks_errors = _parse_int_token(tokens[11])
    attacks_blocked = _parse_int_token(tokens[12])
    attacks_points = _parse_int_token(tokens[13])
    attacks_success_pct = _parse_percentage_token(tokens[14])
    blocks_points = _parse_int_token(tokens[15])

    return MatchStatsMetrics(
        serves_attempts=serves_attempts,
        serves_errors=serves_errors,
        serves_points=serves_points,
        receptions_attempts=receptions_attempts,
        receptions_errors=receptions_errors,
        receptions_positive_pct=receptions_positive_pct,
        receptions_perfect_pct=receptions_perfect_pct,
        receptions_positive=receptions_positive,
        receptions_perfect=receptions_perfect,
        attacks_attempts=attacks_attempts,
        attacks_errors=attacks_errors,
        attacks_blocked=attacks_blocked,
        attacks_points=attacks_points,
        attacks_success_pct=attacks_success_pct,
        blocks_points=blocks_points,
    )


def _parse_compact_player_stats(
    rest: str, team_name: str, jersey_number: Optional[int]
) -> Optional[MatchPlayerStats]:
    parts = _tokenize_compact_stats_text(rest)
    extracted = _extract_compact_value_tokens(parts)
    if not extracted:
        return None
    value_tokens, consumed_count = extracted
    metrics = _build_metrics_from_compact_tokens(value_tokens)
    prefix_length = len(parts) - consumed_count
    name_tokens = parts[:prefix_length]
    if not name_tokens:
        return None
    pre_str = " ".join(name_tokens).strip()
    cutoff = re.search(r"\s[.\d+-]", pre_str)
    if cutoff:
        name_segment = pre_str[: cutoff.start()].strip(" .:-")
    else:
        name_segment = pre_str.strip(" .:-")
    if not name_segment:
        return None
    cleaned_parts = [
        part
        for part in name_segment.split()
        if not (len(part) == 1 and part.isalpha() and part.isupper())
    ]
    if cleaned_parts:
        name_segment = " ".join(cleaned_parts)
    player_name = pretty_name(name_segment)
    total_points = _parse_int_token(value_tokens[0])
    break_points = _parse_int_token(value_tokens[1])
    plus_minus = _parse_int_token(value_tokens[2])
    return MatchPlayerStats(
        team_name=team_name,
        player_name=player_name,
        jersey_number=jersey_number,
        metrics=metrics,
        total_points=total_points,
        break_points=break_points,
        plus_minus=plus_minus,
    )


def _parse_int_token(token: str) -> int:
    stripped = token.strip().replace("\u00a0", "")
    if not stripped or stripped in {"-", "–"}:
        return 0
    cleaned = stripped.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_optional_int_token(token: str) -> Optional[int]:
    stripped = token.strip().replace("\u00a0", "")
    if not stripped or stripped in {"-", "–"}:
        return None
    cleaned = stripped.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_percentage_token(token: str) -> str:
    stripped = token.strip().replace("\u00a0", "")
    if not stripped or stripped in {"-", "–"}:
        return "0%"
    normalized = stripped.replace("%", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return "0%"
    return f"{int(round(value))}%"


def _compute_percentage_count(attempts: int, pct: str) -> int:
    if attempts <= 0:
        return 0
    cleaned = pct.strip()
    if not cleaned:
        return 0
    numeric = cleaned.replace("%", "").replace(",", ".")
    try:
        value = float(numeric)
    except ValueError:
        return 0
    return int(round(attempts * (value / 100)))


def _parse_player_stats_line(line: str, team_name: str) -> Optional[MatchPlayerStats]:
    cleaned = line.replace("\u00a0", " ").strip()
    if not cleaned:
        return None
    if cleaned.lower().startswith(("trainer", "team", "coaches")):
        return None
    jersey_match = re.match(r"^\s*(\d{1,3})", cleaned)
    jersey_number: Optional[int]
    name_segment: str
    rest: str
    if jersey_match:
        try:
            jersey_number = int(jersey_match.group(1))
        except ValueError:
            jersey_number = None
        rest = cleaned[jersey_match.end() :].strip()
    else:
        jersey_number = None
        rest = cleaned
    if not rest:
        return None
    compact_parsed = _parse_compact_player_stats(rest, team_name, jersey_number)
    if compact_parsed is not None:
        return compact_parsed
    value_matches = list(_PLAYER_VALUE_PATTERN.finditer(rest))
    if len(value_matches) < 13:
        return None
    first_value = value_matches[0]
    name_segment = rest[: first_value.start()].strip(" .:-")
    if not name_segment:
        return None
    player_name = pretty_name(name_segment)
    numeric_tokens = [match.group(0) for match in value_matches]
    metrics_count = 13
    metrics_tokens = numeric_tokens[:metrics_count]
    extra_tokens = numeric_tokens[metrics_count:]
    try:
        serves_attempts = _parse_int_token(metrics_tokens[0])
        serves_errors = _parse_int_token(metrics_tokens[1])
        serves_points = _parse_int_token(metrics_tokens[2])
        receptions_attempts = _parse_int_token(metrics_tokens[3])
        receptions_errors = _parse_int_token(metrics_tokens[4])
        receptions_positive_pct = _parse_percentage_token(metrics_tokens[5])
        receptions_perfect_pct = _parse_percentage_token(metrics_tokens[6])
        receptions_positive = _compute_percentage_count(
            receptions_attempts, receptions_positive_pct
        )
        receptions_perfect = _compute_percentage_count(
            receptions_attempts, receptions_perfect_pct
        )
        attacks_attempts = _parse_int_token(metrics_tokens[7])
        attacks_errors = _parse_int_token(metrics_tokens[8])
        attacks_blocked = _parse_int_token(metrics_tokens[9])
        attacks_points = _parse_int_token(metrics_tokens[10])
        attacks_success_pct = _parse_percentage_token(metrics_tokens[11])
        blocks_points = _parse_int_token(metrics_tokens[12])
    except (IndexError, ValueError):
        return None
    metrics = MatchStatsMetrics(
        serves_attempts=serves_attempts,
        serves_errors=serves_errors,
        serves_points=serves_points,
        receptions_attempts=receptions_attempts,
        receptions_errors=receptions_errors,
        receptions_positive_pct=receptions_positive_pct,
        receptions_perfect_pct=receptions_perfect_pct,
        receptions_positive=receptions_positive,
        receptions_perfect=receptions_perfect,
        attacks_attempts=attacks_attempts,
        attacks_errors=attacks_errors,
        attacks_blocked=attacks_blocked,
        attacks_points=attacks_points,
        attacks_success_pct=attacks_success_pct,
        blocks_points=blocks_points,
    )
    total_points = None
    if extra_tokens:
        total_points = _parse_optional_int_token(extra_tokens[0])
    break_points = None
    plus_minus = None
    if len(extra_tokens) > 1:
        break_points = _parse_optional_int_token(extra_tokens[1])
    if len(extra_tokens) > 2:
        plus_minus = _parse_optional_int_token(extra_tokens[2])
    return MatchPlayerStats(
        team_name=team_name,
        player_name=player_name,
        jersey_number=jersey_number,
        metrics=metrics,
        total_points=total_points,
        break_points=break_points,
        plus_minus=plus_minus,
    )


def _parse_team_player_lines(
    lines: Sequence[str], team_name: str
) -> List[MatchPlayerStats]:
    """Parse player lines for a single team from a stats PDF.

    Newer VBL PDFs sometimes wrap a player row across multiple lines. The
    legacy implementation expected all values to be present on a single line,
    which caused us to silently drop the affected players. We now keep track of
    partially parsed lines and merge them with following lines until the
    statistics can be parsed successfully.
    """

    players: List[MatchPlayerStats] = []
    pending: Optional[str] = None

    def try_parse(text: str) -> Optional[MatchPlayerStats]:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return None
        return _parse_player_stats_line(normalized, team_name)

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if re.match(r"(?i)^nr\b", stripped):
            pending = None
            continue
        if ("aufschlag" in lowered and "annahme" in lowered) or (
            "angriff" in lowered and "block" in lowered
        ):
            pending = None
            continue
        if stripped.lower().startswith("libero"):
            pending = None
            continue

        if pending is not None:
            combined = f"{pending} {stripped}"
            parsed = try_parse(combined)
            if parsed is not None:
                players.append(parsed)
                pending = None
                continue
            parsed = try_parse(stripped)
            if parsed is not None:
                players.append(parsed)
                pending = None
                continue
            if re.search(r"\d", stripped):
                pending = combined
            else:
                pending = stripped
            continue

        parsed = try_parse(stripped)
        if parsed is not None:
            players.append(parsed)
            pending = None
            continue
        pending = stripped

    if pending is not None:
        parsed = try_parse(pending)
        if parsed is not None:
            players.append(parsed)

    return players


def _extract_stats_team_names(lines: Sequence[str]) -> List[str]:
    names: List[str] = []
    team_pattern = re.compile(r"(?:Spielbericht\s+)?(.+?)\s+\d+\s*$")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = team_pattern.match(stripped)
        if not match:
            continue
        candidate = match.group(1).strip()
        if not candidate or candidate.lower() == "spielbericht":
            continue
        names.append(candidate)
        if len(names) >= 2:
            break
    return names


def _parse_stats_totals_pdf(data: bytes) -> Tuple[MatchStatsTotals, ...]:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError:
        return ()
    except Exception:
        return ()
    if not reader.pages:
        return ()
    raw_text = reader.pages[0].extract_text() or ""
    cleaned = raw_text.replace("\x00", "")
    lines = cleaned.splitlines()
    if not lines:
        return ()
    markers = [idx for idx, line in enumerate(lines) if line.strip() == "Spieler insgesamt"]
    if not markers:
        return ()
    team_names = _extract_stats_team_names(lines)
    summaries: List[MatchStatsTotals] = []
    for marker_index, marker in enumerate(markers):
        header_entries: List[Tuple[int, str]] = []
        cursor = marker - 1
        while cursor >= 0 and len(header_entries) < 6:
            candidate_raw = lines[cursor]
            candidate = candidate_raw.strip()
            if candidate:
                header_entries.append((cursor, _normalize_stats_header_line(candidate)))
            cursor -= 1
        header_entries.reverse()
        header_lines = [entry[1] for entry in header_entries]
        totals_candidates: List[str] = []
        for probe in range(marker + 1, len(lines)):
            candidate = lines[probe].strip()
            if not candidate:
                if totals_candidates:
                    break
                continue
            if candidate.startswith("Satz"):
                break
            if "Spieler insgesamt" in candidate:
                break
            if not re.search(r"\d", candidate):
                if totals_candidates:
                    break
                continue
            totals_candidates.append(candidate)
            # Continue collecting lines in case the totals are split across multiple rows.
        if not totals_candidates:
            continue
        points_lines = [
            entry
            for entry in totals_candidates
            if re.search(r"\bPunkte\b", entry, re.IGNORECASE)
        ]
        other_lines = [
            entry
            for entry in totals_candidates
            if entry not in points_lines
        ]
        ordered_totals = points_lines + other_lines if points_lines else totals_candidates
        totals_line = " ".join(ordered_totals)
        normalized_totals = _normalize_stats_totals_line(totals_line)
        team_name = (
            team_names[marker_index]
            if marker_index < len(team_names)
            else f"Team {marker_index + 1}"
        )
        player_lines: List[str] = []
        start_index = header_entries[-1][0] + 1 if header_entries else 0
        for idx in range(start_index, marker):
            raw_line = lines[idx].strip()
            if not raw_line or raw_line.lower().startswith("libero"):
                continue
            player_lines.append(lines[idx])
        players = _parse_team_player_lines(player_lines, team_name)
        summaries.append(
            MatchStatsTotals(
                team_name=team_name,
                header_lines=tuple(header_lines),
                totals_line=normalized_totals,
                players=tuple(players),
            )
        )
    return tuple(summaries)


def fetch_match_stats_totals(
    stats_url: str,
    *,
    retries: int = 3,
    delay_seconds: float = 2.0,
) -> Tuple[MatchStatsTotals, ...]:
    cached = _STATS_TOTALS_CACHE.get(stats_url)
    if cached is not None:
        return cached
    manual_entries = _load_manual_stats_totals().get(stats_url)
    try:
        response = _http_get(
            stats_url,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except requests.RequestException:
        if manual_entries:
            summaries = tuple(
                MatchStatsTotals(
                    team_name=team_name,
                    header_lines=(),
                    totals_line="",
                    metrics=metrics,
                    players=players,
                )
                for _, team_name, metrics, players in manual_entries
            )
            _STATS_TOTALS_CACHE[stats_url] = summaries
            return summaries
        _STATS_TOTALS_CACHE[stats_url] = ()
        return ()
    summaries = list(_parse_stats_totals_pdf(response.content))
    if manual_entries:
        index_lookup: Dict[str, int] = {}
        for idx, (keys, _, _, _) in enumerate(manual_entries):
            for key in keys:
                index_lookup[key] = idx
        updated: List[MatchStatsTotals] = []
        matched_indices: set[int] = set()
        for entry in summaries:
            normalized_team = normalize_name(entry.team_name)
            match_idx = index_lookup.get(normalized_team)
            if match_idx is not None:
                matched_indices.add(match_idx)
                _, _, metrics, players = manual_entries[match_idx]
                updated.append(
                    MatchStatsTotals(
                        team_name=entry.team_name,
                        header_lines=entry.header_lines,
                        totals_line=entry.totals_line,
                        metrics=metrics,
                        players=players or entry.players,
                    )
                )
            else:
                updated.append(entry)
        for idx, (_keys, team_name, metrics, players) in enumerate(manual_entries):
            if idx in matched_indices:
                continue
            updated.append(
                MatchStatsTotals(
                    team_name=team_name,
                    header_lines=(),
                    totals_line="",
                    metrics=metrics,
                    players=players,
                )
            )
        summaries = updated
    summaries_tuple = tuple(summaries)
    _STATS_TOTALS_CACHE[stats_url] = summaries_tuple
    return summaries_tuple


def collect_match_stats_totals(
    matches: Iterable[Match],
) -> Dict[str, Tuple[MatchStatsTotals, ...]]:
    collected: Dict[str, Tuple[MatchStatsTotals, ...]] = {}
    for match in matches:
        if not match.is_finished or not match.stats_url:
            continue
        stats_url = match.stats_url
        if stats_url in collected:
            continue
        summaries = fetch_match_stats_totals(stats_url)
        if summaries:
            collected[stats_url] = summaries
    return collected


def pretty_name(name: str) -> str:
    if is_usc(name):
        return USC_CANONICAL_NAME
    canonical = TEAM_CANONICAL_LOOKUP.get(normalize_name(name))
    if canonical:
        return canonical
    return (
        name.replace("Mnster", "Münster")
        .replace("Munster", "Münster")
        .replace("Thringen", "Thüringen")
        .replace("Wei", "Weiß")
        .replace("wei", "weiß")
    )


def get_team_short_label(name: str) -> str:
    normalized = normalize_name(name)
    short = TEAM_SHORT_NAME_LOOKUP.get(normalized)
    if short:
        return short
    return pretty_name(name)


def find_next_usc_home_match(matches: Iterable[Match], *, reference: Optional[datetime] = None) -> Optional[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    future_home_games = [
        match
        for match in matches
        if is_usc(match.host) and match.kickoff >= now
    ]
    future_home_games.sort(key=lambda match: match.kickoff)
    return future_home_games[0] if future_home_games else None


def find_last_matches_for_team(
    matches: Iterable[Match],
    team_name: str,
    *,
    limit: int,
    reference: Optional[datetime] = None,
) -> List[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    relevant = [
        match
        for match in matches
        if match.is_finished and match.kickoff < now and team_in_match(team_name, match)
    ]
    relevant.sort(key=lambda match: match.kickoff, reverse=True)
    return relevant[:limit]


def find_next_match_for_team(
    matches: Iterable[Match],
    team_name: str,
    *,
    reference: Optional[datetime] = None,
) -> Optional[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    upcoming = [
        match
        for match in matches
        if match.kickoff >= now and team_in_match(team_name, match)
    ]
    upcoming.sort(key=lambda match: match.kickoff)
    return upcoming[0] if upcoming else None


def team_in_match(team_name: str, match: Match) -> bool:
    return is_same_team(team_name, match.home_team) or is_same_team(team_name, match.away_team)


def is_same_team(a: str, b: str) -> bool:
    return normalize_name(a) == normalize_name(b)


GERMAN_WEEKDAYS = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}

GERMAN_WEEKDAYS_LONG = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag",
}

GERMAN_MONTHS = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


def format_generation_timestamp(value: datetime) -> str:
    localized = value.astimezone(BERLIN_TZ)
    weekday = GERMAN_WEEKDAYS_LONG.get(localized.weekday(), localized.strftime("%A"))
    month = GERMAN_MONTHS.get(localized.month, localized.strftime("%B"))
    day = localized.day
    time_label = localized.strftime("%H:%M")
    return f"{weekday}, {day:02d}. {month} {localized.year} um {time_label}"


def format_match_line(
    match: Match,
    *,
    stats: Optional[Sequence[MatchStatsTotals]] = None,
    highlight_teams: Optional[Mapping[str, str]] = None,
) -> str:
    kickoff_local = match.kickoff.astimezone(BERLIN_TZ)
    date_label = kickoff_local.strftime("%d.%m.%Y")
    weekday = GERMAN_WEEKDAYS.get(kickoff_local.weekday(), kickoff_local.strftime("%a"))
    time_label = kickoff_local.strftime("%H:%M")
    kickoff_label = f"{date_label} ({weekday}) {time_label} Uhr"
    home = pretty_name(match.home_team)
    away = pretty_name(match.away_team)
    result = match.result.summary if match.result else "-"
    teams = f"{home} vs. {away}"
    result_block = ""
    if match.is_finished:
        result_block = f"<div class=\"match-result\">Ergebnis: {escape(result)}</div>"
    extras: List[str] = []
    if match.referees and not match.is_finished:
        referee_label = ", ".join(escape(referee) for referee in match.referees)
        extras.append(f"<span>Schiedsrichter: {referee_label}</span>")
    if match.attendance and match.is_finished:
        extras.append(f"<span>Zuschauer: {escape(match.attendance)}</span>")
    if match.mvps and match.is_finished:
        mvp_labels: List[str] = []
        for selection in match.mvps:
            name = selection.name.strip() if selection.name else ""
            if not name:
                continue
            raw_team = (
                selection.team.strip()
                if isinstance(selection.team, str)
                else ""
            )
            team_label = pretty_name(raw_team) if raw_team else None
            if team_label:
                mvp_labels.append(f"{escape(name)} ({escape(team_label)})")
            elif selection.medal:
                mvp_labels.append(f"{escape(selection.medal)} – {escape(name)}")
            else:
                mvp_labels.append(escape(name))
        if mvp_labels:
            if len(mvp_labels) == 2:
                rendered_mvp = " und ".join(mvp_labels)
            else:
                rendered_mvp = " / ".join(mvp_labels)
            extras.append(f"<span>MVP: {rendered_mvp}</span>")

    links: List[str] = []
    if match.info_url:
        links.append(f"<a href=\"{escape(match.info_url)}\" target=\"_blank\" rel=\"noopener\">Spielinfos</a>")
    if match.stats_url and match.is_finished:
        links.append(f"<a href=\"{escape(match.stats_url)}\" target=\"_blank\" rel=\"noopener\">Statistik (PDF)</a>")

    meta_html = ""
    if extras or links:
        combined = extras + links
        meta_html = f"<div class=\"match-meta\">{' · '.join(combined)}</div>"
    stats_html = ""
    if stats:
        normalized_usc = normalize_name(USC_CANONICAL_NAME)
        canonical_usc = TEAM_CANONICAL_LOOKUP.get(normalized_usc)
        if canonical_usc:
            normalized_usc = normalize_name(canonical_usc)
        highlight_map: Dict[str, str] = {}
        if highlight_teams:
            for role, name in highlight_teams.items():
                if not name:
                    continue
                normalized_focus = normalize_name(name)
                canonical_focus = TEAM_CANONICAL_LOOKUP.get(normalized_focus)
                if canonical_focus:
                    normalized_focus = normalize_name(canonical_focus)
                highlight_map[role] = normalized_focus
        fallback_cards: List[str] = []
        table_entries: List[Tuple[str, Optional[str], MatchStatsMetrics]] = []
        tables_available = True
        for entry in stats:
            team_label = get_team_short_label(entry.team_name)
            normalized_team = normalize_name(entry.team_name)
            canonical_team = TEAM_CANONICAL_LOOKUP.get(normalized_team)
            if canonical_team:
                normalized_team = normalize_name(canonical_team)
            team_role: Optional[str] = None
            if normalized_team == normalized_usc:
                team_role = "usc"
            else:
                for role, normalized_focus in highlight_map.items():
                    if normalized_focus and normalized_team == normalized_focus:
                        team_role = role
                        break
            metrics = entry.metrics or _parse_match_stats_metrics(entry.totals_line)
            if metrics is None:
                tables_available = False
            else:
                table_entries.append((team_label, team_role, metrics))
            content_lines = [line for line in entry.header_lines if line]
            content_lines.append(entry.totals_line)
            content_text = "\n".join(content_lines)
            attrs: List[str] = ["class=\"match-stats-card\""]
            if team_role:
                attrs.append(f"data-team-role=\"{team_role}\"")
            attr_text = " ".join(attrs)
            card_lines = [
                f"        <article {attr_text}>",
                f"          <h4>{escape(team_label)}</h4>",
                f"          <pre>{escape(content_text)}</pre>",
                "        </article>",
            ]
            fallback_cards.append("\n".join(card_lines))
        if tables_available and table_entries:
            serve_rows: List[str] = []
            attack_rows: List[str] = []
            for team_label, team_role, metrics in table_entries:
                row_attr = f" data-team-role=\"{team_role}\"" if team_role else ""
                serve_rows.append(
                    "\n".join(
                        [
                            f"              <tr{row_attr}>",
                            f"                <th scope=\"row\">{escape(team_label)}</th>",
                            f"                <td>{metrics.serves_attempts}</td>",
                            f"                <td>{metrics.serves_errors}</td>",
                            f"                <td>{metrics.serves_points}</td>",
                            f"                <td>{metrics.receptions_attempts}</td>",
                            f"                <td>{metrics.receptions_errors}</td>",
                            f"                <td>{escape(metrics.receptions_positive_pct)} ({escape(metrics.receptions_perfect_pct)})</td>",
                            "              </tr>",
                        ]
                    )
                )
                attack_rows.append(
                    "\n".join(
                        [
                            f"              <tr{row_attr}>",
                            f"                <th scope=\"row\">{escape(team_label)}</th>",
                            f"                <td>{metrics.attacks_attempts}</td>",
                            f"                <td>{metrics.attacks_errors}</td>",
                            f"                <td>{metrics.attacks_blocked}</td>",
                            f"                <td>{metrics.attacks_points}</td>",
                            f"                <td>{escape(metrics.attacks_success_pct)}</td>",
                            f"                <td>{metrics.blocks_points}</td>",
                            "              </tr>",
                        ]
                    )
                )
            serve_rows_html = "\n".join(serve_rows)
            attack_rows_html = "\n".join(attack_rows)
            stats_html = (
                "    <details class=\"match-stats\">\n"
                "      <summary>Teamstatistik</summary>\n"
                "      <div class=\"match-stats-content\">\n"
                "        <div class=\"match-stats-table-wrapper\">\n"
                "          <table class=\"match-stats-table\">\n"
                "            <thead>\n"
                "              <tr>\n"
                "                <th scope=\"col\" rowspan=\"2\">Team</th>\n"
                "                <th scope=\"colgroup\" colspan=\"3\">Aufschlag</th>\n"
                "                <th scope=\"colgroup\" colspan=\"3\">Annahme</th>\n"
                "              </tr>\n"
                "              <tr>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Pos (Prf)</th>\n"
                "              </tr>\n"
                "            </thead>\n"
                "            <tbody>\n"
                f"{serve_rows_html}\n"
                "            </tbody>\n"
                "          </table>\n"
                "        </div>\n"
                "        <div class=\"match-stats-table-wrapper\">\n"
                "          <table class=\"match-stats-table\">\n"
                "            <thead>\n"
                "              <tr>\n"
                "                <th scope=\"col\" rowspan=\"2\">Team</th>\n"
                "                <th scope=\"colgroup\" colspan=\"5\">Angriff</th>\n"
                "                <th scope=\"colgroup\" colspan=\"1\">Block</th>\n"
                "              </tr>\n"
                "              <tr>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Blo</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "                <th scope=\"col\">Pkt%</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "              </tr>\n"
                "            </thead>\n"
                "            <tbody>\n"
                f"{attack_rows_html}\n"
                "            </tbody>\n"
                "          </table>\n"
                "        </div>\n"
                "      </div>\n"
                "    </details>"
            )
        elif fallback_cards:
            cards_html = "\n".join(fallback_cards)
            stats_html = (
                "    <details class=\"match-stats\">\n"
                "      <summary>Teamstatistik</summary>\n"
                "      <div class=\"match-stats-content\">\n"
                f"{cards_html}\n"
                "      </div>\n"
                "    </details>"
            )

    segments: List[str] = [
        "<li>",
        "  <div class=\"match-line\">",
        f"    <div class=\"match-header\"><strong>{escape(kickoff_label)}</strong> – {escape(teams)}</div>",
    ]
    if result_block:
        segments.append(f"    {result_block}")
    if meta_html:
        segments.append(f"    {meta_html}")
    if stats_html:
        segments.append(stats_html)
    segments.extend(["  </div>", "</li>"])
    return "\n".join(segments)


def format_news_list(items: Sequence[NewsItem]) -> str:
    if not items:
        return "<li>Keine aktuellen Artikel gefunden.</li>"

    rendered: List[str] = []
    for item in items:
        title = escape(item.title)
        url = escape(item.url)
        meta_parts: List[str] = [escape(item.source)] if item.source else []
        date_label = item.formatted_date
        if date_label:
            meta_parts.append(escape(date_label))
        meta = " – ".join(meta_parts)
        meta_html = f"<span class=\"news-meta\">{meta}</span>" if meta else ""
        rendered.append(
            f"<li><a href=\"{url}\">{title}</a>{meta_html}</li>"
        )
    return "\n      ".join(rendered)


MVP_DISPLAY_COLUMNS: Sequence[Tuple[str, str]] = (
    ("Rang", "Rang"),
    ("Name", "Name"),
    ("Position", "Position"),
    ("Mannschaft", "Team"),
    ("Kennzahl", "Kennzahl"),
    ("Spiele", "Spiele/Quote"),
    ("Wertung", "Wertung"),
)


def format_instagram_list(links: Sequence[str]) -> str:
    if not links:
        return "<li>Keine Links gefunden.</li>"

    rendered: List[str] = []
    for link in links:
        parsed = urlparse(link)
        segments = [segment for segment in parsed.path.split("/") if segment]
        display: str
        if not segments:
            display = f"@{parsed.netloc}" if parsed.netloc else link
        elif "p" in segments:
            index = segments.index("p")
            if index + 1 < len(segments):
                display = f"Beitrag {segments[index + 1]}"
            else:
                display = "Instagram-Post"
        elif "reel" in segments:
            index = segments.index("reel")
            if index + 1 < len(segments):
                display = f"Reel {segments[index + 1]}"
            else:
                display = "Reels"
        elif segments[0] == "stories" and len(segments) > 1:
            display = f"Stories @{segments[1]}"
        elif segments[-1] == "reels":
            display = "Reels-Übersicht"
        else:
            display = f"@{segments[0]}"
        rendered.append(f"<li><a href=\"{escape(link)}\">{escape(display)}</a></li>")
    return "\n          ".join(rendered)


def format_mvp_rankings_section(
    rankings: Optional[Mapping[str, Mapping[str, Any]]],
    *,
    usc_name: str,
    opponent_name: str,
) -> str:
    if not rankings:
        return ""

    normalized_usc = normalize_name(usc_name)
    normalized_opponent = normalize_name(opponent_name)

    def matches_team(team_normalized: str, target_normalized: str) -> bool:
        if not team_normalized or not target_normalized:
            return False
        if team_normalized == target_normalized:
            return True
        return team_normalized in target_normalized or target_normalized in team_normalized

    categories: List[str] = []
    for index, (indicator, payload) in enumerate(rankings.items()):
        headers = list((payload or {}).get("headers") or [])
        rows = list((payload or {}).get("rows") or [])
        header_index = {header: idx for idx, header in enumerate(headers)}

        def value_for(row: Sequence[str], header: str) -> str:
            index = header_index.get(header)
            if index is not None and index < len(row):
                return row[index].strip()
            return ""

        team_entries: Dict[str, List[Dict[str, str]]] = {"opponent": [], "usc": []}
        for row in rows:
            values: Dict[str, str] = {}
            for header, idx in header_index.items():
                if idx < len(row):
                    values[header] = row[idx]

            name_value = escape((values.get("Name") or value_for(row, "Name") or "–"))
            rank_value = escape((values.get("Rang") or value_for(row, "Rang") or "–"))
            team_raw = (
                (values.get("Mannschaft") or values.get("Team") or value_for(row, "Mannschaft"))
            ).strip()
            team_label = get_team_short_label(team_raw) if team_raw else ""
            position_raw = (values.get("Position") or value_for(row, "Position")).strip()
            sets_raw = (values.get("Sätze") or value_for(row, "Sätze")).strip()
            games_raw = (values.get("Spiele") or value_for(row, "Spiele")).strip()

            wert1_raw = (values.get("Wert1") or value_for(row, "Wert1")).strip()
            wertung_raw = (values.get("Wertung") or value_for(row, "Wertung")).strip()

            if wert1_raw and wertung_raw:
                score_value = f"{escape(wert1_raw)} | {escape(wertung_raw)}"
            else:
                metric_columns = ("Wert1", "Wert2", "Wert3", "Kennzahl", "Wertung")
                metric_values: List[str] = []
                for key in metric_columns:
                    raw_value = (values.get(key) or value_for(row, key)).strip()
                    if raw_value:
                        metric_values.append(escape(raw_value))

                if metric_values:
                    first_metric = metric_values[0]
                    last_metric = metric_values[-1]
                    if len(metric_values) == 1 or first_metric == last_metric:
                        score_value = first_metric
                    else:
                        score_value = f"{first_metric} | {last_metric}"
                else:
                    score_value = "–"

            if team_raw:
                normalized_team = normalize_name(team_raw)
            else:
                normalized_team = ""

            if matches_team(normalized_team, normalized_opponent):
                team_role = "opponent"
            elif matches_team(normalized_team, normalized_usc):
                team_role = "usc"
            else:
                continue

            meta_parts: List[str] = []
            if position_raw:
                meta_parts.append(escape(position_raw))
            if team_label:
                meta_parts.append(escape(team_label))
            if sets_raw:
                meta_parts.append(f"{escape(sets_raw)} Sätze")
            if games_raw:
                meta_parts.append(f"{escape(games_raw)} Spiele")
            meta_text = " • ".join(meta_parts)

            entry: Dict[str, str] = {
                "rank": rank_value,
                "name": name_value,
                "meta": meta_text,
                "score": score_value,
                "team": team_role,
            }
            team_entries[team_role].append(entry)

        ordered_entries: List[Dict[str, str]] = []
        for team_key in ("opponent", "usc"):
            ordered_entries.extend(team_entries[team_key][:3])

        list_items: List[str] = []
        for entry in ordered_entries:
            meta_html = (
                f"                    <span class=\"mvp-entry-meta\">{entry['meta']}</span>\n"
                if entry["meta"]
                else ""
            )
            list_items.append(
                "                <li class=\"mvp-entry\" "
                f"data-team=\"{entry['team']}\">\n"
                f"                  <span class=\"mvp-entry-rank\">{entry['rank']}</span>\n"
                "                  <div class=\"mvp-entry-info\">\n"
                f"                    <span class=\"mvp-entry-name\">{entry['name']}</span>\n"
                f"{meta_html}"
                "                  </div>\n"
                f"                  <span class=\"mvp-entry-score\">{entry['score']}</span>\n"
                "                </li>"
            )

        if list_items:
            items_html = "\n".join(list_items)
            category_body = (
                "            <div class=\"mvp-category-content\">\n"
                "              <ol class=\"mvp-list\">\n"
                f"{items_html}\n"
                "              </ol>\n"
                "            </div>\n"
            )
        else:
            category_body = (
                "            <div class=\"mvp-category-content\">\n"
                "              <p class=\"mvp-empty\">Keine MVP-Rankings für diese Kategorie verfügbar.</p>\n"
                "            </div>\n"
            )

        open_attr = " open" if index == 0 else ""
        categories.append(
            f"          <details class=\"mvp-category\"{open_attr}>\n"
            "            <summary>\n"
            f"              <span class=\"mvp-category-title\">{escape(indicator)}</span>\n"
            "            </summary>\n"
            f"{category_body}"
            "          </details>"
        )

    if not categories:
        return ""

    categories_html = "\n".join(categories)
    usc_label = get_team_short_label(usc_name)
    opponent_label = get_team_short_label(opponent_name)
    return (
        "\n"
        "    <section class=\"mvp-group\">\n"
        "      <details class=\"mvp-overview\">\n"
        "        <summary>MVP-Rankings</summary>\n"
        "        <div class=\"mvp-overview-content\">\n"
        "          <p class=\"mvp-note\">Top-3-Platzierungen je Team aus dem offiziellen MVP-Ranking der Volleyball Bundesliga.</p>\n"
        "          <div class=\"mvp-legend\">\n"
        f"            <span class=\"mvp-legend-item\" data-team=\"usc\">{escape(usc_label)}</span>\n"
        f"            <span class=\"mvp-legend-item\" data-team=\"opponent\">{escape(opponent_label)}</span>\n"
        "          </div>\n"
        f"{categories_html}\n"
        "        </div>\n"
        "      </details>\n"
        "    </section>\n"
        "\n"
    )


def calculate_age(birthdate: date, reference: date) -> Optional[int]:
    if birthdate > reference:
        return None
    years = reference.year - birthdate.year
    if (reference.month, reference.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def format_roster_list(
    roster: Sequence[RosterMember], *, match_date: Optional[date] = None
) -> str:
    if not roster:
        return "<li>Keine Kaderdaten gefunden.</li>"

    rendered: List[str] = []
    if isinstance(match_date, datetime):
        match_day: Optional[date] = match_date.date()
    else:
        match_day = match_date

    for member in roster:
        number = member.number_label
        if number and number.strip().isdigit():
            number_display = f"#{number.strip()}"
        elif number:
            number_display = number.strip()
        else:
            number_display = "Staff"
        name_html = escape(member.name)
        height_display: Optional[str] = None
        if member.height and not member.is_official:
            height_value = member.height.strip()
            if height_value:
                normalized = height_value.replace(',', '.').replace(' ', '')
                if normalized.replace('.', '', 1).isdigit():
                    if not height_value.endswith('cm'):
                        height_display = f"{height_value} cm"
                    else:
                        height_display = height_value
                else:
                    height_display = height_value
        birth_display = member.formatted_birthdate
        birthdate_value = member.birthdate_value
        age_display: Optional[str] = None
        if birthdate_value and match_day:
            age_value = calculate_age(birthdate_value, match_day)
            if age_value is not None:
                age_display = f"{age_value}"
        if birth_display:
            if age_display:
                birth_display = f"{birth_display} ({age_display})"
        else:
            birth_display = "–"

        nationality_value = (member.nationality or "").strip() or "–"
        role_value = (member.role or "").strip() or "–"

        detail_parts: List[str] = []
        if not member.is_official:
            detail_parts.append(height_display or "–")
        detail_parts.append(birth_display)
        detail_parts.append(nationality_value)
        detail_parts.append(role_value)

        meta_block = "<div class=\"roster-details\">{}</div>".format(
            " | ".join(escape(part) for part in detail_parts)
        )
        classes = ["roster-item"]
        classes.append("roster-official" if member.is_official else "roster-player")
        rendered.append(
            ("<li class=\"{classes}\">"
             "<span class=\"roster-number\">{number}</span>"
             "<div class=\"roster-text\"><span class=\"roster-name\">{name}</span>{meta}</div>"
             "</li>").format(
                classes=" ".join(classes),
                number=escape(number_display),
                name=name_html,
                meta=meta_block,
            )
        )
    return "\n          ".join(rendered)


def collect_birthday_notes(
    match_date: date,
    rosters: Sequence[tuple[str, Sequence[RosterMember]]],
) -> List[str]:
    notes: List[tuple[int, str]] = []
    for _team_name, roster in rosters:
        for member in roster:
            if member.is_official:
                continue
            birthdate = member.birthdate_value
            if not birthdate:
                continue
            try:
                occurrence = date(match_date.year, birthdate.month, birthdate.day)
            except ValueError:
                # Defensive: skip invalid dates such as 29.02 in non-leap years
                try:
                    occurrence = date(match_date.year - 1, birthdate.month, birthdate.day)
                except ValueError:
                    continue
            if occurrence > match_date:
                occurrence = date(match_date.year - 1, birthdate.month, birthdate.day)
            delta = (match_date - occurrence).days
            if delta < 0 or delta > 7:
                continue
            age_value = calculate_age(birthdate, match_date)
            if delta == 0:
                if age_value is not None:
                    note = f"{member.name.strip()} hat heute Geburtstag ({age_value} Jahre)!"
                else:
                    note = f"{member.name.strip()} hat heute Geburtstag!"
            else:
                date_label = occurrence.strftime("%d.%m.%Y")
                if age_value is not None:
                    note = (
                        f"{member.name.strip()} hatte am {date_label} Geburtstag"
                        f" ({age_value} Jahre)."
                    )
                else:
                    note = f"{member.name.strip()} hatte am {date_label} Geburtstag."
            notes.append((delta, note))
    notes.sort(key=lambda item: (item[0], item[1]))
    return [note for _, note in notes]


def format_transfer_list(items: Sequence[TransferItem]) -> str:
    if not items:
        return "<li>Keine Wechsel gemeldet.</li>"

    rendered: List[str] = []
    current_category: Optional[str] = None
    for item in items:
        if item.category and item.category != current_category:
            rendered.append(
                f"<li class=\"transfer-category\">{escape(item.category)}</li>"
            )
            current_category = item.category
        parts: List[str] = []
        name_part = item.name.strip()
        if name_part:
            parts.append(name_part)
        type_label = item.type_code.strip()
        if type_label:
            parts.append(type_label)
        nationality = item.nationality.strip()
        if nationality:
            parts.append(nationality)
        info = item.info.strip()
        if info:
            parts.append(info)
        related = item.related_club.strip()
        if related:
            parts.append(related)
        if not parts:
            continue
        rendered.append(
            f"<li class=\"transfer-line\">{' | '.join(escape(part) for part in parts)}</li>"
        )
    return "\n          ".join(rendered)



def _format_season_results_section(
    data: Optional[Mapping[str, Any]], opponent_name: str
) -> str:
    if not data or not isinstance(data, Mapping):
        return ""

    raw_title = data.get("title")
    if isinstance(raw_title, str) and raw_title.strip():
        title = raw_title.strip()
    else:
        title = "Ergebnis der Saison 2024/25"

    teams_raw = data.get("teams")
    teams_by_key: Dict[str, Dict[str, Any]] = {}
    if isinstance(teams_raw, Sequence):
        for entry in teams_raw:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            key = normalize_name(name)
            if not key or key in teams_by_key:
                continue
            details_raw = entry.get("details")
            details: List[str] = []
            if isinstance(details_raw, Sequence):
                for item in details_raw:
                    if not item:
                        continue
                    details.append(str(item).strip())
            teams_by_key[key] = {"name": name, "details": details}

    if not teams_by_key:
        links_raw = data.get("links")
        has_links = bool(
            isinstance(links_raw, Sequence)
            and any(
                isinstance(entry, Mapping)
                and str(entry.get("label") or "").strip()
                and str(entry.get("url") or "").strip()
                for entry in links_raw
            )
        )
        if not has_links:
            return ""

    normalized_opponent = normalize_name(opponent_name)
    normalized_usc = normalize_name(USC_CANONICAL_NAME)

    selected: List[Dict[str, Any]] = []
    missing_opponent = False
    if normalized_opponent and normalized_opponent in teams_by_key:
        selected.append(teams_by_key[normalized_opponent])
    elif normalized_opponent:
        missing_opponent = True

    usc_entry = teams_by_key.get(normalized_usc)
    if usc_entry and (not selected or usc_entry["name"] != selected[0]["name"]):
        selected.append(usc_entry)
    elif not selected and usc_entry:
        selected.append(usc_entry)

    status_message = ""
    if not selected:
        status_message = "Keine Saisoninformationen verfügbar."
    elif missing_opponent:
        status_message = (
            f"Für {pretty_name(opponent_name)} liegen keine Saisoninformationen vor."
        )

    cards_markup: List[str] = []
    for team in selected:
        name = team.get("name")
        if not name:
            continue
        details = [detail for detail in team.get("details", []) if detail]
        details_html = ""
        if details:
            detail_items = "".join(
                f"\n              <li>{escape(str(detail))}</li>" for detail in details
            )
            details_html = (
                "\n            <ul class=\"season-results-list\">"
                f"{detail_items}\n            </ul>"
            )
        cards_markup.append(
            "        <article class=\"season-results-card\">\n"
            f"          <h3>{escape(str(name))}</h3>{details_html}\n"
            "        </article>"
        )

    if not cards_markup:
        cards_markup.append(
            "        <p class=\"season-results-fallback\">Keine Saisoninformationen verfügbar.</p>"
        )

    links_raw = data.get("links")
    link_block: List[str] = []
    link_items: List[str] = []
    if isinstance(links_raw, Sequence):
        for entry in links_raw:
            if not isinstance(entry, Mapping):
                continue
            label = str(entry.get("label") or "").strip()
            url = str(entry.get("url") or "").strip()
            if not label or not url:
                continue
            link_items.append(
                f"          <li><a href=\"{escape(url)}\" rel=\"noopener\" target=\"_blank\">{escape(label)}</a></li>"
            )

    internal_link_url, internal_link_label = INTERNATIONAL_MATCHES_LINK
    link_items.append(
        f"          <li><a href=\"{escape(internal_link_url)}\">{escape(internal_link_label)}</a></li>"
    )
    link_items.append(
        "          <li><a href=\"https://github.com/uscmuenster/usc_streaminginfos\" rel=\"noopener\" target=\"_blank\">GitHub Projekt - Streaminginfos</a></li>"
    )

    if link_items:
        link_block = [
            "      <div class=\"season-results-links\">",
            "        <h3>Weitere Informationen</h3>",
            "        <ul class=\"season-results-link-list\">",
            *link_items,
            "        </ul>",
            "      </div>",
        ]

    header_lines = [
        "      <div class=\"season-results-header\">",
        f"        <h2>{escape(title)}</h2>",
    ]
    if status_message:
        header_lines.append(
            f"        <p class=\"season-results-status\">{escape(status_message)}</p>"
        )
    header_lines.append("      </div>")

    section_lines = [
        "    <section class=\"season-results\">",
        *header_lines,
        "      <div class=\"season-results-grid\">",
        *cards_markup,
        "      </div>",
    ]
    section_lines.extend(link_block)
    section_lines.append("    </section>")

    return "\n".join(section_lines)


def _parse_scouting_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BERLIN_TZ)
    return parsed.astimezone(BERLIN_TZ)


def _format_scouting_date(value: Optional[str]) -> str:
    parsed = _parse_scouting_datetime(value)
    if not parsed:
        return "–"
    return parsed.strftime("%d.%m.%Y")


def _resolve_opponent_label(match: Mapping[str, Any]) -> str:
    opponent_short = match.get("opponent_short")
    if opponent_short:
        return str(opponent_short)
    opponent = match.get("opponent")
    if opponent:
        return str(opponent)
    return "Unbekannt"


def _format_home_away_label(is_home: Optional[bool]) -> str:
    return "Heim" if is_home else "Auswärts"


def _format_home_away_marker(is_home: Optional[bool]) -> str:
    return "(H)" if is_home else "(A)"


def _format_int_value(value: Any, default: str = "0") -> str:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return str(int(stripped))
        except ValueError:
            return stripped
    return str(value)


def _format_pct_value(value: Any, default: str = "0%") -> str:
    if value in (None, ""):
        return default
    return str(value)


def _indent_html(content: str, spaces: int) -> str:
    indent = " " * spaces
    return "\n".join(f"{indent}{line}" if line else "" for line in content.splitlines())


def _summarize_set_results(sets: Sequence[str]) -> Optional[str]:
    home_sets = 0
    away_sets = 0
    parsed_any = False

    for raw_value in sets:
        parts = raw_value.split(":", 1)
        if len(parts) != 2:
            continue
        left, right = parts
        try:
            left_points = int(left.strip())
            right_points = int(right.strip())
        except ValueError:
            continue

        if left_points == right_points:
            continue

        parsed_any = True
        if left_points > right_points:
            home_sets += 1
        else:
            away_sets += 1

    if not parsed_any:
        return None

    return f"{home_sets}:{away_sets}"


def _format_match_sets_label(match: Mapping[str, Any]) -> str:
    result = match.get("result") or {}

    score_value = (result.get("score") or "").strip()
    if score_value:
        return score_value

    sets = result.get("sets") or []
    cleaned = [str(item).strip() for item in sets if str(item).strip()]
    if not cleaned:
        return "–"

    summarized = _summarize_set_results(cleaned)
    if summarized:
        return summarized

    return " ".join(cleaned)


def _resolve_match_metric(match: Mapping[str, Any], key: str) -> Any:
    metrics = match.get("metrics")
    if isinstance(metrics, Mapping):
        return metrics.get(key)
    return None


def _build_player_match_table_html(player: Mapping[str, Any]) -> str:
    matches = [match for match in player.get("matches") or [] if isinstance(match, Mapping)]
    totals = player.get("totals") if isinstance(player.get("totals"), Mapping) else None

    if not matches and totals is None:
        return '<p class="empty-state">Keine Spiele verfügbar.</p>'

    columns: list[tuple[str, bool]] = [
        ("Datum", False),
        ("Gegner", False),
        ("Sätze", False),
        ("Auf-Ges", True),
        ("Auf-Fhl", True),
        ("Auf-Pkt", True),
        ("An-Ges", True),
        ("An-Fhl", True),
        ("An-Pos%", True),
        ("An-Prf%", True),
        ("Ag-Ges", True),
        ("Ag-Fhl", True),
        ("Ag-Blo", True),
        ("Ag-Pkt", True),
        ("Ag-%", True),
        ("Block", True),
        ("Pkt.", True),
        ("Breakpkt.", True),
        ("+/−", True),
    ]

    lines = ['<table class="stats-table player-match-table">', '  <thead>', '    <tr>']
    for label, is_numeric in columns:
        cell_class = ' class="numeric"' if is_numeric else ""
        lines.append(
            f"      <th scope=\"col\"{cell_class}>{escape(label)}</th>"
        )
    lines.extend(['    </tr>', '  </thead>', '  <tbody>'])

    for match in matches:
        opponent = _resolve_opponent_label(match)
        row_values: list[tuple[str, bool]] = [
            (_format_scouting_date(match.get("kickoff")), False),
            (opponent, False),
            (_format_match_sets_label(match), False),
            (_format_int_value(_resolve_match_metric(match, "serves_attempts")), True),
            (_format_int_value(_resolve_match_metric(match, "serves_errors")), True),
            (_format_int_value(_resolve_match_metric(match, "serves_points")), True),
            (_format_int_value(_resolve_match_metric(match, "receptions_attempts")), True),
            (_format_int_value(_resolve_match_metric(match, "receptions_errors")), True),
            (
                _format_pct_value(
                    _resolve_match_metric(match, "receptions_positive_pct"),
                    default="–",
                ),
                True,
            ),
            (
                _format_pct_value(
                    _resolve_match_metric(match, "receptions_perfect_pct"),
                    default="–",
                ),
                True,
            ),
            (_format_int_value(_resolve_match_metric(match, "attacks_attempts")), True),
            (_format_int_value(_resolve_match_metric(match, "attacks_errors")), True),
            (_format_int_value(_resolve_match_metric(match, "attacks_blocked")), True),
            (_format_int_value(_resolve_match_metric(match, "attacks_points")), True),
            (
                _format_pct_value(
                    _resolve_match_metric(match, "attacks_success_pct"),
                    default="–",
                ),
                True,
            ),
            (_format_int_value(_resolve_match_metric(match, "blocks_points")), True),
            (
                _format_int_value(match.get("total_points"), default="–"),
                True,
            ),
            (
                _format_int_value(match.get("break_points"), default="–"),
                True,
            ),
            (
                _format_int_value(match.get("plus_minus"), default="–"),
                True,
            ),
        ]

        lines.append("    <tr>")
        for value, is_numeric in row_values:
            cell_class = " class=\"numeric\"" if is_numeric else ""
            lines.append(f"      <td{cell_class}>{escape(value)}</td>")
        lines.append("    </tr>")

    if totals is not None:
        lines.append('    <tr class="stats-table__total player-match-table__total-row">')
        lines.append('      <th scope="row">Summe</th>')
        lines.append('      <td></td>')
        lines.append('      <td></td>')
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('serves_attempts')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('serves_errors')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('serves_points')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('receptions_attempts')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('receptions_errors')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_pct_value(totals.get('receptions_positive_pct'), default='–'))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_pct_value(totals.get('receptions_perfect_pct'), default='–'))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('attacks_attempts')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('attacks_errors')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('attacks_blocked')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('attacks_points')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_pct_value(totals.get('attacks_success_pct'), default='–'))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(totals.get('blocks_points')))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(player.get('total_points'), default='–'))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(player.get('break_points_total'), default='–'))}</td>"
        )
        lines.append(
            f"      <td class=\"numeric\">{escape(_format_int_value(player.get('plus_minus_total'), default='–'))}</td>"
        )
        lines.append("    </tr>")

    lines.extend(['  </tbody>', '</table>'])
    return "\n".join(lines)


def _render_player_overview_content(
    usc_scouting: Optional[Mapping[str, Any]]
) -> tuple[str, str, str]:
    default_meta = "Die Daten werden geladen…"
    default_table = '        <p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>'
    default_list = '        <p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>'
    if not usc_scouting:
        return default_meta, default_table, default_list

    players = usc_scouting.get("players") or []
    if not players:
        return "Keine Spielerinnendaten verfügbar.", default_table, default_list

    meta_text = (
        "1 Spielerin mit Statistikdaten."
        if len(players) == 1
        else f"{len(players)} Spielerinnen mit Statistikdaten."
    )

    table_html_raw = _build_player_totals_table_html(players)
    table_html = (
        _indent_html(table_html_raw, 8) if table_html_raw else default_table
    )

    cards = []
    for player in players:
        if not isinstance(player, Mapping):
            continue
        cards.append(_build_player_card_html(player))

    if not cards:
        return meta_text, table_html, default_list

    cards_html = _indent_html("\n\n".join(cards), 8)
    return meta_text, table_html, cards_html


def _render_match_overview_content(
    usc_scouting: Optional[Mapping[str, Any]]
) -> str:
    default_html = '        <p class="empty-state">Keine Spiele verfügbar.</p>'
    if not usc_scouting:
        return default_html

    matches = usc_scouting.get("matches") or []
    totals = usc_scouting.get("totals")
    table_html = _build_match_table_html(matches, totals if isinstance(totals, Mapping) else None)
    if not table_html:
        return default_html

    return _indent_html(table_html, 8)


def build_html_report(
    *,
    next_home=None,
    usc_recent=None,
    opponent_recent=None,
    usc_next=None,
    opponent_next=None,
    usc_news=(),
    opponent_news=(),
    usc_instagram=(),
    opponent_instagram=(),
    usc_roster=(),
    opponent_roster=(),
    usc_transfers=(),
    opponent_transfers=(),
    usc_photo=None,
    opponent_photo=None,
    season_results=None,
    generated_at: Optional[datetime] = None,
    font_scale: float = 1.0,
    match_stats=None,
    mvp_rankings=None,
    usc_scouting: Optional[Mapping[str, Any]] = None,
) -> str:
    """Generate a lightweight scouting landing page for USC Münster."""

    generated_at = generated_at or datetime.now(tz=BERLIN_TZ)
    generated_label = format_generation_timestamp(generated_at)
    generated_iso = generated_at.astimezone(BERLIN_TZ).isoformat()

    (
        player_meta_text,
        player_table_html,
        player_list_html,
    ) = _render_player_overview_content(usc_scouting)
    preloaded_overview_json = "null"
    if usc_scouting:
        preloaded_overview_json = json.dumps(usc_scouting, ensure_ascii=False)
        preloaded_overview_json = preloaded_overview_json.replace("</", "<\\/")

    html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scouting USC Münster</title>
  <link rel="icon" type="image/png" sizes="32x32" href="favicon.png">
  <link rel="manifest" href="manifest.webmanifest">
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7f9;
      --fg: #0f172a;
      --muted: #475569;
      --accent: #0f766e;
      --accent-soft: rgba(15, 118, 110, 0.12);
      --card-bg: #ffffff;
      --card-border: rgba(15, 118, 110, 0.2);
      --shadow: 0 16px 34px rgba(15, 118, 110, 0.12);
    }}

    html {{
      font-size: 100%;
    }}

    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1f24;
        --fg: #e2f1f4;
        --muted: #93b4bf;
        --accent-soft: rgba(94, 234, 212, 0.16);
        --card-bg: #132a30;
        --card-border: rgba(94, 234, 212, 0.28);
        --shadow: 0 16px 30px rgba(0, 0, 0, 0.35);
      }}
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
    }}

    main {{
      max-width: min(120rem, 96vw);
      margin: 0 auto;
      padding: clamp(1.4rem, 4vw, 3rem) clamp(1.2rem, 5vw, 3.6rem);
      display: grid;
      gap: clamp(1.8rem, 4vw, 3rem);
    }}

    header.page-header {{
      display: grid;
      gap: 0.8rem;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(2.1rem, 5vw, 3rem);
      letter-spacing: -0.01em;
    }}

    p.page-intro {{
      margin: 0;
      max-width: 72rem;
      font-size: clamp(1rem, 2.4vw, 1.2rem);
      color: var(--muted);
    }}

    .update-note {{
      margin: 0;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0.9rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 600;
      font-size: 0.65rem;
      border: 1px solid var(--card-border);
    }}

    section {{
      display: grid;
      gap: clamp(1rem, 3vw, 1.8rem);
    }}

    h2 {{
      margin: 0;
      font-size: clamp(1.35rem, 3.2vw, 1.9rem);
    }}

    .section-hint {{
      margin: 0;
      color: var(--muted);
      font-size: 0.95rem;
    }}

    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      gap: clamp(1rem, 3vw, 1.6rem);
    }}

    .table-container {{
      overflow-x: auto;
      border-radius: 1rem;
      border: 1px solid var(--card-border);
      background: var(--card-bg);
      box-shadow: var(--shadow);
      padding: clamp(0.35rem, 1.5vw, 0.75rem);
    }}

    .stats-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
      min-width: 52rem;
    }}

    .stats-table caption {{
      text-align: left;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }}

    .stats-table th,
    .stats-table td {{
      padding: 0.55rem 0.75rem;
      text-align: left;
      white-space: nowrap;
      border-bottom: 1px solid rgba(15, 118, 110, 0.15);
    }}

    .stats-table thead th {{
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--accent);
      border-bottom: 2px solid var(--card-border);
    }}

    .stats-table tbody tr:nth-child(even) {{
      background: rgba(15, 118, 110, 0.06);
    }}

    .stats-table td.numeric,
    .stats-table th.numeric {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}

    .stats-table td.numeric-center,
    .stats-table th.numeric-center {{
      text-align: center;
      font-variant-numeric: tabular-nums;
    }}

    .stats-table__total th,
    .stats-table__total td {{
      font-weight: 600;
      border-top: 2px solid var(--card-border);
      background: rgba(15, 118, 110, 0.08);
    }}

    @media (prefers-color-scheme: dark) {{
      .stats-table tbody tr:nth-child(even) {{
        background: rgba(148, 210, 189, 0.08);
      }}
      .stats-table__total th,
      .stats-table__total td {{
        background: rgba(148, 210, 189, 0.12);
        border-top: 2px solid rgba(94, 234, 212, 0.28);
      }}
      .stats-table th,
      .stats-table td {{
        border-bottom: 1px solid rgba(94, 234, 212, 0.18);
      }}
    }}

    .player-list {{
      display: grid;
      gap: clamp(1.2rem, 3vw, 2rem);
    }}

    .player-card {{
      background: var(--card-bg);
      border-radius: 1.1rem;
      border: 1px solid var(--card-border);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .player-card__summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      cursor: pointer;
      padding: clamp(1.1rem, 3vw, 1.6rem);
      list-style: none;
      user-select: none;
    }}

    .player-card__summary::-webkit-details-marker {{
      display: none;
    }}

    .player-card__summary::after {{
      content: '▾';
      font-size: 1.1rem;
      color: var(--muted);
      transition: transform 0.2s ease;
    }}

    .player-card[open] > .player-card__summary::after {{
      transform: rotate(-180deg);
    }}

    .player-card__summary h3 {{
      margin: 0;
      font-size: clamp(1.25rem, 3vw, 1.6rem);
    }}

    .player-card__summary:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: 4px;
    }}

    .player-card__content {{
      display: grid;
      gap: clamp(0.9rem, 2.6vw, 1.3rem);
      padding: clamp(0.8rem, 2.4vw, 1.1rem) clamp(1.1rem, 3vw, 1.6rem) clamp(1.1rem, 3vw, 1.6rem);
      border-top: 1px solid var(--card-border);
    }}

    .player-card__table-wrapper {{
      overflow-x: auto;
    }}

    .player-match-table {{
      min-width: 52rem;
    }}


    .empty-state {{
      margin: 0;
      color: var(--muted);
      font-style: italic;
    }}
  </style>
</head>
<body>
  <main>
    <header class="page-header">
      <h1>Scouting USC Münster</h1>
      <p class="page-intro">Aggregierte Statistiken aller verfügbaren USC-Partien aus den offiziellen VBL-PDFs. Die Übersicht gruppiert alle Werte pro Spielerin und zeigt Summen über alle erfassten Spiele.</p>
      <p class="update-note" data-update-note data-generated="{generated_iso}">
        <span aria-hidden="true">📅</span>
        <span>Aktualisiert am {generated_label}</span>
      </p>
    </header>

    <section>
      <h2>Spielerinnen</h2>
      <p class="section-hint" data-player-meta>{player_meta}</p>
      <div class="table-container" data-player-table-container>
{player_table}
      </div>
      <div class="player-list" data-player-list>
{player_list}
      </div>
      <p class="empty-state" data-error hidden>Beim Laden der Scouting-Daten ist ein Fehler aufgetreten.</p>
    </section>
  </main>
  <script>
    const OVERVIEW_PATH = 'data/usc_stats_overview.json';
    const PRELOADED_OVERVIEW = __PRELOADED_OVERVIEW__;

    function formatDate(value) {{
      if (!value) return '–';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '–';
      return new Intl.DateTimeFormat('de-DE', {{ day: '2-digit', month: '2-digit', year: 'numeric' }}).format(date);
    }}

    function formatDateTime(value) {{
      if (!value) return '–';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '–';
      return new Intl.DateTimeFormat('de-DE', {{
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      }}).format(date);
    }}

    function formatInt(value) {{
      if (value === null || value === undefined) return '0';
      return Number(value).toString();
    }}

    function formatIntOrDash(value) {{
      if (value === null || value === undefined || value === '') return '–';
      if (typeof value === 'number') {{
        if (!Number.isFinite(value)) return '–';
        return Number.isInteger(value) ? value.toString() : value.toString();
      }}
      const trimmed = String(value).trim();
      if (!trimmed) return '–';
      const parsed = Number(trimmed);
      if (!Number.isNaN(parsed)) {{
        return Number.isInteger(parsed) ? Math.trunc(parsed).toString() : parsed.toString();
      }}
      return trimmed;
    }}

    function formatPctOrDash(value) {{
      if (value === null || value === undefined || value === '') return '–';
      return String(value);
    }}

    function getOpponentLabel(match) {{
      if (match && match.opponent_short) return match.opponent_short;
      if (match && match.opponent) return match.opponent;
      return 'Unbekannt';
    }}

    function formatSetScores(match) {{
      if (!match || !match.result) return '–';
      const sets = Array.isArray(match.result.sets) ? match.result.sets : [];
      const cleaned = sets
        .map(item => (item === null || item === undefined ? '' : String(item).trim()))
        .filter(Boolean);
      return cleaned.length ? cleaned.join(' ') : '–';
    }}

    function getMatchMetric(match, key) {{
      if (!match || !match.metrics || typeof match.metrics !== 'object') return undefined;
      return match.metrics[key];
    }}

    function buildPlayerMatchesTable(player) {{
      const matches = Array.isArray(player.matches)
        ? player.matches.filter(match => match && typeof match === 'object')
        : [];
      const totals = player && typeof player.totals === 'object' ? player.totals : null;
      if (!matches.length && !totals) {{
        return null;
      }}

      const columns = [
        {{ label: 'Datum' }},
        {{ label: 'Gegner' }},
        {{ label: 'Sätze' }},
        {{ label: 'Auf-Ges', numeric: true }},
        {{ label: 'Auf-Fhl', numeric: true }},
        {{ label: 'Auf-Pkt', numeric: true }},
        {{ label: 'An-Ges', numeric: true }},
        {{ label: 'An-Fhl', numeric: true }},
        {{ label: 'An-Pos%', numeric: true }},
        {{ label: 'An-Prf%', numeric: true }},
        {{ label: 'Ag-Ges', numeric: true }},
        {{ label: 'Ag-Fhl', numeric: true }},
        {{ label: 'Ag-Blo', numeric: true }},
        {{ label: 'Ag-Pkt', numeric: true }},
        {{ label: 'Ag-%', numeric: true }},
        {{ label: 'Block', numeric: true }},
        {{ label: 'Pkt.', numeric: true }},
        {{ label: 'Breakpkt.', numeric: true }},
        {{ label: '+/-', numeric: true }},
      ];

      const table = document.createElement('table');
      table.className = 'stats-table player-match-table';

      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      columns.forEach(column => {{
        const th = document.createElement('th');
        th.scope = 'col';
        if (column.numeric) th.className = 'numeric';
        th.textContent = column.label;
        headerRow.appendChild(th);
      }});
      thead.appendChild(headerRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      matches.forEach(match => {{
        const row = document.createElement('tr');
        const cells = [
          {{ value: formatDate(match.kickoff) }},
          {{ value: getOpponentLabel(match) }},
          {{ value: formatSetScores(match) }},
          {{ value: formatInt(getMatchMetric(match, 'serves_attempts')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'serves_errors')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'serves_points')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'receptions_attempts')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'receptions_errors')), numeric: true }},
          {{ value: formatPctOrDash(getMatchMetric(match, 'receptions_positive_pct')), numeric: true }},
          {{ value: formatPctOrDash(getMatchMetric(match, 'receptions_perfect_pct')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'attacks_attempts')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'attacks_errors')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'attacks_blocked')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'attacks_points')), numeric: true }},
          {{ value: formatPctOrDash(getMatchMetric(match, 'attacks_success_pct')), numeric: true }},
          {{ value: formatInt(getMatchMetric(match, 'blocks_points')), numeric: true }},
          {{ value: formatIntOrDash(match.total_points), numeric: true }},
          {{ value: formatIntOrDash(match.break_points), numeric: true }},
          {{ value: formatIntOrDash(match.plus_minus), numeric: true }},
        ];
        cells.forEach((cell, index) => {{
          const td = document.createElement('td');
          if (cell.numeric || (columns[index] && columns[index].numeric)) {{
            td.className = 'numeric';
          }}
          td.textContent = cell.value;
          row.appendChild(td);
        }});
        tbody.appendChild(row);
      }});

      if (totals) {{
        const totalRow = document.createElement('tr');
        totalRow.className = 'stats-table__total player-match-table__total-row';

        const totalCells = [
          {{ type: 'th', value: 'Summe', attrs: {{ scope: 'row' }} }},
          {{ value: '–' }},
          {{ value: '–' }},
          {{ value: formatInt(totals.serves_attempts), numeric: true }},
          {{ value: formatInt(totals.serves_errors), numeric: true }},
          {{ value: formatInt(totals.serves_points), numeric: true }},
          {{ value: formatInt(totals.receptions_attempts), numeric: true }},
          {{ value: formatInt(totals.receptions_errors), numeric: true }},
          {{ value: formatPctOrDash(totals.receptions_positive_pct), numeric: true }},
          {{ value: formatPctOrDash(totals.receptions_perfect_pct), numeric: true }},
          {{ value: formatInt(totals.attacks_attempts), numeric: true }},
          {{ value: formatInt(totals.attacks_errors), numeric: true }},
          {{ value: formatInt(totals.attacks_blocked), numeric: true }},
          {{ value: formatInt(totals.attacks_points), numeric: true }},
          {{ value: formatPctOrDash(totals.attacks_success_pct), numeric: true }},
          {{ value: formatInt(totals.blocks_points), numeric: true }},
          {{ value: formatIntOrDash(player.total_points), numeric: true }},
          {{ value: formatIntOrDash(player.break_points_total), numeric: true }},
          {{ value: formatIntOrDash(player.plus_minus_total), numeric: true }},
        ];

        totalCells.forEach((cell, index) => {{
          const isNumeric = cell.numeric || (columns[index] && columns[index].numeric);
          if (cell.type === 'th') {{
            const th = document.createElement('th');
            if (cell.attrs && cell.attrs.scope) {{
              th.scope = cell.attrs.scope;
            }}
            th.textContent = cell.value;
            totalRow.appendChild(th);
          }} else {{
            const td = document.createElement('td');
            if (isNumeric) td.className = 'numeric';
            td.textContent = cell.value;
            totalRow.appendChild(td);
          }}
        }});

        tbody.appendChild(totalRow);
      }}

      table.appendChild(tbody);
      return table;
    }}

    function buildPlayerSummaryTable(players) {{
      const validPlayers = Array.isArray(players)
        ? players.filter(player => player && typeof player === 'object')
        : [];
      if (!validPlayers.length) {{
        return null;
      }}

      const columns = [
        {{ label: '#', title: 'Rückennummer', numeric: true }},
        {{ label: 'Spielerin' }},
        {{ label: 'Sp.', title: 'Spiele mit Statistikdaten', numeric: true }},
        {{ label: 'Srv\u00a0V', title: 'Aufschlag-Versuche', numeric: true }},
        {{ label: 'Srv\u00a0F', title: 'Aufschlag-Fehler', numeric: true }},
        {{ label: 'Srv\u00a0Asse', title: 'Aufschlag-Asse', numeric: true }},
        {{ label: 'Ann\u00a0V', title: 'Annahme-Versuche', numeric: true }},
        {{ label: 'Ann\u00a0F', title: 'Annahme-Fehler', numeric: true }},
        {{ label: 'Ann\u00a0+%', title: 'Positive Annahmen', numeric: true }},
        {{ label: 'Ann\u00a0Perf%', title: 'Perfekte Annahmen', numeric: true }},
        {{ label: 'Ang\u00a0V', title: 'Angriffs-Versuche', numeric: true }},
        {{ label: 'Ang\u00a0F', title: 'Angriffs-Fehler', numeric: true }},
        {{ label: 'Ang\u00a0gebl.', title: 'Geblockte Angriffe', numeric: true }},
        {{ label: 'Ang\u00a0Pkt.', title: 'Angriffspunkte', numeric: true }},
        {{ label: 'Ang\u00a0%', title: 'Angriffsquote', numeric: true }},
        {{ label: 'Block', title: 'Blockpunkte', numeric: true }},
        {{ label: 'Pkt.', title: 'Gesamtpunkte', numeric: true }},
        {{ label: 'Breakpkt.', title: 'Breakpunkte', numeric: true }},
        {{ label: '+/-', title: 'Plus/Minus', numeric: true }},
      ];

      const table = document.createElement('table');
      table.className = 'stats-table';

      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      columns.forEach(column => {{
        const th = document.createElement('th');
        th.scope = 'col';
        if (column.numeric) th.className = 'numeric';
        if (column.title) th.title = column.title;
        th.textContent = column.label;
        headerRow.appendChild(th);
      }});
      thead.appendChild(headerRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      validPlayers.forEach(player => {{
        const totals = player && typeof player.totals === 'object' ? player.totals : {{}};
        const matches = Array.isArray(player.matches) ? player.matches : [];
        const matchCount = typeof player.match_count === 'number'
          ? player.match_count
          : matches.length;
        const row = document.createElement('tr');
        const jersey = player.jersey_number;
        const values = [
          {{ value: jersey === null || jersey === undefined || jersey === '' ? '–' : String(jersey), numeric: true }},
          {{ value: player.name || 'Unbekannt' }},
          {{ value: formatInt(matchCount), numeric: true }},
          {{ value: formatInt(totals.serves_attempts), numeric: true }},
          {{ value: formatInt(totals.serves_errors), numeric: true }},
          {{ value: formatInt(totals.serves_points), numeric: true }},
          {{ value: formatInt(totals.receptions_attempts), numeric: true }},
          {{ value: formatInt(totals.receptions_errors), numeric: true }},
          {{ value: formatPctOrDash(totals.receptions_positive_pct), numeric: true }},
          {{ value: formatPctOrDash(totals.receptions_perfect_pct), numeric: true }},
          {{ value: formatInt(totals.attacks_attempts), numeric: true }},
          {{ value: formatInt(totals.attacks_errors), numeric: true }},
          {{ value: formatInt(totals.attacks_blocked), numeric: true }},
          {{ value: formatInt(totals.attacks_points), numeric: true }},
          {{ value: formatPctOrDash(totals.attacks_success_pct), numeric: true }},
          {{ value: formatInt(totals.blocks_points), numeric: true }},
          {{ value: formatIntOrDash(player.total_points), numeric: true }},
          {{ value: formatIntOrDash(player.break_points_total), numeric: true }},
          {{ value: formatIntOrDash(player.plus_minus_total), numeric: true }},
        ];
        values.forEach((entry, index) => {{
          const cell = document.createElement('td');
          if (entry.numeric || (columns[index] && columns[index].numeric)) {{
            cell.className = 'numeric';
          }}
          cell.textContent = entry.value;
          row.appendChild(cell);
        }});
        tbody.appendChild(row);
      }});
      table.appendChild(tbody);
      return table;
    }}

    function renderPlayers(data) {{
      const container = document.querySelector('[data-player-list]');
      const tableContainer = document.querySelector('[data-player-table-container]');
      const metaNode = document.querySelector('[data-player-meta]');
      const errorNode = document.querySelector('[data-error]');
      container.innerHTML = '';
      if (tableContainer) tableContainer.innerHTML = '';
      if (errorNode) errorNode.hidden = true;
      const players = Array.isArray(data.players) ? data.players : [];
      if (metaNode) {{
        metaNode.textContent = players.length === 1 ? '1 Spielerin mit Statistikdaten.' : `<<players.length>> Spielerinnen mit Statistikdaten.`;
      }}
      if (!players.length) {{
        if (tableContainer) {{
          tableContainer.innerHTML = '<p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>';
        }}
        container.innerHTML = '<p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>';
        return;
      }}
      if (tableContainer) {{
        const table = buildPlayerSummaryTable(players);
        if (table) {{
          tableContainer.appendChild(table);
        }} else {{
          tableContainer.innerHTML = '<p class="empty-state">Noch keine Spielerinnendaten verfügbar.</p>';
        }}
      }}
      for (const player of players) {{
        const card = document.createElement('details');
        card.className = 'player-card';

        const summary = document.createElement('summary');
        summary.className = 'player-card__summary';
        const title = document.createElement('h3');
        const playerName = player && player.name ? player.name : 'Unbekannt';
        title.textContent = player.jersey_number ? `#<<player.jersey_number>> <<playerName>>` : playerName;
        summary.appendChild(title);
        card.appendChild(summary);

        const content = document.createElement('div');
        content.className = 'player-card__content';

        const tableWrapper = document.createElement('div');
        tableWrapper.className = 'player-card__table-wrapper';
        const table = buildPlayerMatchesTable(player);
        if (table) {{
          tableWrapper.appendChild(table);
        }} else {{
          tableWrapper.innerHTML = '<p class="empty-state">Keine Spiele verfügbar.</p>';
        }}
        content.appendChild(tableWrapper);
        card.appendChild(content);

        container.appendChild(card);
      }}
    }}

    function applyOverview(data) {{
      if (!data) return;
      renderPlayers(data);
      const note = document.querySelector('[data-update-note] span:last-child');
      if (note && data.generated) {{
        note.textContent = `Aktualisiert am <<formatDateTime(data.generated)>>`;
      }}
    }}

    async function bootstrap() {{
      let hasData = false;
      if (PRELOADED_OVERVIEW) {{
        applyOverview(PRELOADED_OVERVIEW);
        hasData = true;
      }}
      try {{
        const response = await fetch(OVERVIEW_PATH, {{ cache: 'no-store' }});
        if (!response.ok) {{
          throw new Error(`HTTP <<response.status>>`);
        }}
        const data = await response.json();
        applyOverview(data);
        hasData = true;
      }} catch (error) {{
        if (!hasData) {{
          const container = document.querySelector('[data-player-list]');
          if (container) {{
            container.innerHTML = '<p class="empty-state">Die Scouting-Daten konnten nicht geladen werden.</p>';
          }}
          const tableContainer = document.querySelector('[data-player-table-container]');
          if (tableContainer) {{
            tableContainer.innerHTML = '<p class="empty-state">Die Scouting-Daten konnten nicht geladen werden.</p>';
          }}
          const errorNode = document.querySelector('[data-error]');
          if (errorNode) {{
            errorNode.hidden = false;
            errorNode.textContent = `Fehler beim Laden: <<error instanceof Error ? error.message : String(error)>>`;
          }}
        }} else {{
          console.error(error);
        }}
      }}
    }}

    document.addEventListener('DOMContentLoaded', bootstrap);
  </script>
</body>
</html>"""
    class _SafeFormatDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    html = html.format_map(_SafeFormatDict(
        generated_iso=escape(generated_iso),
        generated_label=escape(generated_label),
        player_meta=escape(player_meta_text),
        player_table=player_table_html,
        player_list=player_list_html,
    ))
    html = html.replace("__PRELOADED_OVERVIEW__", preloaded_overview_json)
    html = html.replace("<<", "${").replace(">>", "}")
    return html


__all__ = [
    "BERLIN_TZ",
    "DEFAULT_SCHEDULE_URL",
    "NEWS_LOOKBACK_DAYS",
    "NewsItem",
    "Match",
    "MatchResult",
    "RosterMember",
    "MatchStatsTotals",
    "MatchPlayerStats",
    "TransferItem",
    "TEAM_HOMEPAGES",
    "TEAM_ROSTER_IDS",
    "TABLE_URL",
    "VBL_NEWS_URL",
    "VBL_PRESS_URL",
    "WECHSELBOERSE_URL",
    "USC_HOMEPAGE",
    "collect_team_news",
    "collect_team_transfers",
    "collect_match_stats_totals",
    "resolve_match_stats_metrics",
    "collect_instagram_links",
    "collect_team_roster",
    "collect_team_photo",
    "build_html_report",
    "download_schedule",
    "get_team_homepage",
    "get_team_roster_url",
    "fetch_team_news",
    "fetch_schedule",
    "find_last_matches_for_team",
    "find_next_match_for_team",
    "find_next_usc_home_match",
    "load_schedule_from_file",
    "parse_roster",
    "parse_schedule",
]
