from __future__ import annotations

import json

from scripts.manual_stats import (
    build_manual_stats_overview,
    load_manual_team_files,
)


def _create_manual_stats_file(tmp_path):
    directory = tmp_path / "manual"
    directory.mkdir()
    payload = {
        "team": "Test Team",
        "aliases": ["TT"],
        "matches": [
            {
                "stats_url": "https://example.com/match-1",
                "serve": {"attempts": 10, "errors": 3, "points": 2},
                "reception": {
                    "attempts": 20,
                    "errors": 4,
                    "positive_pct": "40%",
                    "perfect_pct": "10%",
                },
                "attack": {
                    "attempts": 30,
                    "errors": 5,
                    "blocked": 2,
                    "points": 12,
                    "success_pct": "40%",
                },
                "block": {"points": 5},
                "players": [
                    {
                        "name": "PLAYER One",
                        "jersey_number": 7,
                        "total_points": 5,
                        "break_points": 2,
                        "plus_minus": 1,
                        "metrics": {
                            "serves_attempts": 5,
                            "serves_errors": 1,
                            "serves_points": 1,
                            "receptions_attempts": 6,
                            "receptions_errors": 1,
                            "receptions_positive_pct": "50%",
                            "receptions_perfect_pct": "17%",
                            "attacks_attempts": 9,
                            "attacks_errors": 2,
                            "attacks_blocked": 1,
                            "attacks_points": 4,
                            "attacks_success_pct": "44%",
                            "blocks_points": 0,
                        },
                    }
                ],
            },
            {
                "stats_url": "https://example.com/match-2",
                "serve": {"attempts": 15, "errors": 2, "points": 3},
                "reception": {
                    "attempts": 25,
                    "errors": 5,
                    "positive_pct": "44%",
                    "perfect_pct": "20%",
                },
                "attack": {
                    "attempts": 28,
                    "errors": 6,
                    "blocked": 3,
                    "points": 14,
                    "success_pct": "50%",
                },
                "block": {"points": 4},
                "players": [],
            },
        ],
    }
    path = directory / "test_team.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


def test_load_manual_team_files(tmp_path):
    directory = _create_manual_stats_file(tmp_path)

    entries = load_manual_team_files(directory)
    assert len(entries) == 1
    team_file = entries[0]

    assert team_file.team == "Test Team"
    assert len(team_file.matches) == 2
    first_match = team_file.matches[0]
    assert first_match.serve["attempts"] == 10
    assert first_match.reception["positive_pct"] == "40%"


def test_build_manual_stats_overview(tmp_path):
    directory = _create_manual_stats_file(tmp_path)
    output_path = tmp_path / "overview.json"

    payload = build_manual_stats_overview(directory=directory, output_path=output_path)

    assert output_path.exists()
    assert payload["team_count"] == 1

    team_payload = payload["teams"][0]
    assert team_payload["team"] == "Test Team"
    assert team_payload["match_count"] == 2

    totals = team_payload["totals"]
    assert totals["serve"]["attempts"] == 25
    assert totals["serve"]["errors"] == 5
    assert totals["reception"]["positive"] == 19
    assert totals["reception"]["perfect"] == 7
    assert totals["reception"]["positive_pct"] == "42%"
    assert totals["attack"]["points"] == 26
    assert totals["attack"]["success_pct"] == "45%"

    matches = team_payload["matches"]
    assert len(matches) == 2
    first_reception = matches[0]["reception"]
    assert first_reception["positive"] == 8
    assert first_reception["perfect"] == 2
