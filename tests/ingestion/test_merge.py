import pandas as pd

from src.ingestion.merge import merge_sources


def make_frame(source, rows):
    return pd.DataFrame(rows).assign(source=source)


def test_merge_combines_two_sources_for_same_player():
    fantasypros = make_frame(
        "fantasypros",
        [{"player_name": "Patrick Mahomes", "team": "KC", "position": "QB", "FPTS": 24.5}],
    )
    ecr = make_frame(
        "fantasypros_ecr",
        [{"player_name": "Patrick Mahomes Jr.", "team": "KC", "position": "QB", "rank_ecr": 40}],
    )

    merged = merge_sources([fantasypros, ecr])

    assert len(merged) == 1
    row = merged.iloc[0]
    assert row["fantasypros_FPTS"] == 24.5
    assert row["fantasypros_ecr_rank_ecr"] == 40


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


def test_merge_overwrites_source_field_literally_named_player_id():
    # merge_sources owns the player_id column (canonical name+position id); a
    # source's own field by that name is overwritten, not preserved. Enrichment
    # sources with real external ids (e.g. FFC) never pass through here -- they
    # join via _left_join_by_player with an explicit column keep-list.
    src = make_frame(
        "somesource",
        [{"player_name": "Christian McCaffrey", "team": "SF", "position": "RB", "player_id": 2434, "adp": 1.2}],
    )

    merged = merge_sources([src])

    assert len(merged) == 1
    assert merged.iloc[0]["player_id"] == "christianmccaffrey_rb"
