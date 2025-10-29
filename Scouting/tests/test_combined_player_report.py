from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "Scouting"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts.combined_player_report import render_combined_player_html


def _write_sample_csv(path: Path) -> None:
    path.write_text(
        """data_sources,match_number,match_id,kickoff,kickoff_comparison,is_home,team,opponent,opponent_comparison,opponent_short,host,host_comparison,location,result_summary,player_name,jersey_number,total_points,break_points,plus_minus,serves_attempts,serves_errors,serves_points,receptions_attempts,receptions_errors,receptions_positive,receptions_perfect,receptions_positive_pct,receptions_perfect_pct,attacks_attempts,attacks_errors,attacks_blocked,attacks_points,attacks_success_pct,blocks_points,stats_url,csv_path
pdf;csv,42,98765,2024-03-18T19:30:00+01:00,"PDF, CSV: 18.03.2024",True,USC Münster,VC Wiesbaden,"PDF, CSV: VC Wiesbaden",Wiesbaden,USC Münster,"PDF, CSV: USC Münster",Halle Berg Fidel,3:1,Max Mustermann,12,18,6,5,22,3,5,18,2,12,6,0.67,0.33,25,4,2,19,0.6,3,https://example.com/stats.pdf,docs/data/csv/sample.csv
""",
        encoding="utf-8",
    )


def test_render_combined_player_html(tmp_path: Path) -> None:
    csv_path = tmp_path / "combined.csv"
    _write_sample_csv(csv_path)

    html = render_combined_player_html(csv_path=csv_path)

    assert "Kombinierte Spielerinnen-Statistiken" in html
    assert "USC Münster" in html
    assert "Max Mustermann" in html
    assert "PDF, CSV: USC Münster" in html
    assert "60.0%" in html  # formatted percentage from attacks_success_pct
    assert "href=\"https://example.com/stats.pdf\"" in html
