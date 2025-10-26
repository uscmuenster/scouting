from __future__ import annotations

import requests

from datetime import datetime, timezone

from scripts import stats as stats_module
from scripts import report


def test_build_stats_overview_offline(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    output_path = tmp_path / "usc.json"
    payload = stats_module.build_stats_overview(output_path=output_path)

    assert payload["match_count"] == 2
    matches_by_stats_url = {match["stats_url"]: match for match in payload["matches"]}

    schwerin_url = "https://www.volleyball-bundesliga.de/uploads/70a7c2ba-97bc-4478-8e8e-e55ec764d2e6"
    flacht_url = "https://www.volleyball-bundesliga.de/uploads/19bb6c96-f1cc-4867-9058-0864849ec964"

    assert schwerin_url in matches_by_stats_url
    assert flacht_url in matches_by_stats_url

    schwerin_match = matches_by_stats_url[schwerin_url]
    assert schwerin_match["metrics"]["serves_attempts"] == 105
    assert schwerin_match["metrics"]["receptions_attempts"] == 88
    assert schwerin_match["metrics"]["attacks_points"] == 52
    assert schwerin_match["metrics"]["blocks_points"] == 9

    totals = payload["totals"]
    assert totals["serves_attempts"] == 179  # 74 + 105
    assert totals["attacks_points"] == 92  # 40 + 52

    players_by_name = {player["name"]: player for player in payload["players"]}
    ford_matches = players_by_name["FORD Brianna"]["matches"]
    ford_schwerin = next(entry for entry in ford_matches if entry["stats_url"] == schwerin_url)
    assert ford_schwerin["metrics"]["attacks_points"] == 14
    assert ford_schwerin["metrics"]["serves_points"] == 5
    assert ford_schwerin["total_points"] == 19


def test_build_stats_overview_for_other_team(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    output_path = tmp_path / "schwerin.json"
    payload = stats_module.build_stats_overview(
        output_path=output_path,
        focus_team="SSC Palmberg Schwerin",
    )

    assert output_path.exists()
    assert payload["team"] == "SSC Palmberg Schwerin"
    assert payload["match_count"] == 1
    assert payload["player_count"] == 14

    match = payload["matches"][0]
    assert match["opponent"] == "USC Münster"
    assert match["metrics"]["serves_attempts"] == 107
    assert match["metrics"]["attacks_points"] == 50


def test_build_stats_overview_for_hamburg_includes_players(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    output_path = tmp_path / "hamburg.json"
    schwerin_url = "https://www.volleyball-bundesliga.de/uploads/831866c1-9e16-46f8-827c-4b0dd011928b"
    stuttgart_url = "https://www.volleyball-bundesliga.de/uploads/eb523e7a-332e-481d-a2ad-a6f9d1615c3e"

    matches = [
        report.Match(
            kickoff=datetime(2025, 10, 11, 17, 30, tzinfo=timezone.utc),
            home_team="ETV Hamburger Volksbank Volleys",
            away_team="Allianz MTV Stuttgart",
            host="ETV Hamburger Volksbank Volleys",
            location="CU Arena (21147 Hamburg)",
            result=report.MatchResult(
                score="0:3",
                total_points="51:75",
                sets=("14:25", "20:25", "17:25"),
            ),
            match_number="2005",
            match_id="777479964",
            info_url=None,
            stats_url=stuttgart_url,
            scoresheet_url=None,
            attendance=None,
        ),
        report.Match(
            kickoff=datetime(2025, 10, 18, 16, 0, tzinfo=timezone.utc),
            home_team="SSC Palmberg Schwerin",
            away_team="ETV Hamburger Volksbank Volleys",
            host="SSC Palmberg Schwerin",
            location="Palmberg Arena (19059 Schwerin)",
            result=report.MatchResult(
                score="3:0",
                total_points="75:41",
                sets=("25:16", "25:11", "25:14"),
            ),
            match_number="2012",
            match_id="777480001",
            info_url=None,
            stats_url=schwerin_url,
            scoresheet_url=None,
            attendance=None,
        ),
    ]

    payload = stats_module.build_stats_overview(
        matches=matches,
        output_path=output_path,
        focus_team=stats_module.HAMBURG_CANONICAL_NAME,
    )

    assert payload["team"] == stats_module.HAMBURG_CANONICAL_NAME
    assert payload["match_count"] == 2
    assert payload["player_count"] > 0

    players_by_name = {player["name"]: player for player in payload["players"]}
    assert "Frobel Svea" in players_by_name

    frobel_matches = {
        entry["stats_url"]: entry for entry in players_by_name["Frobel Svea"]["matches"]
    }

    assert schwerin_url in frobel_matches
    assert stuttgart_url in frobel_matches

    assert frobel_matches[schwerin_url]["metrics"]["attacks_points"] == 9
    assert frobel_matches[stuttgart_url]["metrics"]["attacks_points"] == 10


def test_build_stats_overview_for_aachen_includes_players(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    output_path = tmp_path / "aachen.json"
    wiesbaden_url = "https://www.volleyball-bundesliga.de/uploads/70911979-1c77-4379-a3c6-2307f6da95f7"
    stuttgart_url = "https://www.volleyball-bundesliga.de/uploads/87ce921b-7c97-4bd1-8784-72e187d41fa7"

    matches = [
        report.Match(
            kickoff=datetime(2025, 10, 24, 18, 0, tzinfo=timezone.utc),
            home_team="Ladies in Black Aachen",
            away_team="VC Wiesbaden",
            host="Ladies in Black Aachen",
            location="Neuer Tivoli (52070 Aachen)",
            result=report.MatchResult(
                score="3:2",
                total_points="108:109",
                sets=(),
            ),
            match_number="2004",
            match_id="777479987",
            info_url=None,
            stats_url=wiesbaden_url,
            scoresheet_url=None,
            attendance=None,
        ),
        report.Match(
            kickoff=datetime(2025, 10, 29, 19, 0, tzinfo=timezone.utc),
            home_team="Allianz MTV Stuttgart",
            away_team="Ladies in Black Aachen",
            host="Allianz MTV Stuttgart",
            location="SCHARRena (70174 Stuttgart)",
            result=report.MatchResult(
                score="3:0",
                total_points="75:44",
                sets=(),
            ),
            match_number="2007",
            match_id="777479988",
            info_url=None,
            stats_url=stuttgart_url,
            scoresheet_url=None,
            attendance=None,
        ),
    ]

    payload = stats_module.build_stats_overview(
        matches=matches,
        output_path=output_path,
        focus_team=stats_module.AACHEN_CANONICAL_NAME,
    )

    assert output_path.exists()
    assert payload["team"] == stats_module.AACHEN_CANONICAL_NAME
    assert payload["match_count"] == 2
    assert payload["player_count"] > 0

    matches_by_url = {entry["stats_url"]: entry for entry in payload["matches"]}
    assert matches_by_url[wiesbaden_url]["metrics"]["serves_attempts"] == 108
    assert matches_by_url[wiesbaden_url]["metrics"]["attacks_points"] == 61
    assert matches_by_url[stuttgart_url]["metrics"]["serves_attempts"] == 49
    assert matches_by_url[stuttgart_url]["metrics"]["attacks_points"] == 24

    totals = payload["totals"]
    assert totals["serves_attempts"] == 157
    assert totals["attacks_points"] == 85
    assert totals["blocks_points"] == 13

    players_by_name = {player["name"]: player for player in payload["players"]}
    assert "Jebens Celine" in players_by_name
    jebens_matches = {
        entry["stats_url"]: entry for entry in players_by_name["Jebens Celine"]["matches"]
    }
    assert wiesbaden_url in jebens_matches
    assert stuttgart_url in jebens_matches

def test_build_league_stats_overview(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    output_path = tmp_path / "league.json"
    payload = stats_module.build_league_stats_overview(output_path=output_path)

    assert output_path.exists()
    assert payload["team_count"] >= 2

    teams = {entry["team"]: entry for entry in payload["teams"]}
    assert "USC Münster" in teams
    assert teams["USC Münster"]["match_count"] == 2

    assert "SSC Palmberg Schwerin" in teams
    assert teams["SSC Palmberg Schwerin"]["match_count"] == 1
