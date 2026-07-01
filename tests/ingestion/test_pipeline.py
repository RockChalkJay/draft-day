import pandas as pd

from src.ingestion.pipeline import ECR_RANK_COL, ensure_aav


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
