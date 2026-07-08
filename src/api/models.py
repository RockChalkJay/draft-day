"""Pydantic request/response models for the stateless rankings API.

The browser owns all draft state and re-sends it each call; these models are the
wire contract. Player rows are passed as free-form dicts so the raw merged-table
columns flow through untouched -- the engine, not the API schema, decides which
columns matter.
"""

from typing import Any

from pydantic import BaseModel, Field


class ScoringConfigModel(BaseModel):
    """A preset name, optionally with per-category weight overrides. Any category
    left null inherits from the preset (default "ppr")."""
    preset: str | None = "ppr"
    passing: dict[str, float] | None = None
    rushing: dict[str, float] | None = None
    receiving: dict[str, float] | None = None
    kicking: dict[str, float] | None = None
    defense: dict[str, float] | None = None
    misc: dict[str, float] | None = None


class ReplacementConfigModel(BaseModel):
    qb_starters: int = 1
    rb_starters: int = 2
    wr_starters: int = 2
    te_starters: int = 1
    flex_spots: int = 1


class RosterSlotModel(BaseModel):
    pos: str
    player_id: str | None = None


class TeamModel(BaseModel):
    team_id: str
    bankroll: float
    roster: list[RosterSlotModel] = Field(default_factory=list)


class LeagueStateModel(BaseModel):
    teams: list[TeamModel] = Field(default_factory=list)
    drafted_player_ids: list[str] = Field(default_factory=list)
    starting_bankroll: float = 200.0


class PlayersResult(BaseModel):
    players: list[dict[str, Any]]
    count: int
    source: str  # "cache", "live", "sample", or "empty"


class StaticRequest(BaseModel):
    players: list[dict[str, Any]]
    scoring_config: ScoringConfigModel = Field(default_factory=ScoringConfigModel)
    replacement_config: ReplacementConfigModel = Field(default_factory=ReplacementConfigModel)
    num_teams: int = 12
    num_tiers: int = 5


class StaticResult(BaseModel):
    players: list[dict[str, Any]]
    replacement_levels: dict[str, float]


class LiveRequest(BaseModel):
    static_result: StaticResult
    league_state: LeagueStateModel


class LiveResult(BaseModel):
    players: list[dict[str, Any]]
    pdm_map: dict[str, float]
    inflation: float  # conserving factor (money in room vs value on board)
    market_heat: float = 1.0  # anticipatory draft-phase decay; worth uses inflation * market_heat
