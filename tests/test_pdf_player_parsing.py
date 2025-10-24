from __future__ import annotations

from usc_kommentatoren.report import (
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
