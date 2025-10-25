from scripts.report import _parse_match_stats_metrics


def test_parse_match_stats_metrics_handles_keyword_totals() -> None:
    parts = [
        "Punkte 75 33 +23",
        "Aufschlag 105 19 14",
        "Annahme 88 15 30% ( 15%)",
        "Angriff 132 10 8 52 39%",
        "Block 9",
    ]
    metrics = _parse_match_stats_metrics(" ".join(parts))

    assert metrics.serves_attempts == 105
    assert metrics.serves_errors == 19
    assert metrics.serves_points == 14
    assert metrics.receptions_attempts == 88
    assert metrics.receptions_errors == 15
    assert metrics.receptions_positive_pct == "30%"
    assert metrics.receptions_perfect_pct == "15%"
    assert metrics.attacks_attempts == 132
    assert metrics.attacks_errors == 10
    assert metrics.attacks_blocked == 8
    assert metrics.attacks_points == 52
    assert metrics.attacks_success_pct == "39%"
    assert metrics.blocks_points == 9
