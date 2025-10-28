"""Tests for the VBL statistics scraper helpers."""

from __future__ import annotations

from typing import Dict

from scripts.statsvbl import (
    collect_vbl_match_leg_results,
    parse_competition_matches_html,
    parse_leg_list_html,
)


COMPETITION_HTML = """
<html>
  <body>
    <table id="matches">
      <thead>
        <tr>
          <th>Nr</th>
          <th>Datum</th>
          <th>Zeit</th>
          <th>Heim</th>
          <th>Gast</th>
          <th>Ergebnis</th>
          <th>Sätze</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>102</td>
          <td>17.02.2024</td>
          <td>19:00</td>
          <td>USC Münster</td>
          <td>Dresdner SC</td>
          <td>3 - 2</td>
          <td>25-22, 23-25, 25-23, 19-25, 15-12</td>
          <td>
            <a href="MatchStatistics.aspx?mID=11835&ID=185&CID=228&PID=209&type=LegList">LegList</a>
            <a href="MatchStatistics.aspx?mID=11835&ID=185&PID=209&type=Summary">Summary</a>
          </td>
        </tr>
        <tr>
          <td>101</td>
          <td>10.02.2024</td>
          <td>19:30</td>
          <td>USC Münster</td>
          <td>NawaRo Straubing</td>
          <td>3 - 0</td>
          <td>25-21, 25-19, 25-18</td>
          <td>
            <a href="MatchStatistics.aspx?mID=11832&ID=185&CID=228&PID=209&type=LegList">LegList</a>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


LEG_LIST_HTML = """
<html>
  <body>
    <table class="leg-list">
      <thead>
        <tr>
          <th>Satz</th>
          <th>Heimteam</th>
          <th>Spielstand</th>
          <th>Gastteam</th>
          <th>Dauer</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>1</td>
          <td>USC Münster</td>
          <td>25 - 22</td>
          <td>Dresdner SC</td>
          <td>00:25</td>
        </tr>
        <tr>
          <td>2</td>
          <td>USC Münster</td>
          <td>23 - 25</td>
          <td>Dresdner SC</td>
          <td>00:27</td>
        </tr>
        <tr>
          <td>3</td>
          <td>USC Münster</td>
          <td>25 - 23</td>
          <td>Dresdner SC</td>
          <td>00:26</td>
        </tr>
        <tr>
          <td>4</td>
          <td>USC Münster</td>
          <td>19 - 25</td>
          <td>Dresdner SC</td>
          <td>00:28</td>
        </tr>
        <tr>
          <td>5</td>
          <td>USC Münster</td>
          <td>15 - 12</td>
          <td>Dresdner SC</td>
          <td>00:18</td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_competition_matches_html_extracts_basic_fields() -> None:
    matches = parse_competition_matches_html(COMPETITION_HTML, base_url="https://example.com")
    assert len(matches) == 2
    first = matches[0]
    assert first.match_id == "11835"
    assert first.match_number == "102"
    assert first.home_team == "USC Münster"
    assert first.away_team == "Dresdner SC"
    assert first.result == "3 - 2"
    assert first.set_results.startswith("25-22")
    assert first.leg_list_url == (
        "https://example.com/MatchStatistics.aspx?mID=11835&ID=185&CID=228&PID=209&type=LegList"
    )


def test_parse_leg_list_html_extracts_sets() -> None:
    legs = parse_leg_list_html(LEG_LIST_HTML)
    assert len(legs) == 5
    first = legs[0]
    assert first.set_number == 1
    assert first.home_points == 25
    assert first.away_points == 22
    assert first.duration == "00:25"
    assert first.home_label == "USC Münster"
    assert first.away_label == "Dresdner SC"


def test_collect_vbl_match_leg_results_combines_matches_and_leg_lists() -> None:
    leg_html_by_match: Dict[str, str] = {
        "11835": LEG_LIST_HTML,
        "11832": """
        <html>
          <body>
            <table>
              <tr><th>Set</th><th>Home</th><th>Away</th><th>Score</th></tr>
              <tr><td>1</td><td>USC Münster</td><td>NawaRo Straubing</td><td>25-21</td></tr>
              <tr><td>2</td><td>USC Münster</td><td>NawaRo Straubing</td><td>25-19</td></tr>
              <tr><td>3</td><td>USC Münster</td><td>NawaRo Straubing</td><td>25-18</td></tr>
            </table>
          </body>
        </html>
        """,
    }

    payload = collect_vbl_match_leg_results(
        competition_id="185",
        phase_id="209",
        club_id="228",
        base_url="https://example.com",
        match_fetcher=lambda url: COMPETITION_HTML,
        leg_fetcher=lambda match, url: leg_html_by_match[match.match_id],
    )

    assert payload["match_count"] == 2
    assert payload["competition_id"] == "185"
    assert payload["phase_id"] == "209"
    matches = payload["matches"]
    assert len(matches) == 2

    first = matches[0]
    assert first["match_id"] == "11835"
    assert first["home_sets"] == 3
    assert first["away_sets"] == 2
    assert first["set_scores"] == "25-22, 23-25, 25-23, 19-25, 15-12"
    assert first["has_leg_data"] is True

    second = matches[1]
    assert second["match_id"] == "11832"
    assert second["home_sets"] == 3
    assert second["away_sets"] == 0
    assert second["set_scores"] == "25-21, 25-19, 25-18"

