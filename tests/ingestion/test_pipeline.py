import pandas as pd
import pytest

from src.ingestion.merge import merge_sources
from src.ingestion.pipeline import ECR_RANK_COL, ensure_aav


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


def test_existing_aav_is_preserved():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB", "aav": 55, ECR_RANK_COL: 1}])
    out = ensure_aav(df)
    assert out["aav"].iloc[0] == 55  # untouched market feed


def test_aav_synthesized_from_ecr_rank():
    rows = [{"player_id": f"p{i}", "position": "RB", ECR_RANK_COL: i + 1} for i in range(60)]
    out = ensure_aav(pd.DataFrame(rows))
    assert "aav" in out.columns
    # Monotonic in rank: the consensus #1 is worth more than a late pick.
    assert out["aav"].iloc[0] > out["aav"].iloc[40]
    assert out["aav"].iloc[0] > 1


def test_kdst_get_zero_aav_when_synthesized():
    rows = [{"player_id": "rb", "position": "RB", ECR_RANK_COL: 1},
            {"player_id": "k", "position": "K", ECR_RANK_COL: 150},
            {"player_id": "dst", "position": "DST", ECR_RANK_COL: 160}]
    out = ensure_aav(pd.DataFrame(rows))
    assert out.set_index("player_id").loc["k", "aav"] == 0
    assert out.set_index("player_id").loc["dst", "aav"] == 0


def test_missing_ecr_column_yields_zero_aav():
    out = ensure_aav(pd.DataFrame([{"player_id": "p0", "position": "RB"}]))
    assert out["aav"].iloc[0] == 0
