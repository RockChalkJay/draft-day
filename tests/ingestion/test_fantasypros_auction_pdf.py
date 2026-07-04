import pandas as pd

from src.ingestion.fantasypros_auction_pdf import (
    _cluster,
    _extract_page_rows,
    overall_values,
)


class _FakePage:
    """Minimal stand-in for a pdfplumber Page: extract_words() returns a list
    of {"text", "x0", "top"} dicts, matching the fields the parser reads."""

    def __init__(self, words):
        self._words = words

    def extract_words(self):
        return self._words


def _word(text, x0, top):
    return {"text": text, "x0": x0, "top": top}


def _row_words(rank, name, team, value, col_x0, top, dollar_x0=None):
    """Builds the words for one "N. Name, TEAM   $value" table cell, matching
    FantasyPros' real token boundaries (name/comma glued, team separate,
    dollar sign glued to its number)."""
    dollar_x0 = col_x0 + 77.2 if dollar_x0 is None else dollar_x0
    return [
        _word(f"{rank}.", col_x0, top),
        _word(f"{name},", col_x0 + 6, top),
        _word(team, col_x0 + 6 + len(name) * 1.5, top),
        _word(f"${value}", dollar_x0, top),
    ]


def test_cluster_groups_nearby_values():
    assert _cluster([30, 30, 124, 125, 300], tolerance=8) == [30, 124, 300]


def test_extract_page_rows_two_column_layout():
    words = []
    words += _row_words(1, "Puka Nacua", "LAR", 66, col_x0=30, top=68.1)
    words += _row_words(101, "Jordyn Tyson", "NO", 7, col_x0=124.8, top=68.1)
    words += _row_words(2, "Jahmyr Gibbs", "DET", 61, col_x0=30, top=75.0)
    page = _FakePage(words)

    rows = _extract_page_rows(page, section="Overall")

    assert (1, "Puka Nacua", "LAR", 66, "Overall") in rows
    assert (101, "Jordyn Tyson", "NO", 7, "Overall") in rows
    assert (2, "Jahmyr Gibbs", "DET", 61, "Overall") in rows
    assert len(rows) == 3


def test_extract_page_rows_skips_row_whose_dollar_is_far_from_expected_column():
    # A long name (e.g. "Jacory Croskey-Merritt") can push a row's $ value out
    # of its normal x-position in FantasyPros' own PDF export; that row should
    # be skipped rather than mis-paired with a neighboring value.
    words = _row_words(105, "Jacory Croskey-Merritt", "WAS", 6, col_x0=124.8, top=95.5,
                        dollar_x0=124.8 + 200)  # way outside tolerance
    page = _FakePage(words)

    rows = _extract_page_rows(page, section="Overall")

    assert rows == []


def test_overall_values_prefers_overall_section():
    df = pd.DataFrame([
        {"rank": 26, "player": "Josh Allen", "team": "BUF", "value": 29, "section": "Overall"},
        {"rank": 1, "player": "Josh Allen", "team": "BUF", "value": 27, "section": "Quarterbacks"},
    ])

    result = overall_values(df)

    assert len(result) == 1
    assert result.iloc[0]["value"] == 29


def test_overall_values_falls_back_to_positional_section_when_overall_missing():
    df = pd.DataFrame([
        {"rank": 38, "player": "Jacory Croskey-Merritt", "team": "WAS", "value": 5,
         "section": "Running Backs"},
    ])

    result = overall_values(df)

    assert len(result) == 1
    assert result.iloc[0]["value"] == 5


def test_overall_values_dedupes_by_normalized_name():
    df = pd.DataFrame([
        {"rank": 102, "player": "Patrick Mahomes II", "team": "KC", "value": 6,
         "section": "Overall"},
        {"rank": 11, "player": "Patrick Mahomes II", "team": "KC", "value": 6,
         "section": "Quarterbacks"},
    ])

    result = overall_values(df)

    assert len(result) == 1
