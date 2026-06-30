"""Piece 3: Tier-Cliff Multiplier (live).

Recomputed after every pick over the UNDRAFTED subset only. A static, full-board
TCM measures the gap to whoever was 2 spots below before the draft started --
which goes stale as players are drafted, understating cliff urgency exactly when
it matters most. Computing over the undrafted board keeps it honest and is the
same shape of operation pdm/inflation already do live.
"""

import numpy as np
import pandas as pd

from src.rankings.league_state import LeagueState

DROP_THRESHOLD = 0.10


def calculate_tcm(df: pd.DataFrame, league_state: LeagueState) -> pd.Series:
    """Per position, among undrafted rows only, compare each player's points to
    the player two spots below them; if the drop exceeds 10%, ``tcm = 1 + drop``,
    else ``1.0``. Drafted rows get ``NaN`` (their worth is never consumed again).

    The last two players in each position have nobody two spots below, so they
    land on exactly ``1.0`` rather than being compared against a stale tail.
    Where ``points == 0`` the drop is skipped (no divide-by-zero), also ``1.0``.
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)

    undrafted = df[~df["player_id"].isin(league_state.drafted_player_ids)]
    if undrafted.empty:
        return result

    ranked = undrafted.sort_values(["position", "points"], ascending=[True, False])
    below2 = ranked.groupby("position")["points"].shift(-2)
    pts = ranked["points"]

    drop = (pts - below2) / pts.where(pts > 0)
    tcm = pd.Series(np.where(drop > DROP_THRESHOLD, 1.0 + drop, 1.0), index=ranked.index)
    # Tail players (no row 2 below) and zero-point players fall back to 1.0.
    tcm = tcm.where(below2.notna() & (pts > 0), 1.0)

    result.loc[ranked.index] = tcm
    return result
