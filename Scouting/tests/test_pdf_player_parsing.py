from __future__ import annotations

from dataclasses import replace

from scripts import report as report_module
from scripts.report import (
    MatchPlayerStats,
    MatchStatsMetrics,
    MatchStatsTotals,
    _parse_player_stats_line,
    _parse_stats_totals_pdf,
    _parse_team_player_lines,
    _build_modern_compact_tokens,
    fetch_match_stats_totals,
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


def test_parse_team_player_lines_adds_zero_stats_for_inactive_player() -> None:
    lines = [
        "Nr Spielerin Pos Aufschlag Annahme Angriff Block Punkte",
        "6 VON MEYENN Constanze Diagonal",
        "9 Jordan, Emilia 12 2 1 15 3 40% 20% 25 5 2 10 45% 3 18",
    ]

    players = _parse_team_player_lines(
        lines, "ETV Hamburger Volksbank Volleys"
    )

    assert len(players) == 2

    inactive, active = players
    assert inactive.player_name == "VON MEYENN Constanze"
    assert inactive.jersey_number == 6
    assert inactive.total_points == 0
    assert inactive.break_points == 0
    assert inactive.plus_minus == 0
    assert inactive.metrics.serves_attempts == 0
    assert inactive.metrics.receptions_attempts == 0
    assert inactive.metrics.attacks_attempts == 0
    assert inactive.metrics.blocks_points == 0

    assert active.player_name == "Jordan, Emilia"


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


def test_split_player_line_candidates_handles_prefixed_role_markers() -> None:
    raw_line = (
        "Kotrainer 1LMolenaar Pippa   .   .  -2   .   . .  30   2  27% ( 13%)   .   .   . .  . . "
        "2LSchaefer Lara-Marie   .   .   .   .   . .   .   .   .   .   .   .   . .  . ."
    )

    players = _parse_team_player_lines([raw_line], "USC Münster")
    assert len(players) == 2

    molenaar, schaefer = players

    assert molenaar.player_name == "Molenaar Pippa"
    assert molenaar.jersey_number == 1
    assert molenaar.total_points == 0
    assert molenaar.break_points == 0
    assert molenaar.plus_minus == -2
    assert molenaar.metrics.serves_attempts == 0
    assert molenaar.metrics.receptions_attempts == 30
    assert molenaar.metrics.receptions_errors == 2
    assert molenaar.metrics.receptions_positive_pct == "27%"
    assert molenaar.metrics.receptions_perfect_pct == "13%"

    assert schaefer.player_name == "Schaefer Lara-Marie"
    assert schaefer.jersey_number == 2
    assert schaefer.total_points == 0
    assert schaefer.metrics.serves_attempts == 0


def test_extract_modern_compact_percentages_handles_spacing() -> None:
    text = "Kuipers Jette 5 5 6 6 1 2 7 1 1 1 1 1 1 1 6 . 3 1 % ( 6 % ) 1 5 . . 6 4 0 % 5 1 0"
    positive, perfect = report_module._extract_modern_compact_percentages(text)
    assert positive == "31%"
    assert perfect == "6%"


def test_extract_modern_compact_percentages_trims_prefix_digits() -> None:
    text = (
        "Levinska Marta Kamelija ... 5 8 3 2 4 2 7 3 9 9 4 1 2 2 4 % ( 7 % ) 7 6 2"
    )
    positive, perfect = report_module._extract_modern_compact_percentages(text)
    assert positive == "24%"
    assert perfect == "7%"


def test_build_modern_compact_tokens_decodes_split_prefix_digits() -> None:
    snippet = (
        "Levinska Marta Kamelija 4 6 4 5 4 5 . 5 1 5 5 3 1 2 3 . . . . . 3 7 5 4 1 4"
        " 3 8 % 1 7 3 2 1 3"
    )
    tokens = _build_modern_compact_tokens(snippet)
    assert tokens[3] == "46"
    assert tokens[4] == "4"
    assert tokens[5] == "5"
    assert tokens[6] == "45"
    assert tokens[7] == "5"


def test_build_modern_compact_tokens_uses_longest_prefix_slice() -> None:
    snippet = (
        "Levinska Marta Kamelija 4 4 5 6 . 3 1 2 5 1 2 1 3 . 1 . . . . 2 2 . . 1 1"
        " 5 0 % . 5 8 3 2 4 2 7 3 9 9"
    )
    tokens = _build_modern_compact_tokens(snippet)
    assert tokens[3] == "44"
    assert tokens[4] == "5"
    assert tokens[5] == "6"
    assert tokens[6] == "31"
    assert tokens[7] == "25"


def test_parse_stats_totals_pdf_handles_players_after_totals_marker(monkeypatch) -> None:
    lines = [
        "Team B 2",
        "Satz Punkte Aufschlag Annahme Angriff Bk",
        "Spieler insgesamt",
        "Trainer",
        "Kotrainer 1LMolenaar Pippa   .   .  -2   .   . .  30   2  27% ( 13%)   .   .   . .  . .",
        " 2LSchaefer Lara-Marie   .   .   .   .   . .   .   .   .   .   .   .   . .  . .",
        " 3 Spöler Esther 55555**  10   6 +7  19   2 1   1   . 100%   .  17   .   1 7 41% 2",
        " 75 33+23105 1914 88 15 30% ( 15%)132 10  852 39%9",
    ]
    text = "\n".join(lines)

    class DummyPage:
        def extract_text(self) -> str:
            return text

    class DummyReader:
        def __init__(self, _data: object) -> None:
            self.pages = [DummyPage()]

    monkeypatch.setattr(report_module, "PdfReader", DummyReader)

    summaries = _parse_stats_totals_pdf(b"dummy")
    assert len(summaries) == 1

    summary = summaries[0]
    names = {player.player_name for player in summary.players}
    assert "Molenaar Pippa" in names

    molenaar = next(
        player for player in summary.players if player.player_name == "Molenaar Pippa"
    )
    assert molenaar.metrics.serves_attempts == 0


def test_fetch_match_stats_totals_prefers_parsed_player_metrics(monkeypatch, tmp_path) -> None:
    stats_url = "https://example.com/sample.pdf"

    parsed_metrics = MatchStatsMetrics(
        serves_attempts=0,
        serves_errors=0,
        serves_points=0,
        receptions_attempts=30,
        receptions_errors=2,
        receptions_positive_pct="27%",
        receptions_perfect_pct="13%",
        attacks_attempts=0,
        attacks_errors=0,
        attacks_blocked=0,
        attacks_points=0,
        attacks_success_pct="0%",
        blocks_points=0,
        receptions_positive=8,
        receptions_perfect=4,
    )

    parsed_player = MatchPlayerStats(
        team_name="USC Münster",
        player_name="MOLENAAR Pippa",
        jersey_number=1,
        metrics=parsed_metrics,
        total_points=0,
        break_points=0,
        plus_minus=2,
    )

    parsed_summary = MatchStatsTotals(
        team_name="USC Münster",
        header_lines=(),
        totals_line="",
        metrics=parsed_metrics,
        players=(parsed_player,),
    )

    manual_metrics = replace(parsed_metrics, serves_attempts=1)
    manual_player = MatchPlayerStats(
        team_name="USC Münster",
        player_name="MOLENAAR Pippa",
        jersey_number=1,
        metrics=manual_metrics,
        total_points=0,
        break_points=0,
        plus_minus=2,
    )

    manual_entries = {
        stats_url: [
            (
                ("usc munster",),
                "USC Münster",
                manual_metrics,
                (manual_player,),
            )
        ]
    }

    monkeypatch.setattr(report_module, "_STATS_TOTALS_CACHE", {})
    monkeypatch.setattr(report_module, "_MANUAL_STATS_TOTALS", None)
    monkeypatch.setattr(
        report_module,
        "_load_manual_stats_totals",
        lambda: manual_entries,
    )

    cache_path = tmp_path / "cache.pdf"
    cache_path.write_bytes(b"dummy")

    monkeypatch.setattr(
        report_module,
        "resolve_stats_pdf_cache_path",
        lambda _url: cache_path,
    )
    monkeypatch.setattr(
        report_module,
        "_parse_stats_totals_pdf",
        lambda _data: (parsed_summary,),
    )

    summaries = fetch_match_stats_totals(stats_url)
    assert len(summaries) == 1

    summary = summaries[0]
    assert summary.players[0].metrics.serves_attempts == 0
    assert summary.players[0].player_name == "MOLENAAR Pippa"
