from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "Scouting"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts import __main__


def test_build_parser_exposes_skip_html_flag():
    parser = __main__.build_parser()
    args = parser.parse_args(["--skip-html"])
    assert args.skip_html is True
    assert isinstance(args.output, __main__.Path)
    assert isinstance(args.data_output, __main__.Path)


def test_build_parser_supports_skip_schedule_download_flag():
    parser = __main__.build_parser()
    args = parser.parse_args(["--skip-schedule-download"])
    assert args.skip_schedule_download is True


def test_build_parser_accepts_combined_csv_output(tmp_path):
    parser = __main__.build_parser()
    target = tmp_path / "players.csv"
    args = parser.parse_args(["--combined-player-csv-output", str(target)])
    assert args.combined_player_csv_output == target
