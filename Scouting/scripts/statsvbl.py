"""Utilities for scraping match data from the VBL DataProject portal."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_VBL_BASE_URL = "https://vbl-web.dataproject.com"
REQUEST_TIMEOUT = 20


@dataclass(frozen=True)
class VBLMatch:
    """Lightweight representation of a VBL match listed on the portal."""

    match_id: str
    competition_id: Optional[str] = None
    phase_id: Optional[str] = None
    club_id: Optional[str] = None
    match_number: Optional[str] = None
    date_label: Optional[str] = None
    time_label: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    result: Optional[str] = None
    set_results: Optional[str] = None
    leg_list_url: Optional[str] = None
    info_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "match_id": self.match_id,
            "competition_id": self.competition_id,
            "phase_id": self.phase_id,
            "club_id": self.club_id,
            "match_number": self.match_number,
            "date": self.date_label,
            "time": self.time_label,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "result": self.result,
            "set_results": self.set_results,
            "leg_list_url": self.leg_list_url,
            "info_url": self.info_url,
        }


@dataclass(frozen=True)
class VBLLegResult:
    """Score summary for a single set within a VBL match."""

    set_number: int
    home_points: int
    away_points: int
    home_label: Optional[str] = None
    away_label: Optional[str] = None
    duration: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "set": self.set_number,
            "home_points": self.home_points,
            "away_points": self.away_points,
            "home_label": self.home_label,
            "away_label": self.away_label,
            "duration": self.duration,
        }


def _default_fetcher(url: str) -> str:
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _normalize_label(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _parse_first_int(value: str) -> Optional[int]:
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def _parse_score_pair(value: str) -> Optional[Tuple[int, int]]:
    match = re.search(r"(-?\d+)\s*[-:\u2013]\s*(-?\d+)", value)
    if not match:
        return None
    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        return None


def _table_rows(table: Tag) -> Iterable[List[Tag]]:
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if cells:
            yield cells


def parse_competition_matches_html(
    html: str,
    *,
    base_url: str = DEFAULT_VBL_BASE_URL,
) -> List[VBLMatch]:
    """Parse the competition overview page for matches."""

    soup = BeautifulSoup(html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        if candidate.find("a", href=re.compile(r"MatchStatistics\.aspx", re.IGNORECASE)):
            table = candidate
            break
    if table is None:
        raise ValueError("Could not locate the competition matches table in the provided HTML")

    header_cells = []
    thead = table.find("thead")
    if thead:
        header_cells = thead.find_all("th")
    if not header_cells:
        header_row = table.find("tr")
        if header_row:
            header_cells = header_row.find_all("th")
    header_labels = [_normalize_label(cell.get_text(" ", strip=True)) for cell in header_cells]

    def _find_index(keywords: Sequence[str]) -> Optional[int]:
        for idx, label in enumerate(header_labels):
            for keyword in keywords:
                if keyword in label:
                    return idx
        return None

    match_number_idx = _find_index(["nr", "no", "match"])
    date_idx = _find_index(["datum", "date"])
    time_idx = _find_index(["zeit", "time"])
    home_idx = _find_index(["heim", "home", "team a"])
    away_idx = _find_index(["gast", "away", "team b"])
    result_idx = _find_index(["ergebnis", "result", "score"])
    sets_idx = _find_index(["s\u00e4tze", "sets", "leg"])

    matches: List[VBLMatch] = []
    seen_ids: set[str] = set()
    for cells in _table_rows(table):
        texts = [cell.get_text(" ", strip=True) for cell in cells]
        if not any(texts):
            continue

        anchors = cells[0].find_all("a", href=True)
        if len(anchors) <= 1:
            anchors = [anchor for cell in cells for anchor in cell.find_all("a", href=True)]

        match_id: Optional[str] = None
        competition_id: Optional[str] = None
        phase_id: Optional[str] = None
        club_id: Optional[str] = None
        leg_list_url: Optional[str] = None
        info_url: Optional[str] = None

        for anchor in anchors:
            href = anchor.get("href") or ""
            if not href:
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            if "mID" in params and not match_id:
                match_id = params["mID"][0]
            if "ID" in params and not competition_id:
                competition_id = params["ID"][0]
            if "PID" in params and not phase_id:
                phase_id = params["PID"][0]
            if "CID" in params and not club_id:
                club_id = params["CID"][0]
            type_param = (params.get("type") or [""])[0].lower()
            if "matchstatistics.aspx" in parsed.path.lower() and type_param == "leglist":
                if leg_list_url is None:
                    leg_list_url = full_url
            elif "matchstatistics.aspx" in parsed.path.lower():
                if info_url is None:
                    info_url = full_url

        if not match_id:
            row_html = "".join(str(cell) for cell in cells)
            fallback = re.search(r"mID=(\d+)", row_html)
            if fallback:
                match_id = fallback.group(1)

        if not match_id or match_id in seen_ids:
            continue

        seen_ids.add(match_id)

        def _get_value(index: Optional[int]) -> Optional[str]:
            if index is None or index >= len(cells):
                return None
            value = cells[index].get_text(" ", strip=True)
            return value or None

        match_number = _get_value(match_number_idx)
        date_label = _get_value(date_idx)
        time_label = _get_value(time_idx)
        home_team = _get_value(home_idx)
        away_team = _get_value(away_idx)
        result_text = _get_value(result_idx)
        set_results = _get_value(sets_idx)

        matches.append(
            VBLMatch(
                match_id=match_id,
                competition_id=competition_id,
                phase_id=phase_id,
                club_id=club_id,
                match_number=match_number,
                date_label=date_label,
                time_label=time_label,
                home_team=home_team,
                away_team=away_team,
                result=result_text,
                set_results=set_results,
                leg_list_url=leg_list_url,
                info_url=info_url,
            )
        )

    return matches


def _table_looks_like_leg_list(table: "BeautifulSoup") -> bool:
    headers = " ".join(
        _normalize_label(cell.get_text(" ", strip=True)) for cell in table.find_all("th")
    )
    if any(keyword in headers for keyword in ["set", "satz", "leg"]):
        return True
    sample_row = table.find("tr")
    if not sample_row:
        return False
    values = sample_row.get_text(" ", strip=True)
    numbers = re.findall(r"\d+", values)
    return len(numbers) >= 3


def parse_leg_list_html(html: str) -> List[VBLLegResult]:
    """Parse the LegList match statistics table."""

    soup = BeautifulSoup(html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        if _table_looks_like_leg_list(candidate):
            table = candidate
            break
    if table is None:
        raise ValueError("Could not locate the leg list table in the provided HTML")

    header_cells = []
    thead = table.find("thead")
    if thead:
        header_cells = thead.find_all("th")
    if not header_cells:
        header_row = table.find("tr")
        if header_row:
            header_cells = header_row.find_all("th")
    header_labels = [_normalize_label(cell.get_text(" ", strip=True)) for cell in header_cells]

    def _find_index(keywords: Sequence[str]) -> Optional[int]:
        for idx, label in enumerate(header_labels):
            for keyword in keywords:
                if keyword in label:
                    return idx
        return None

    set_idx = _find_index(["set", "satz", "leg"])
    home_team_idx = _find_index(["heim", "home", "team a"])
    home_points_idx = _find_index(
        ["heim punkte", "heim points", "home points", "home score", "heim ergebnis"]
    )
    away_team_idx = _find_index(["gast", "away", "team b"])
    away_points_idx = _find_index(
        ["gast punkte", "gast points", "away points", "away score", "gast ergebnis"]
    )
    score_idx = _find_index(["score", "ergebnis", "result", "punkte", "points"])
    duration_idx = _find_index(["dauer", "duration", "zeit", "time"])

    legs: List[VBLLegResult] = []
    for cells in _table_rows(table):
        texts = [cell.get_text(" ", strip=True) for cell in cells]
        if not any(texts):
            continue

        set_number = None
        if set_idx is not None and set_idx < len(cells):
            set_number = _parse_first_int(cells[set_idx].get_text(" ", strip=True))
        if set_number is None:
            candidate_set = _parse_first_int(texts[0]) if texts else None
            if candidate_set in {1, 2, 3, 4, 5}:
                set_number = candidate_set
            else:
                set_number = len(legs) + 1

        def _value_at(index: Optional[int]) -> Optional[str]:
            if index is None or index >= len(cells):
                return None
            value = cells[index].get_text(" ", strip=True)
            return value or None

        home_label = _value_at(home_team_idx)
        away_label = _value_at(away_team_idx)

        home_points: Optional[int] = None
        away_points: Optional[int] = None

        if home_points_idx is not None and home_points_idx < len(cells):
            home_points = _parse_first_int(cells[home_points_idx].get_text(" ", strip=True))
        if away_points_idx is not None and away_points_idx < len(cells):
            away_points = _parse_first_int(cells[away_points_idx].get_text(" ", strip=True))

        if (home_points is None or away_points is None) and score_idx is not None and score_idx < len(cells):
            pair = _parse_score_pair(cells[score_idx].get_text(" ", strip=True))
            if pair:
                home_points, away_points = pair

        if home_points is None or away_points is None:
            for cell in cells:
                pair = _parse_score_pair(cell.get_text(" ", strip=True))
                if pair:
                    home_points, away_points = pair
                    break

        if home_points is None or away_points is None:
            numeric_values: List[int] = []
            for cell in cells:
                text = cell.get_text(" ", strip=True)
                if re.search(r"\d\s*:\s*\d", text):
                    continue
                parsed = _parse_first_int(text)
                if parsed is not None:
                    numeric_values.append(parsed)
            if len(numeric_values) >= 3:
                home_points = numeric_values[1]
                away_points = numeric_values[2]

        if home_label is None:
            for text in texts:
                if not text or _parse_first_int(text) is not None:
                    continue
                if home_points is not None and str(home_points) in text:
                    continue
                if away_points is not None and str(away_points) in text:
                    continue
                home_label = text
                break

        if away_label is None:
            reversed_texts = list(reversed(texts))
            for text in reversed_texts:
                if not text or _parse_first_int(text) is not None:
                    continue
                if home_label and text == home_label:
                    continue
                away_label = text
                break

        if home_points is None or away_points is None:
            continue

        duration = _value_at(duration_idx)
        if duration:
            duration = duration.replace("\xa0", " ").strip() or None

        legs.append(
            VBLLegResult(
                set_number=set_number,
                home_points=home_points,
                away_points=away_points,
                home_label=home_label,
                away_label=away_label,
                duration=duration,
            )
        )

    return legs


def build_leg_list_url(
    match_id: str,
    *,
    competition_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    club_id: Optional[str] = None,
    base_url: str = DEFAULT_VBL_BASE_URL,
) -> str:
    params: Dict[str, str] = {"mID": match_id, "type": "LegList"}
    if competition_id:
        params["ID"] = competition_id
    if phase_id:
        params["PID"] = phase_id
    if club_id:
        params["CID"] = club_id
    return f"{base_url.rstrip('/')}/MatchStatistics.aspx?{urlencode(params)}"


def fetch_competition_matches(
    competition_id: str,
    phase_id: str,
    *,
    base_url: str = DEFAULT_VBL_BASE_URL,
    fetcher: Optional[Callable[[str], str]] = None,
) -> List[VBLMatch]:
    url = f"{base_url.rstrip('/')}/CompetitionMatches.aspx?ID={competition_id}&PID={phase_id}"
    fetch = fetcher or _default_fetcher
    html = fetch(url)
    return parse_competition_matches_html(html, base_url=base_url)


def fetch_match_leg_list(
    match: VBLMatch,
    *,
    base_url: str = DEFAULT_VBL_BASE_URL,
    fetcher: Optional[Callable[[str], str]] = None,
    club_id: Optional[str] = None,
) -> List[VBLLegResult]:
    url = match.leg_list_url
    if not url:
        url = build_leg_list_url(
            match.match_id,
            competition_id=match.competition_id,
            phase_id=match.phase_id,
            club_id=club_id or match.club_id,
            base_url=base_url,
        )
    fetch = fetcher or _default_fetcher
    html = fetch(url)
    return parse_leg_list_html(html)


def _build_match_payload(match: VBLMatch, legs: Sequence[VBLLegResult]) -> Dict[str, object]:
    payload: Dict[str, object] = dict(match.to_dict())
    payload["legs"] = [leg.to_dict() for leg in legs]
    home_sets = sum(1 for leg in legs if leg.home_points > leg.away_points)
    away_sets = sum(1 for leg in legs if leg.away_points > leg.home_points)
    payload["home_sets"] = home_sets if legs else None
    payload["away_sets"] = away_sets if legs else None
    if legs:
        payload["set_scores"] = ", ".join(
            f"{leg.home_points}-{leg.away_points}" for leg in legs
        )
    else:
        payload["set_scores"] = match.set_results
    payload["has_leg_data"] = bool(legs)
    return payload


def collect_vbl_match_leg_results(
    competition_id: str,
    phase_id: str,
    *,
    club_id: Optional[str] = None,
    base_url: str = DEFAULT_VBL_BASE_URL,
    match_fetcher: Optional[Callable[[str], str]] = None,
    leg_fetcher: Optional[Callable[[VBLMatch, str], str]] = None,
) -> Dict[str, object]:
    try:
        matches = fetch_competition_matches(
            competition_id,
            phase_id,
            base_url=base_url,
            fetcher=match_fetcher,
        )
    except (requests.RequestException, ValueError):
        return {
            "competition_id": competition_id,
            "phase_id": phase_id,
            "club_id": club_id,
            "match_count": 0,
            "matches": [],
        }

    collected: List[Dict[str, object]] = []
    for match in matches:
        if club_id and match.club_id and match.club_id != club_id:
            continue
        effective_match = match
        if club_id and not match.club_id:
            effective_match = replace(match, club_id=club_id)
        try:
            legs = fetch_match_leg_list(
                effective_match,
                base_url=base_url,
                fetcher=(
                    (lambda url, match=effective_match: leg_fetcher(match, url))
                    if leg_fetcher
                    else None
                ),
                club_id=club_id,
            )
        except (requests.RequestException, ValueError):
            legs = []
        collected.append(_build_match_payload(effective_match, legs))

    return {
        "competition_id": competition_id,
        "phase_id": phase_id,
        "club_id": club_id,
        "match_count": len(collected),
        "matches": collected,
    }


__all__ = [
    "DEFAULT_VBL_BASE_URL",
    "VBLMatch",
    "VBLLegResult",
    "build_leg_list_url",
    "collect_vbl_match_leg_results",
    "fetch_competition_matches",
    "fetch_match_leg_list",
    "parse_competition_matches_html",
    "parse_leg_list_html",
]

