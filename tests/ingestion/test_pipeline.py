import pandas as pd
import pytest

from src.ingestion.merge import merge_sources
from src.ingestion.pipeline import _derive_context_stats, _injury_risk, _join_vegas


def _fp_position_frame(position, rows):
    return pd.DataFrame(rows).assign(position=position, source="fantasypros")


def test_same_source_position_frames_must_be_concatenated_before_merge():
    # FantasyPros returns one frame per position, all source="fantasypros", and
    # RB/WR/TE share stat columns (RECEIVING_*). merge_sources keys columns by
    # source, so passing the frames separately collides on the shared prefixed
    # columns -- the exact bug that silently forced the live pull to fall back to
    # the sample. fetch_live must concat them into one frame first.
    rb = _fp_position_frame("RB", [{"player_name": "Bijan Robinson", "team": "ATL",
                                     "RUSHING_YDS": 1200, "RECEIVING_REC": 50}])
    wr = _fp_position_frame("WR", [{"player_name": "Ja'Marr Chase", "team": "CIN",
                                    "RECEIVING_REC": 100, "RECEIVING_YDS": 1400}])

    with pytest.raises(ValueError):
        merge_sources([rb, wr])

    merged = merge_sources([pd.concat([rb, wr], ignore_index=True)])
    assert len(merged) == 2
    assert "fantasypros_RUSHING_YDS" in merged.columns
    assert "fantasypros_RECEIVING_YDS" in merged.columns


def test_injury_risk_tiers_from_history():
    df = pd.DataFrame([
        {"player_id": "durable", "nflverse_injuries_weeks_out_or_doubtful": 0,
         "nflverse_injuries_seasons_with_injury_report": 3},   # 0/season -> Low
        {"player_id": "some", "nflverse_injuries_weeks_out_or_doubtful": 6,
         "nflverse_injuries_seasons_with_injury_report": 3},    # 2/season -> Med
        {"player_id": "fragile", "nflverse_injuries_weeks_out_or_doubtful": 12,
         "nflverse_injuries_seasons_with_injury_report": 3},    # 4/season -> High
        {"player_id": "rookie"},                                # no history -> blank
    ])
    risk = dict(zip(df["player_id"], _injury_risk(df)))
    assert risk == {"durable": "Low", "some": "Med", "fragile": "High", "rookie": ""}


def test_vegas_joined_by_team():
    df = pd.DataFrame([
        {"player_id": "a", "player_name": "A", "team": "SF", "position": "RB"},
        {"player_id": "b", "player_name": "B", "team": "CHI", "position": "WR"},
    ])

    class _FakeVegas:
        def fetch(self, seasons=None):
            return pd.DataFrame({"team": ["SF", "CHI"], "vegas_implied_team_total": [27.5, 19.0]})

    import src.ingestion.pipeline as pipe
    orig = pipe.VegasFetcher
    pipe.VegasFetcher = _FakeVegas
    try:
        out = _join_vegas(df)
    finally:
        pipe.VegasFetcher = orig
    assert out.set_index("player_id").loc["a", "vegas_implied_team_total"] == 27.5
    assert out.set_index("player_id").loc["b", "vegas_implied_team_total"] == 19.0


def test_derive_context_stats_flattens_source_columns():
    df = pd.DataFrame([{
        "player_id": "a", "position": "WR",
        "nflverse_target_share": 0.24,
        "vegas_implied_team_total": 25.5,
        "nflverse_injuries_weeks_out_or_doubtful": 1,
        "nflverse_injuries_seasons_with_injury_report": 2,
    }])
    out = _derive_context_stats(df)
    row = out.iloc[0]
    assert row["target_share"] == 0.24
    assert row["team_total"] == 25.5
    assert row["injury_risk"] in {"Low", "Med", "High"}
