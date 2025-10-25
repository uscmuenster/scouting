from __future__ import annotations

import requests

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
    assert ford_schwerin["metrics"]["attacks_points"] == 17
    assert ford_schwerin["metrics"]["serves_points"] == 4
    assert ford_schwerin["total_points"] == 24
