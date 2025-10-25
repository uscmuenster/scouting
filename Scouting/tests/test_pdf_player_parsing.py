from __future__ import annotations

from scripts.report import (
    _parse_player_stats_line,
    _parse_team_player_lines,
)


def test_parse_player_stats_line_single_line() -> None:
    line = (
        "9 Jordan, Emilia 12 2 1 15 3 40% 20% 25 5 2 10 45% 3 18"
    )
    parsed = _parse_player_stats_line(line, "USC Münster")
    assert parsed is not None
    assert parsed.player_name == "Jordan, Emilia"
    assert parsed.jersey_number == 9
    assert parsed.total_points == 12
    assert parsed.break_points == 2
    assert parsed.plus_minus == 1
    assert parsed.metrics.receptions_positive == 0
    assert parsed.metrics.receptions_perfect == 0


def test_parse_team_player_lines_handles_multiline_rows() -> None:
    lines = [
        "Nr Spielerin Pos Aufschlag Annahme Angriff Block Punkte",
        "9 Jordan, Emilia Außenangreiferin",
        "12 2 1 15 3 40% 20% 25 5 2 10 45% 3 18",
        "10 Ford, Brianna Diagonal",
        "11 1 3 22 4 30% 10% 30 6 3 12 40% 2 19",
    ]

    combined_first = (
        "9 Jordan, Emilia Außenangreiferin 12 2 1 15 3 40% 20% 25 5 2 10 45% 3 18"
    )
    combined_second = (
        "10 Ford, Brianna Diagonal 11 1 3 22 4 30% 10% 30 6 3 12 40% 2 19"
    )

    expected_first = _parse_player_stats_line(combined_first, "USC Münster")
    expected_second = _parse_player_stats_line(combined_second, "USC Münster")
    assert expected_first is not None
    assert expected_second is not None

    players = _parse_team_player_lines(lines, "USC Münster")
    assert players == [expected_first, expected_second]


def test_parse_compact_player_stats_includes_counts() -> None:
    line = "5 MALM Cecilia 1 2 * * 6 4 +2 13 1 2 10 . 40% ( 20%) 12 3 . 4 33% ."
    parsed = _parse_player_stats_line(line, "USC Münster")
    assert parsed is not None
    assert parsed.total_points == 6
    assert parsed.break_points == 4
    assert parsed.plus_minus == 2
    assert parsed.metrics.receptions_positive == 4
    assert parsed.metrics.receptions_perfect == 2


def test_parse_compact_stats_handles_split_sign_tokens() -> None:
    line = (
        "4 ten Brinke Marije 3 3 6 * * * * 12 9 + 10 7 . 1 1 . 100% . 9 1 1 7 78% 4"
    )
    parsed = _parse_player_stats_line(line, "SSC Palmberg Schwerin")
    assert parsed is not None
    assert parsed.total_points == 12
    assert parsed.break_points == 9
    assert parsed.plus_minus == 10
    assert parsed.metrics.serves_attempts == 7
    assert parsed.metrics.receptions_attempts == 1
    assert parsed.metrics.attacks_points == 7


def test_parse_compact_stats_handles_split_negative_tokens() -> None:
    line = (
        "11 Frobel Svea 2 4 4 * * 9 1 - 5 8 . . 30 5 33% ( 10%) 30 5 4 9 30% ."
    )
    parsed = _parse_player_stats_line(line, "ETV Hamburger Volksbank Volleys")
    assert parsed is not None
    assert parsed.total_points == 9
    assert parsed.break_points == 1
    assert parsed.plus_minus == -5
    assert parsed.metrics.receptions_attempts == 30
    assert parsed.metrics.attacks_points == 9
