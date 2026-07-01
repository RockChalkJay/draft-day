"""Stateless rankings API (architecture Option A) + static frontend host.

Three endpoints, no server-side session state:
  GET  /api/players          -> raw merged player table (cache/live/sample)
  POST /api/rankings/static  -> points/tier/vorp (compute once per config)
  POST /api/rankings/live    -> tcm/pdm/worth (recompute after every pick)

The browser holds the LeagueState and re-sends it (plus the static result) on
every /live call, so the server stays a pure function of its inputs.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.models import (
    LiveRequest,
    LiveResult,
    PlayersResult,
    StaticRequest,
    StaticResult,
)
from src.api.serialize import (
    build_league_state,
    build_replacement,
    build_scoring,
    df_to_records,
    records_to_df,
)
from src.ingestion.pipeline import load_player_table_with_source
from src.rankings.valuation import (
    RankingsResult,
    apply_live_valuation,
    calculate_static_rankings,
)

app = FastAPI(title="Draft Day", version="1.0.0")

# Frontend is served same-origin (mount below), so CORS isn't needed in normal
# use. Allowed broadly anyway so the static mockup / a separate dev server can
# hit the API while iterating.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/players", response_model=PlayersResult)
def get_players(refresh: bool = False) -> PlayersResult:
    """Raw merged player table. ``refresh=true`` forces a live re-fetch."""
    df, source = load_player_table_with_source(refresh=refresh)
    return PlayersResult(players=df_to_records(df), count=len(df), source=source)


@app.post("/api/rankings/static", response_model=StaticResult)
def rankings_static(req: StaticRequest) -> StaticResult:
    """Steps 0-2: points -> tiers -> vorp. Call once at draft start; the browser
    caches the result and re-sends it on every /live call."""
    df = records_to_df(req.players)
    result = calculate_static_rankings(
        df,
        scoring=build_scoring(req.scoring_config),
        num_teams=req.num_teams,
        num_tiers=req.num_tiers,
        replacement_config=build_replacement(req.replacement_config),
    )
    return StaticResult(
        players=df_to_records(result.players),
        replacement_levels=result.replacement_levels,
    )


@app.post("/api/rankings/live", response_model=LiveResult)
def rankings_live(req: LiveRequest) -> LiveResult:
    """Steps 3-6: tcm -> pdm -> inflation -> worth. Call after every pick/undo
    with the cached static result plus the current LeagueState."""
    static = RankingsResult(
        players=records_to_df(req.static_result.players),
        replacement_levels=req.static_result.replacement_levels,
    )
    live = apply_live_valuation(static, build_league_state(req.league_state))
    return LiveResult(
        players=df_to_records(live.players),
        pdm_map=live.pdm_map or {},
        position_budgets=live.position_budgets or {},
    )


# Serve the web frontend from /, if present. Mounted last so /api/* wins.
_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
if os.path.isdir(_WEB_DIR):
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
