from __future__ import annotations

import requests

from datetime import datetime, timezone

from scripts import stats as stats_module
from scripts import report


def test_summarize_metrics_prefers_counts_for_percentages() -> None:
    entry_one = report.MatchStatsMetrics(
        serves_attempts=5,
        serves_errors=1,
        serves_points=2,
        receptions_attempts=10,
        receptions_errors=2,
        receptions_positive_pct="10%",
        receptions_perfect_pct="5%",
        attacks_attempts=20,
        attacks_errors=4,
        attacks_blocked=1,
        attacks_points=11,
        attacks_success_pct="30%",
        blocks_points=2,
        receptions_positive=7,
        receptions_perfect=3,
    )
    entry_two = report.MatchStatsMetrics(
        serves_attempts=4,
        serves_errors=0,
        serves_points=1,
        receptions_attempts=10,
        receptions_errors=1,
        receptions_positive_pct="15%",
        receptions_perfect_pct="8%",
        attacks_attempts=15,
        attacks_errors=3,
        attacks_blocked=2,
        attacks_points=9,
        attacks_success_pct="25%",
        blocks_points=1,
        receptions_positive=5,
        receptions_perfect=2,
    )

    aggregated = stats_module.summarize_metrics([entry_one, entry_two])
    assert aggregated is not None
    assert aggregated.receptions_positive == 12
    assert aggregated.receptions_positive_pct == "60%"
    assert aggregated.receptions_perfect == 5
    assert aggregated.receptions_perfect_pct == "25%"
    assert aggregated.attacks_points == 20
    assert aggregated.attacks_success_pct == "57%"


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


def test_build_stats_payload_filters_players_with_roster(monkeypatch) -> None:
    match = report.Match(
        kickoff=datetime(2025, 10, 1, 18, 0, tzinfo=timezone.utc),
        home_team="Focus Team",
        away_team="Opponent Team",
        host="Focus Team",
        location="Arena",
        result=report.MatchResult(
            score="3:0",
            total_points="75:50",
            sets=("25:18", "25:16", "25:16"),
        ),
        match_number="3001",
        match_id="999",
        info_url=None,
        stats_url="https://example.com/stats.pdf",
        scoresheet_url=None,
        attendance=None,
    )

    match_metrics = report.MatchStatsMetrics(
        serves_attempts=60,
        serves_errors=5,
        serves_points=8,
        receptions_attempts=40,
        receptions_errors=6,
        receptions_positive_pct="45%",
        receptions_perfect_pct="18%",
        attacks_attempts=120,
        attacks_errors=12,
        attacks_blocked=6,
        attacks_points=52,
        attacks_success_pct="43%",
        blocks_points=11,
        receptions_positive=18,
        receptions_perfect=7,
    )

    match_entry = stats_module.USCMatchStatsEntry(
        match=match,
        opponent="Opponent Team",
        opponent_short="Opponent",
        is_home=True,
        metrics=match_metrics,
    )

    focus_metrics = report.MatchStatsMetrics(
        serves_attempts=20,
        serves_errors=2,
        serves_points=4,
        receptions_attempts=10,
        receptions_errors=1,
        receptions_positive_pct="60%",
        receptions_perfect_pct="30%",
        attacks_attempts=30,
        attacks_errors=3,
        attacks_blocked=1,
        attacks_points=15,
        attacks_success_pct="50%",
        blocks_points=2,
        receptions_positive=6,
        receptions_perfect=3,
    )

    stray_metrics = report.MatchStatsMetrics(
        serves_attempts=15,
        serves_errors=1,
        serves_points=3,
        receptions_attempts=5,
        receptions_errors=2,
        receptions_positive_pct="20%",
        receptions_perfect_pct="10%",
        attacks_attempts=18,
        attacks_errors=5,
        attacks_blocked=2,
        attacks_points=6,
        attacks_success_pct="33%",
        blocks_points=1,
        receptions_positive=1,
        receptions_perfect=0,
    )

    focus_entry = stats_module.USCPlayerMatchEntry(
        player_name="Focus Player",
        jersey_number=7,
        match=match,
        opponent="Opponent Team",
        opponent_short="Opponent",
        is_home=True,
        metrics=focus_metrics,
        total_points=19,
        break_points=5,
        plus_minus=12,
    )

    stray_entry = stats_module.USCPlayerMatchEntry(
        player_name="Opponent Player",
        jersey_number=11,
        match=match,
        opponent="Opponent Team",
        opponent_short="Opponent",
        is_home=True,
        metrics=stray_metrics,
        total_points=9,
        break_points=2,
        plus_minus=1,
    )

    monkeypatch.setattr(
        stats_module,
        "collect_team_match_stats",
        lambda *args, **kwargs: [match_entry],
    )
    monkeypatch.setattr(
        stats_module,
        "collect_team_player_stats",
        lambda *args, **kwargs: [focus_entry, stray_entry],
    )

    roster_member = report.RosterMember(
        number_label="7",
        number_value=7,
        name="Focus Player",
        role="",
        is_official=False,
        height=None,
        birthdate_label=None,
        nationality=None,
    )

    payload = stats_module._build_stats_payload(
        matches=[match],
        focus_team="Focus Team",
        stats_lookup={},
        focus_roster=(roster_member,),
        generated_at=datetime(2025, 10, 2, 12, 0, tzinfo=timezone.utc),
    )

    player_names = {player["name"] for player in payload["players"]}
    assert player_names == {"Focus Player"}


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
