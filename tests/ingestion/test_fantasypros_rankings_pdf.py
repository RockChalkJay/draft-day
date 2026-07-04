import pandas as pd
import pytest

from src.ingestion.fantasypros_rankings_pdf import parse_lines

STAR = "\uf005" * 5   # SOS star-rating glyphs (private-use area)
INJ = "\uf01a"        # injury-alert icon
DASH = "\u2013"       # en dash standing in for an empty cell


def test_parse_lines_standard_rows_with_tier_carryover():
    lines = [
        "RK PLAYER NAME POS BYE WEEK UPSIDE BUST SOS SEASONECR VS. ADP",
        "Tier 1",
        f"1 Ja'Marr Chase (CIN) WR1 6 {STAR} +2",
        f"2 Bijan Robinson (ATL) RB1 11 {STAR} 0",
        "Tier 2",
        f"3 Puka Nacua (LAR) WR2 11 {STAR} -4",
    ]
    df = parse_lines(lines)

    assert len(df) == 3
    chase = df.iloc[0]
    assert (chase["player"], chase["team"], chase["position"], chase["pos_rank"]) == ("Ja'Marr Chase", "CIN", "WR", 1)
    assert chase["tier"] == 1 and chase["bye"] == 6 and chase["ecr_vs_adp"] == 2
    assert df.iloc[1]["tier"] == 1          # tier carries within the block
    assert df.iloc[2]["tier"] == 2          # ...and advances at the next header
    assert df.iloc[2]["ecr_vs_adp"] == -4   # negative deltas survive


def test_parse_lines_edge_rows():
    lines = [
        "Tier 10",
        "174 Stefon Diggs (FA) WR68 - - -40",                    # FA: no bye, no SOS, real delta
        f"191 Brandon Aubrey (DAL) K1 14 {STAR} -",              # kicker: no delta
        f"160 Houston Texans (HOU) DST1 8 {DASH} {DASH} {STAR} +39",  # DST + empty upside/bust cells
        f"71 Tucker Kraft (GB) {INJ} TE6 11 {STAR} +11",         # inline injury icon
        f"4 Jaxon Smith-Njigba (SEA) WR3 11 {STAR} +1",          # hyphenated name intact
    ]
    df = parse_lines(lines).set_index("rank")

    assert pd.isna(df.loc[174, "bye"]) and df.loc[174, "ecr_vs_adp"] == -40
    assert pd.isna(df.loc[191, "ecr_vs_adp"]) and df.loc[191, "position"] == "K"
    assert df.loc[160, "player"] == "Houston Texans" and df.loc[160, "ecr_vs_adp"] == 39
    assert df.loc[71, "player"] == "Tucker Kraft" and df.loc[71, "position"] == "TE"
    assert df.loc[4, "player"] == "Jaxon Smith-Njigba"


def test_parse_lines_skips_non_player_lines():
    lines = [
        "7/2/26, 11:06 PM 2026 Fantasy Football PPR Rankings | FantasyPros",
        "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php 7/8",
        "Injury Alerts: Q = Questionable, O = Out, IR = Injured Reserve, S = Suspension",
    ]
    assert parse_lines(lines).empty
