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


def build_scoring(model: ScoringConfigModel) -> ScoringConfig:
    """Resolve a preset and layer any provided category overrides on top."""
    base = PRESETS.get(model.preset or "ppr", PRESETS["ppr"])
    return ScoringConfig(
        passing=model.passing if model.passing is not None else dict(base.passing),
        rushing=model.rushing if model.rushing is not None else dict(base.rushing),
        receiving=model.receiving if model.receiving is not None else dict(base.receiving),
        kicking=model.kicking if model.kicking is not None else dict(base.kicking),
        defense=model.defense if model.defense is not None else dict(base.defense),
        misc=model.misc if model.misc is not None else dict(base.misc),
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
