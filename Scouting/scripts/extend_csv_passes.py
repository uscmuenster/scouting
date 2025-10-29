"""Utilities to extend VBL CSV exports with derived passing statistics."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

POSITIVE_PASS_CANDIDATES: Tuple[str, ...] = (
    "Positive Pass Percentage (Pos%)",
    "Positive Pass Percentage",
)
PERFECT_PASS_CANDIDATES: Tuple[str, ...] = (
    "Excellent/ Perfect Pass Percentage (Exc.%)",
    "Excellent/ Perfect Pass Percentage",
)


def parse_decimal(value: str) -> Decimal | None:
    """Parse a numeric string into :class:`Decimal`.

    Empty strings, ``"-"`` and ``"."`` are treated as missing values and result in
    ``None``. Percent symbols are ignored. Numbers using a comma as decimal separator
    are supported.
    """
    cleaned = value.strip()
    if not cleaned or cleaned in {"-", "."}:
        return None

    cleaned = cleaned.replace("%", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def compute_pass_value(total_receptions: str, percentage: str) -> str:
    """Return the derived pass value rounded to the nearest integer.

    Missing values are represented with ``"-"`` to match the raw CSV files.
    """
    receptions = parse_decimal(total_receptions)
    percent = parse_decimal(percentage)

    if receptions is None or percent is None:
        return "-"

    value = (receptions * percent) / Decimal("100")
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return str(int(rounded))


def extend_row(
    row: List[str],
    total_receptions_idx: int,
    positive_percentage_idx: int,
    perfect_percentage_idx: int,
) -> List[str]:
    """Insert the derived pass values into ``row``."""
    insert_at = total_receptions_idx + 1
    positive_pass = compute_pass_value(row[total_receptions_idx], row[positive_percentage_idx])
    perfect_pass = compute_pass_value(row[total_receptions_idx], row[perfect_percentage_idx])
    return row[:insert_at] + [positive_pass, perfect_pass] + row[insert_at:]


def resolve_column_index(
    header: Sequence[str], candidates: Sequence[str], file_name: str
) -> int:
    for column in candidates:
        if column in header:
            return header.index(column)
    raise ValueError(
        f"Missing any of the expected columns {candidates!r} in {file_name}"
    )


def extend_csv(input_path: Path, output_path: Path) -> None:
    """Create an extended CSV file with derived passing statistics."""
    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.reader(input_file)
        try:
            header = next(reader)
        except StopIteration:  # pragma: no cover - guard against empty files
            header = []
            rows: Iterable[List[str]] = []
        else:
            rows = list(reader)

    extendable = bool(header) and "Total Receptions" in header
    if extendable:
        try:
            total_receptions_idx = header.index("Total Receptions")
            positive_idx = resolve_column_index(
                header, POSITIVE_PASS_CANDIDATES, input_path.name
            )
            perfect_idx = resolve_column_index(
                header, PERFECT_PASS_CANDIDATES, input_path.name
            )
        except ValueError:
            extendable = False

    if extendable:
        insert_at = total_receptions_idx + 1
        extended_header = header[:insert_at] + ["Positive Pass", "Perfect Pass"] + header[insert_at:]
        extended_rows = [
            extend_row(row, total_receptions_idx, positive_idx, perfect_idx)
            for row in rows
        ]
    else:
        extended_header = header
        extended_rows = list(rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        if extended_header:
            writer.writerow(extended_header)
        writer.writerows(extended_rows)


def extend_directory(input_dir: Path, output_dir: Path) -> None:
    """Extend all CSV files in ``input_dir`` and write them to ``output_dir``."""
    for csv_file in sorted(input_dir.glob("*.csv")):
        extend_csv(csv_file, output_dir / csv_file.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_root / "docs" / "data" / "csv",
        help="Directory containing the source CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_root / "docs" / "data" / "csv_erweitert",
        help="Target directory for the extended CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extend_directory(args.input_dir, args.output_dir)


if __name__ == "__main__":  # pragma: no cover
    main()
