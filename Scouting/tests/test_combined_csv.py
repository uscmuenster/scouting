from __future__ import annotations

import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "Scouting"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts.combined_csv import export_combined_player_stats


def test_export_combined_player_stats_merges_sources(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()

    csv_file = csv_dir / "m1-test-team.csv"
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Match ID",
                "Match Date",
                "Home Team",
                "Home Coach",
                "Stadium",
                "Number",
                "Name",
                "Total Points",
                "Break Points",
                "W-L",
                "Total Serve",
                "Serve Errors",
                "Ace",
                "Total Receptions",
                "Reception Erros",
                "Positive Pass Percentage",
                "Excellent/ Perfect Pass Percentage",
                "Total Attacks",
                "Attack Erros",
                "Blocked Attack",
                "Attack Points (Exc.)",
                "Attack Points Percentage (Exc.%)",
                "Block Points",
            ]
        )
        writer.writerow(
            [
                "M1",
                "2025-10-01",
                "test team",
                "",
                "Test Arena",
                "7",
                "example player",
                "11",
                "4",
                "3",
                "6",
                "2",
                "1",
                "12",
                "2",
                "50%",
                "25%",
                "14",
                "3",
                "1",
                "6",
                "43%",
                "2",
            ]
        )
        writer.writerow(
            [
                "M1",
                "2025-10-01",
                "test team",
                "",
                "Test Arena",
                "",
                "totals",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    league_payload = {
        "teams": [
            {
                "team": "Test Team",
                "matches": [
                    {
                        "match_number": "M1",
                        "match_id": "M1",
                        "kickoff": "2025-10-01T18:00:00+02:00",
                        "is_home": True,
                        "opponent": "Other Team",
                        "opponent_short": "Other",
                        "host": "Test Team",
                        "location": "Test Arena",
                        "result": {"summary": "3:1"},
                        "stats_url": "https://example.com/stats.pdf",
                    }
                ],
                "players": [
                    {
                        "name": "Example Player",
                        "jersey_number": 7,
                        "matches": [
                            {
                                "match_number": "M1",
                                "match_id": "M1",
                                "kickoff": "2025-10-01T18:00:00+02:00",
                                "is_home": True,
                                "opponent": "Other Team",
                                "opponent_short": "Other",
                                "stats_url": "https://example.com/stats.pdf",
                                "result": {"summary": "3:1"},
                                "metrics": {
                                    "serves_attempts": 5,
                                    "serves_errors": 1,
                                    "serves_points": 2,
                                    "receptions_attempts": 10,
                                    "receptions_errors": 1,
                                    "receptions_positive": 6,
                                    "receptions_perfect": 3,
                                    "receptions_positive_pct": "60%",
                                    "receptions_perfect_pct": "30%",
                                    "attacks_attempts": 15,
                                    "attacks_errors": 2,
                                    "attacks_blocked": 1,
                                    "attacks_points": 7,
                                    "attacks_success_pct": "47%",
                                    "blocks_points": 3,
                                },
                                "total_points": 12,
                                "break_points": 5,
                                "plus_minus": 3,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    csv_payload = {
        "teams": [
            {
                "team": "Test Team",
                "matches": [
                    {
                        "match_number": "M1",
                        "match_id": "M1",
                        "kickoff": "2025-10-01T18:00:00+02:00",
                        "is_home": True,
                        "opponent": "Other Team",
                        "opponent_short": "Other",
                        "host": "test team",
                        "location": "Test Arena",
                        "result": {"summary": "3:1"},
                        "csv_path": "data/csv/m1-test-team.csv",
                    }
                ],
            }
        ]
    }

    output_path = tmp_path / "combined.csv"
    row_count = export_combined_player_stats(
        league_payload=league_payload,
        csv_payload=csv_payload,
        csv_data_dir=csv_dir,
        output_path=output_path,
    )

    assert row_count == 1
    with output_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["player_name"] == "Example Player"
    assert row["team"] == "Test Team"
    assert row["opponent"] == "Other Team"
    assert row["data_sources"] == "csv;pdf"
    assert row["total_points"] == "11"
    assert row["serves_attempts"] == "6"
    assert row["csv_path"] == "data/csv/m1-test-team.csv"
    assert row["stats_url"] == "https://example.com/stats.pdf"
    assert row["host"] == "Test Team"
    assert float(row["receptions_positive_pct"]) == 0.5
