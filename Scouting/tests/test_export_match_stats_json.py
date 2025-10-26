import json

import requests

from scripts import report
from scripts.export_match_stats_json import export_match_stats


def test_export_match_stats_offline(monkeypatch, tmp_path) -> None:
    def offline_http_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(report, "_http_get", offline_http_get)

    stats_url = "https://www.volleyball-bundesliga.de/uploads/eb523e7a-332e-481d-a2ad-a6f9d1615c3e"
    output_path = tmp_path / "match_stats.json"

    payload = export_match_stats(stats_url, output_path=output_path)

    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data == payload
    assert data["stats_url"] == stats_url
    assert data["team_count"] == 2

    teams = {entry["team"]: entry for entry in data["teams"]}
    assert set(teams) == {
        "Allianz MTV Stuttgart",
        "ETV Hamburger Volksbank Volleys",
    }

    stuttgart = teams["Allianz MTV Stuttgart"]
    assert stuttgart["serve"]["attempts"] == 74
    assert stuttgart["attack"]["points"] == 40
    assert stuttgart["reception"]["positive"] == 22
    assert stuttgart["reception"]["perfect"] == 12
    assert stuttgart["player_count"] == len(stuttgart["players"]) > 0

    stuttgart_players = {player["name"]: player for player in stuttgart["players"]}
    assert "Stautz Antonia" in stuttgart_players
    stautz = stuttgart_players["Stautz Antonia"]
    assert stautz["metrics"]["attacks_points"] == 2
    assert stautz["metrics"]["serves_attempts"] == 10
    assert stautz["metrics"]["receptions_positive"] == 6

    varela = stuttgart_players["Varela Lucia"]
    assert varela["metrics"]["receptions_attempts"] == 0
    assert varela["metrics"]["receptions_perfect"] == 0
    assert varela["plus_minus"] == 8

    hamburg = teams["ETV Hamburger Volksbank Volleys"]
    assert hamburg["reception"]["attempts"] == 67
    assert hamburg["attack"]["points"] == 28
    assert hamburg["player_count"] == len(hamburg["players"]) == 14

    players = {player["name"]: player for player in hamburg["players"]}
    assert "Meiser Jana-Marie" in players
    meiser = players["Meiser Jana-Marie"]
    assert meiser["metrics"]["receptions_attempts"] == 21
    assert meiser["metrics"]["receptions_errors"] == 3
