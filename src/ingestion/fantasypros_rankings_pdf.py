"""
Parses a saved/printed FantasyPros cheat-sheet rankings page (e.g. "2026
Fantasy Football PPR Rankings ... | FantasyPros.pdf", printed from
https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php) into a
per-player table of the sheet's overall rank, expert tier, positional rank,
bye week, and ECR-vs-ADP delta.

Like the auction-values importer (fantasypros_auction_pdf.py), this exists so
the app can be re-armed each season with zero code changes: print the season's
cheat sheet to PDF, run the importer, and the board's ECR/tier/bye data comes
from your locked sheet instead of the bundled sample or a live fetch.

    python -m src.ingestion.fantasypros_rankings_pdf path/to/rankings.pdf

writes data/rankings_tiers.csv, which the pipeline applies automatically
(see README).
"""

import argparse
import os
import re
import sys

import pandas as pd

# Row grammar after glyph cleanup:  RK Name (TEAM) POSn BYE <trailing tokens>
# e.g. "1 Ja'Marr Chase (CIN) WR1 6 +2", "174 Stefon Diggs (FA) WR68 - - -40"
#      (FA row: bye "-", no-SOS "-", delta -40), "191 Brandon Aubrey (DAL) K1 14 -".
# Empty cells render as bare "-" tokens, so everything after BYE is captured
# loosely and the ECR-vs-ADP delta is taken from the last numeric token.
ROW_RE = re.compile(
    r"^(?P<rank>\d+)\s+(?P<name>.+?)\s+\((?P<team>[A-Z]{2,3})\)\s+"
    r"(?P<pos>QB|RB|WR|TE|K|DST)(?P<pos_rank>\d+)\s+(?P<bye>\d+|-)"
    r"(?P<rest>(?:\s+(?:-|[+-]?\d+))*)\s*$"
)
TIER_RE = re.compile(r"^Tier (\d+)$")

# Non-text glyphs FantasyPros renders inline: private-use-area icons (the SOS
# star rating, injury alerts) and en/em dashes standing in for empty
# Upside/Bust cells. ASCII hyphens are NOT stripped -- they carry meaning
# (negative deltas, hyphenated names, "-" placeholders the row grammar reads).
GLYPH_RE = re.compile("[\uf000-\uf8ff\u2013\u2014]")


def parse_lines(lines) -> pd.DataFrame:
    """Parse extracted text lines into one row per player. The current "Tier N"
    header is carried forward onto every player row until the next header (tier
    state persists across page breaks -- the sheet only prints a header where
    the tier changes)."""
    rows = []
    tier = None
    for raw in lines:
        line = GLYPH_RE.sub(" ", raw)
        line = re.sub(r"\s+", " ", line).strip()

        tier_match = TIER_RE.match(line)
        if tier_match:
            tier = int(tier_match.group(1))
            continue

        m = ROW_RE.match(line)
        if not m:
            continue
        trailing = [t for t in m.group("rest").split() if t != "-"]
        rows.append({
            "rank": int(m.group("rank")),
            "player": m.group("name"),
            "team": m.group("team"),
            "position": m.group("pos"),
            "pos_rank": int(m.group("pos_rank")),
            "tier": tier,
            "bye": int(m.group("bye")) if m.group("bye") != "-" else None,
            "ecr_vs_adp": int(trailing[-1]) if trailing else None,
        })
    return pd.DataFrame(rows)


def parse_rankings_pdf(pdf_path) -> pd.DataFrame:
    import pdfplumber

    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").splitlines())
    df = parse_lines(lines)

    if not df.empty:
        # The sheet is one contiguous overall ranking; a gap in RK means a page
        # parsed wrong -- fail loudly rather than write a silently-partial override.
        expected = set(range(1, int(df["rank"].max()) + 1))
        missing = expected - set(df["rank"])
        if missing:
            raise ValueError(
                f"Rankings PDF parsed with gaps at overall ranks {sorted(missing)[:10]}"
                f"{'...' if len(missing) > 10 else ''} -- layout may have changed."
            )
    return df


def write_rankings_csv(pdf_path, out_path):
    df = parse_rankings_pdf(pdf_path)
    df.to_csv(out_path, index=False)
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to a printed FantasyPros cheat-sheet rankings PDF")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "data", "rankings_tiers.csv"),
        help="Output CSV path (default: data/rankings_tiers.csv)",
    )
    args = parser.parse_args()

    try:
        df = write_rankings_csv(args.pdf_path, args.out)
    except ValueError as e:
        print(f"Parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    n_tiers = int(df["tier"].max()) if df["tier"].notna().any() else 0
    print(f"Wrote {len(df)} players ({n_tiers} tiers) to {os.path.abspath(args.out)}")
