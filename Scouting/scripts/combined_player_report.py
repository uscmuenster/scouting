"""Render an HTML dashboard for the combined player statistics CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from zoneinfo import ZoneInfo

from .combined_csv import FIELD_ORDER

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_COMBINED_CSV_PATH = BASE_DIR / "docs" / "data" / "combined_player_stats.csv"
DEFAULT_HTML_OUTPUT_PATH = BASE_DIR / "docs" / "index3.html"
BERLIN_TZ = ZoneInfo("Europe/Berlin")


COLUMN_LABELS: Mapping[str, str] = {
    "data_sources": "Quellen",
    "kickoff": "Anpfiff",
    "kickoff_comparison": "Datum (PDF/CSV)",
    "team": "Team",
    "opponent": "Gegner",
    "opponent_comparison": "Gegner (PDF/CSV)",
    "opponent_short": "Gegner (kurz)",
    "host": "Ausrichter",
    "host_comparison": "Ausrichter (PDF/CSV)",
    "result_summary": "Ergebnis",
    "player_name": "Spielerin",
    "jersey_number": "Rückennr.",
    "total_points": "Gesamtpunkte",
    "break_points": "Breakpunkte",
    "plus_minus": "+/-",
    "serves_attempts": "Aufschläge (Versuche)",
    "serves_errors": "Aufschlagfehler",
    "serves_points": "Aufschlagpunkte",
    "receptions_attempts": "Annahmen (Versuche)",
    "receptions_errors": "Annahmefehler",
    "receptions_positive": "Positive Annahmen",
    "receptions_perfect": "Perfekte Annahmen",
    "receptions_positive_pct": "Positive %",
    "receptions_perfect_pct": "Perfekte %",
    "attacks_attempts": "Angriffe (Versuche)",
    "attacks_errors": "Angriffsfehler",
    "attacks_blocked": "Geblockt",
    "attacks_points": "Angriffspunkte",
    "attacks_success_pct": "Angriffsquote",
    "blocks_points": "Blockpunkte",
    "stats_url": "Statistik-Link",
    "csv_path": "CSV-Datei",
}

VISIBLE_FIELDS: Sequence[str] = tuple(
    field for field in FIELD_ORDER if field in COLUMN_LABELS
)


def load_combined_player_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Combined CSV not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = {key: (value or "") for key, value in raw_row.items()}
            rows.append(row)
    return rows


def _format_boolean(value: str) -> str:
    text = value.strip().lower()
    if text in {"true", "1", "yes", "ja"}:
        return "Ja"
    if text in {"false", "0", "no", "nein"}:
        return "Nein"
    return value


def _format_percentage(value: str) -> str:
    text = value.strip().replace("%", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return value
    if number <= 1 and not text.strip().endswith("%"):
        number *= 100
    return f"{number:.1f}%"


def _format_datetime(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return value
    if dt.tzinfo is not None:
        dt = dt.astimezone(BERLIN_TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_cell(field: str, value: str) -> str:
    if not value:
        return ""

    if field == "is_home":
        return _format_boolean(value)
    if field == "kickoff":
        return _format_datetime(value)
    if field.endswith("_pct"):
        return _format_percentage(value)
    if field == "data_sources":
        return value.replace(";", ", ")
    if field == "stats_url":
        return value
    return value


def render_table_rows(rows: Iterable[Mapping[str, str]]) -> str:
    cells: list[str] = []
    for row in rows:
        row_cells: list[str] = []
        for field in VISIBLE_FIELDS:
            raw_value = row.get(field, "")
            formatted = format_cell(field, raw_value)
            if field == "stats_url" and formatted:
                url = escape(raw_value, quote=True)
                label = "PDF"
                formatted_html = (
                    f'<a href="{url}" target="_blank" rel="noopener">{escape(label)}</a>'
                )
            else:
                formatted_html = escape(formatted)
            row_cells.append(f"<td>{formatted_html}</td>")
        cells.append("<tr>" + "".join(row_cells) + "</tr>")
    return "\n".join(cells)


def render_combined_player_html(*, csv_path: Path) -> str:
    rows = load_combined_player_rows(csv_path)
    generated_at = datetime.now(tz=BERLIN_TZ)
    row_count = len(rows)
    table_rows = render_table_rows(rows)
    header_cells = "".join(
        f"<th>{escape(COLUMN_LABELS[field])}</th>" for field in VISIBLE_FIELDS
    )
    if csv_path.is_absolute():
        try:
            relative_path = csv_path.relative_to(BASE_DIR)
        except ValueError:
            relative_path = csv_path
    else:
        relative_path = csv_path
    return f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Scouting Übersicht – Kombinierte Spielerinnen-Statistiken</title>
  <link rel=\"icon\" type=\"image/png\" sizes=\"32x32\" href=\"favicon.png\">
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7f9;
      --fg: #0f172a;
      --accent: #0f766e;
      --muted: #475569;
      --card-bg: #ffffff;
      --card-border: rgba(15, 118, 110, 0.18);
      --shadow: 0 16px 34px rgba(15, 118, 110, 0.12);
      --table-stripe: rgba(14, 116, 144, 0.08);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1f24;
        --fg: #e2f1f4;
        --accent: #5eead4;
        --muted: #cbd5f5;
        --card-bg: #132a30;
        --card-border: rgba(94, 234, 212, 0.28);
        --shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
        --table-stripe: rgba(94, 234, 212, 0.12);
      }}
    }}
    body {{
      margin: 0;
      font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--fg);
      line-height: 1.6;
    }}
    header {{
      padding: clamp(1.8rem, 4vw, 2.6rem) clamp(1.2rem, 4vw, 2.8rem);
      display: grid;
      gap: 0.6rem;
      background: var(--card-bg);
      border-bottom: 1px solid var(--card-border);
      box-shadow: var(--shadow);
    }}
    header h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 2.6rem);
      letter-spacing: -0.01em;
    }}
    header p {{
      margin: 0;
      color: var(--muted);
      max-width: 50ch;
    }}
    main {{
      max-width: 100rem;
      margin: 0 auto;
      padding: clamp(1.2rem, 3vw, 2.2rem) clamp(1rem, 4vw, 3rem);
      display: grid;
      gap: clamp(1.4rem, 3vw, 2.4rem);
    }}
    .meta {{
      display: grid;
      gap: 0.8rem;
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 1rem;
      padding: clamp(0.9rem, 3vw, 1.3rem);
      box-shadow: var(--shadow);
    }}
    .meta div {{
      display: grid;
      gap: 0.2rem;
    }}
    .meta span {{
      font-weight: 600;
      color: var(--accent);
    }}
    .table-wrapper {{
      border-radius: 1rem;
      overflow-x: auto;
      overflow-y: hidden;
      background: rgba(15, 23, 42, 0.92);
      box-shadow: 0 20px 45px rgba(15, 23, 42, 0.55);
      -webkit-overflow-scrolling: touch;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1200px;
    }}
    thead th {{
      text-align: left;
      padding: 0.85rem 1rem;
      font-size: 0.85rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      color: var(--accent);
      background: rgba(15, 118, 110, 0.14);
      border-bottom: 1px solid var(--card-border);
      position: sticky;
      top: 0;
      backdrop-filter: blur(6px);
      z-index: 1;
    }}
    tbody td {{
      padding: 0.8rem 1rem;
      border-top: 1px solid var(--card-border);
      font-size: 0.92rem;
      color: var(--fg);
      vertical-align: top;
    }}
    tbody tr:nth-child(even) td {{
      background: var(--table-stripe);
    }}
    a {{
      color: var(--accent);
      font-weight: 600;
      text-decoration: none;
    }}
    a:hover, a:focus {{
      text-decoration: underline;
    }}
    @media (max-width: 1024px) {{
      header {{
        border-radius: 0;
      }}
      table {{
        min-width: 900px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Kombinierte Spielerinnen-Statistiken</h1>
    <p>Zusammenführung aus PDF- und CSV-Quellen. Jede Zeile entspricht einer Spielerin pro Spiel.</p>
  </header>
  <main>
    <section class=\"meta\">
      <div><span>Aktualisiert</span><div>{generated_at.strftime("%d.%m.%Y %H:%M:%S")} Uhr</div></div>
      <div><span>Einträge</span><div>{row_count}</div></div>
      <div><span>Quelle</span><div>{escape(str(relative_path))}</div></div>
    </section>
    <div class=\"table-wrapper\">
      <table>
        <thead>
          <tr>{header_cells}</tr>
        </thead>
        <tbody>
{table_rows}
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>"""


def generate_combined_player_html(
    *, csv_path: Path = DEFAULT_COMBINED_CSV_PATH, output_path: Path = DEFAULT_HTML_OUTPUT_PATH
) -> Path:
    html = render_combined_player_html(csv_path=csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the combined player statistics HTML dashboard."
    )
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_COMBINED_CSV_PATH, help="Path to the combined player CSV."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_HTML_OUTPUT_PATH,
        help="Target HTML output path (default: docs/index3.html).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    generate_combined_player_html(csv_path=args.csv, output_path=args.output)
    print(f"Combined player HTML dashboard generated -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
