from scripts.report import _format_season_results_section


def _render_details(details):
    payload = {
        "title": "Direkter Vergleich",
        "teams": [
            {"name": "USC Münster", "details": details[0]},
            {"name": "Ladies in Black Aachen", "details": details[1]},
        ],
    }
    return _format_season_results_section(payload, "Ladies in Black Aachen")


def test_direct_comparison_prefers_explicit_label():
    html = _render_details(
        (
            [
                "Spiele: 9",
                "Direkter Vergleich: 4:5",
                "Sätze: 16:18",
            ],
            [
                "Spiele: 9",
                "Direkter Vergleich: 5:4",
                "Sätze: 18:16",
            ],
        )
    )
    assert "Direkter Vergleich: 4:5" in html
    assert "Spiele: 9" not in html


def test_direct_comparison_falls_back_to_wins():
    html = _render_details(
        (
            [
                "Spiele: 9",
                "Siege: 4",
                "Niederlagen: 5",
            ],
            [
                "Spiele: 9",
                "Siege: 5",
                "Niederlagen: 4",
            ],
        )
    )
    assert "Siege: 4" in html
    assert "Spiele: 9" not in html


def test_direct_comparison_uses_score_pattern_as_fallback():
    html = _render_details(
        (
            [
                "Sätze: 16:18",
            ],
            [
                "Sätze: 18:16",
            ],
        )
    )
    assert "Sätze: 16:18" in html

