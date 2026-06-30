"""Conversions between the API's JSON models and the engine's pandas/dataclass
types. Kept separate from app.py so the endpoint handlers stay thin.
"""

import json

import pandas as pd

from src.api.models import (
    LeagueStateModel,
    ReplacementConfigModel,
    ScoringConfigModel,
)
from src.rankings.league_state import LeagueState, RosterSlot, Team
from src.rankings.replacement import ReplacementConfig
from src.rankings.scoring import PRESETS, ScoringConfig


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe records. Routed through pandas' own JSON writer so
    NaN becomes null and numpy scalar types are coerced to plain Python -- both
    of which would otherwise break JSON serialization downstream."""
    return json.loads(df.to_json(orient="records"))


def records_to_df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _merge_category(base_cat: dict, override: dict | None) -> dict:
    """Start from the preset's category weights and apply only the provided keys,
    so a partial override (e.g. receiving {"rec": 0.5}) keeps the preset's other
    weights (yards, TDs) instead of wiping them out."""
    merged = dict(base_cat)
    if override:
        merged.update(override)
    return merged


def build_scoring(model: ScoringConfigModel) -> ScoringConfig:
    """Resolve a preset and layer any provided per-key category overrides on top."""
    base = PRESETS.get(model.preset or "ppr", PRESETS["ppr"])
    return ScoringConfig(
        passing=_merge_category(base.passing, model.passing),
        rushing=_merge_category(base.rushing, model.rushing),
        receiving=_merge_category(base.receiving, model.receiving),
        kicking=_merge_category(base.kicking, model.kicking),
        defense=_merge_category(base.defense, model.defense),
        misc=_merge_category(base.misc, model.misc),
    )


def build_replacement(model: ReplacementConfigModel) -> ReplacementConfig:
    return ReplacementConfig(
        qb_starters=model.qb_starters,
        rb_starters=model.rb_starters,
        wr_starters=model.wr_starters,
        te_starters=model.te_starters,
        flex_spots=model.flex_spots,
    )


def build_league_state(model: LeagueStateModel) -> LeagueState:
    teams = [
        Team(
            team_id=t.team_id,
            bankroll=t.bankroll,
            roster=[RosterSlot(pos=s.pos, player_id=s.player_id) for s in t.roster],
        )
        for t in model.teams
    ]
    return LeagueState(teams=teams, drafted_player_ids=set(model.drafted_player_ids))
