import pandas as pd

from src.ingestion.merge import merge_sources


def make_frame(source, rows):
    return pd.DataFrame(rows).assign(source=source)


def test_merge_combines_two_sources_for_same_player():
    fantasypros = make_frame(
        "fantasypros",
        [{"player_name": "Patrick Mahomes", "team": "KC", "position": "QB", "FPTS": 24.5}],
    )
    sleeper = make_frame(
        "sleeper",
        [{"player_name": "Patrick Mahomes Jr.", "team": "KC", "position": "QB", "injury_status": "Healthy"}],
    )

    merged = merge_sources([fantasypros, sleeper])

    assert len(merged) == 1
    row = merged.iloc[0]
    assert row["fantasypros_FPTS"] == 24.5
    assert row["sleeper_injury_status"] == "Healthy"


def test_merge_keeps_distinct_players_separate():
    fantasypros = make_frame(
        "fantasypros",
        [
            {"player_name": "Patrick Mahomes", "team": "KC", "position": "QB", "FPTS": 24.5},
            {"player_name": "Josh Allen", "team": "BUF", "position": "QB", "FPTS": 23.0},
        ],
    )

    merged = merge_sources([fantasypros])

    assert len(merged) == 2


def test_merge_empty_frames_returns_empty_dataframe():
    assert merge_sources([pd.DataFrame(), pd.DataFrame()]).empty
    assert merge_sources([]).empty


def test_merge_preserves_source_field_literally_named_player_id():
    ffc = make_frame(
        "ffc",
        [{"player_name": "Christian McCaffrey", "team": "SF", "position": "RB", "player_id": 2434, "adp": 1.2}],
    )

    merged = merge_sources([ffc])

    assert len(merged) == 1
    row = merged.iloc[0]
    assert row["ffc_external_player_id"] == 2434
    assert row["player_id"] != 2434
