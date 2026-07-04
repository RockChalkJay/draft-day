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


def test_derive_draft_market_fields_prefers_espn_then_ffc():
    from src.ingestion.pipeline import _derive_draft_market_fields

    df = pd.DataFrame([
        # ESPN ADP present: wins over FFC; delta derived from ECR.
        {"player_name": "A", "fantasypros_ecr_rank_ecr": 1.0, "espn_adp": 3.0, "ffc_adp": 88.0},
        # No ESPN ADP: FFC fallback.
        {"player_name": "B", "fantasypros_ecr_rank_ecr": 30.0, "espn_adp": None, "ffc_adp": 25.0},
    ])
    out = _derive_draft_market_fields(df).set_index("player_name")

    assert out.loc["A", "adp"] == 3 and out.loc["A", "ecr_vs_adp"] == 2
    assert out.loc["B", "adp"] == 25 and out.loc["B", "ecr_vs_adp"] == -5


def test_derive_draft_market_fields_pos_rank_from_ecr():
    from src.ingestion.pipeline import _derive_draft_market_fields

    df = pd.DataFrame([
        {"player_name": "A", "fantasypros_ecr_pos_rank": "WR9"},
        {"player_name": "B", "fantasypros_ecr_pos_rank": None},
    ])
    out = _derive_draft_market_fields(df).set_index("player_name")

    assert out.loc["A", "pos_rank"] == 9
    assert pd.isna(out.loc["B", "pos_rank"])


# ---- Cache TTL: a stale board is the draft-day failure mode ------------------

def _cache_env(tmp_path, monkeypatch, age_hours, live_result):
    """Point the pipeline at a temp parquet cache with a chosen age, and stub
    the live fetch. Returns the list live-fetch calls are recorded into."""
    import os
    import time

    import src.ingestion.pipeline as pipe

    cache_file = tmp_path / "players_raw.parquet"
    pd.DataFrame([{"player_name": "Cached Player", "team": "SF", "position": "RB"}]).to_parquet(cache_file)
    mtime = time.time() - age_hours * 3600
    os.utime(cache_file, (mtime, mtime))
    monkeypatch.setattr(pipe, "CACHE_PATH", str(cache_file))
    monkeypatch.delenv("DRAFTDAY_OFFLINE", raising=False)

    calls = []

    def fake_fetch_live(scoring_format="ppr"):
        calls.append(scoring_format)
        if isinstance(live_result, Exception):
            raise live_result
        return live_result

    monkeypatch.setattr(pipe, "fetch_live", fake_fetch_live)
    return calls


def test_fresh_cache_served_without_live_fetch(tmp_path, monkeypatch):
    import src.ingestion.pipeline as pipe

    calls = _cache_env(tmp_path, monkeypatch, age_hours=1, live_result=RuntimeError("no net"))
    df, source = pipe._resolve_table(refresh=False, scoring_format="ppr", use_sample_on_failure=True)

    assert source == "cache"
    assert df.iloc[0]["player_name"] == "Cached Player"
    assert calls == []  # fresh cache means no network attempt at all


def test_stale_cache_triggers_live_refetch(tmp_path, monkeypatch):
    import src.ingestion.pipeline as pipe

    live = pd.DataFrame([{"player_name": "Fresh Player", "team": "CHI", "position": "WR"}])
    _cache_env(tmp_path, monkeypatch, age_hours=pipe.CACHE_TTL_HOURS + 5, live_result=live)
    df, source = pipe._resolve_table(refresh=False, scoring_format="ppr", use_sample_on_failure=True)

    assert source == "live"
    assert df.iloc[0]["player_name"] == "Fresh Player"


def test_stale_cache_still_beats_sample_when_live_fails(tmp_path, monkeypatch):
    import src.ingestion.pipeline as pipe

    _cache_env(tmp_path, monkeypatch, age_hours=pipe.CACHE_TTL_HOURS + 5,
               live_result=RuntimeError("no net"))
    df, source = pipe._resolve_table(refresh=False, scoring_format="ppr", use_sample_on_failure=True)

    assert source == "cache"  # stale real data > bundled demo sample
    assert df.iloc[0]["player_name"] == "Cached Player"
