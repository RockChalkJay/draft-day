"""
Parses FantasyPros' "Cheat Sheet: Positional Rankings" PDF (the free auction
Draft Wizard export, e.g. https://www.fantasypros.com/nfl/rankings/auction-values.php
"Download PDF") into a player -> auction-dollar-value table.

FantasyPros republishes this same two-column, rank-dot-name-comma-team-dollar
layout every season, so this parser is meant to be reused year over year: drop
next season's PDF in and re-run, no code changes expected. If FantasyPros
changes the export's layout, `_extract_page_rows` is the one place to adjust.

Usage (regenerates the override the app already reads automatically --
see README's `data/auction_values.csv` note):

    python -m src.ingestion.fantasypros_auction_pdf path/to/cheat_sheet.pdf
"""

import argparse
import os
import re
import sys
from collections import defaultdict

import pandas as pd

from src.ingestion.id_mapping import normalize_name

ROW_RE = re.compile(r"^(\d+)\.\s*(.+?),\s*([A-Z]{2,3})$")

LINE_TOLERANCE = 3  # px; words within this vertical band belong to one row
COLUMN_TOLERANCE = 8  # px; rank-marker x0's within this band are one column
DOLLAR_COLUMN_OFFSET = 77.2  # px from a column's rank markers to its $ values
DOLLAR_MATCH_TOLERANCE = 6  # px; how close a $ token must sit to that offset

SECTION_HEADERS = {
    "overall",
    "quarterbacks",
    "running backs",
    "wide receivers",
    "tight ends",
    "kickers",
    "defenses/special teams",
    "dbs",
}


def _cluster(sorted_values, tolerance):
    """Groups sorted numbers into buckets where consecutive gaps are small,
    returning each bucket's minimum as its representative."""
    clusters = []
    for v in sorted_values:
        if clusters and v - clusters[-1][-1] < tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [min(c) for c in clusters]


def _current_section(page_text):
    for line in page_text.splitlines():
        if line.strip().lower() in SECTION_HEADERS:
            return line.strip()
    return "Overall"


def _extract_page_rows(page, section):
    """Returns a list of (rank, name, team, value) tuples found on one page.

    FantasyPros lays each page out as 1-6 side-by-side rank columns, each with
    its own "N. Name, TEAM" text and a $ value column offset a fixed distance
    to its right. Long names occasionally push a row's $ value out of its
    normal x-position (a rendering quirk in FantasyPros' own PDF export, not
    an artifact of this parser); rows where no $ token lands close enough to
    the expected column position are skipped rather than guessed at.
    """
    words = page.extract_words()
    words.sort(key=lambda w: (w["top"], w["x0"]))

    lines, current, current_top = [], [], None
    for w in words:
        if current_top is None or abs(w["top"] - current_top) < LINE_TOLERANCE:
            current.append(w)
            current_top = w["top"] if current_top is None else current_top
        else:
            lines.append(current)
            current, current_top = [w], w["top"]
    if current:
        lines.append(current)

    rank_marker_x0s = sorted(
        {round(w["x0"]) for line in lines for w in line if re.match(r"^\d+\.$", w["text"])}
    )
    column_starts = _cluster(rank_marker_x0s, COLUMN_TOLERANCE)
    if not column_starts:
        return []

    def column_for(x0):
        best = column_starts[0]
        for cs in column_starts:
            if cs - 3 <= x0:
                best = cs
        return best

    rows = []
    for line in lines:
        by_column = defaultdict(list)
        for w in line:
            by_column[column_for(w["x0"])].append(w)
        for cs, words_in_cell in by_column.items():
            words_in_cell.sort(key=lambda w: w["x0"])
            dollar_words = [w for w in words_in_cell if w["text"].startswith("$")]
            text_words = [w for w in words_in_cell if not w["text"].startswith("$")]
            match = ROW_RE.match(" ".join(w["text"] for w in text_words))
            if not match:
                continue
            rank, name, team = int(match.group(1)), match.group(2), match.group(3)
            expected_x = cs + DOLLAR_COLUMN_OFFSET
            best_dollar, best_dist = None, None
            for dw in dollar_words:
                dist = abs(dw["x0"] - expected_x)
                if best_dist is None or dist < best_dist:
                    best_dollar, best_dist = dw, dist
            if best_dollar is None or best_dist > DOLLAR_MATCH_TOLERANCE:
                continue
            rows.append((rank, name, team, int(best_dollar["text"].lstrip("$")), section))
    return rows


def parse_auction_values(pdf_path) -> pd.DataFrame:
    """Parses every section of the cheat-sheet PDF into one row per
    (section, rank) entry. Columns: rank, player, team, value, section.

    The same player appears in multiple sections (once in "Overall", once in
    their position's own section); use `overall_values()` to reduce this to
    one row per player.
    """
    import pdfplumber

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            section = _current_section(page.extract_text() or "")
            all_rows.extend(_extract_page_rows(page, section))

    return pd.DataFrame(all_rows, columns=["rank", "player", "team", "value", "section"])


def overall_values(df: pd.DataFrame) -> pd.DataFrame:
    """Reduces parse_auction_values' output to one row per player: prefers the
    'Overall' section (the single-currency, full-pool auction value) and only
    falls back to a positional section's value for players missing there
    (e.g. a name skipped in Overall due to the PDF's own rendering quirk)."""
    if df.empty:
        return df

    df = df.copy()
    df["_key"] = df["player"].map(normalize_name)
    df["_priority"] = (df["section"].str.lower() != "overall").astype(int)
    df = df.sort_values(["_key", "_priority"])
    deduped = df.drop_duplicates(subset="_key", keep="first")
    return deduped[["player", "team", "value", "section"]].reset_index(drop=True)


def write_override_csv(pdf_path, out_path):
    parsed = parse_auction_values(pdf_path)
    result = overall_values(parsed)
    result[["player", "value"]].to_csv(out_path, index=False)

    unique_players = parsed["player"].map(normalize_name).nunique() if not parsed.empty else 0
    skipped = unique_players - len(result)
    return result, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to FantasyPros' cheat-sheet PDF")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "data", "auction_values.csv"),
        help="Output CSV path (default: data/auction_values.csv)",
    )
    args = parser.parse_args()

    result, skipped = write_override_csv(args.pdf_path, args.out)
    print(f"Wrote {len(result)} player values to {os.path.abspath(args.out)}")
    if skipped:
        print(
            f"({skipped} player(s) had no cleanly-parseable value in the PDF and were left "
            "out -- the app will fall back to its own computed Value for them.)",
            file=sys.stderr,
        )
