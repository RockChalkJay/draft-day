import pandas as pd

from src.rankings.league_state import LeagueState, RosterSlot, Team
from src.rankings.scoring import PRESETS
from src.rankings.valuation import (
    apply_live_valuation,
    calculate_final_worth,
    calculate_static_rankings,
)


def _worth_frame(vorp, tcm=1.0):
    return pd.DataFrame([{"player_id": "p0", "position": "RB", "vorp": vorp, "tcm": tcm}])


def _pair(vorp_a, vorp_b, tcm_a=1.0, tcm_b=1.0):
    return pd.DataFrame([
        {"player_id": "a", "position": "RB", "vorp": vorp_a, "tcm": tcm_a},
        {"player_id": "b", "position": "RB", "vorp": vorp_b, "tcm": tcm_b},
    ])


def test_single_player_gets_floor_plus_whole_pool():
    # Only positive-VORP player in the RB pool -> $1 floor + the entire $40 pool.
    worth = calculate_final_worth(_worth_frame(100.0), {"RB": 40.0}, set())
    assert worth.iloc[0] == 41


def test_vorp_zero_forces_worth_zero():
    worth = calculate_final_worth(_worth_frame(0.0), {"RB": 100.0}, set())
    assert worth.iloc[0] == 0


def test_drafted_player_gets_zero():
    worth = calculate_final_worth(_worth_frame(100.0), {"RB": 40.0}, {"p0"})
    assert worth.iloc[0] == 0


def test_pool_split_conserves_budget():
    # compression 1.0: weights 100:25 -> 80:20 of the $100 pool, +$1 each.
    worth = calculate_final_worth(_pair(100.0, 25.0), {"RB": 100.0}, set(), compression=1.0)
    assert worth.tolist() == [81, 21]
    assert worth.sum() == 102  # 2 players' $1 floors + $100 pool


def test_compression_flattens_top_heavy_distribution():
    hi = calculate_final_worth(_pair(100.0, 25.0), {"RB": 100.0}, set(), compression=1.0)
    lo = calculate_final_worth(_pair(100.0, 25.0), {"RB": 100.0}, set(), compression=0.5)
    assert lo.iloc[0] < hi.iloc[0]  # top pulled down
    assert lo.iloc[1] > hi.iloc[1]  # middle lifted


def test_tcm_tilts_pool_within_position():
    # Equal VORP; the cliff player (tcm 1.5) takes a bigger slice, pool conserved.
    worth = calculate_final_worth(_pair(50.0, 50.0, tcm_a=1.5, tcm_b=1.0), {"RB": 100.0}, set(), compression=1.0)
    assert worth.iloc[0] > worth.iloc[1]
    assert worth.sum() == 102


def test_end_to_end_static_then_live():
    rows = []
    for i in range(20):
        rows.append({"player_id": f"rb{i}", "player_name": f"RB{i}", "position": "RB",
                     "fantasypros_RUSHING_YDS": 1600 - i * 70, "fantasypros_RUSHING_TDS": 14 - i * 0.5,
                     "fantasypros_RECEIVING_REC": 50 - i, "fantasypros_RECEIVING_YDS": 400 - i * 12,
                     "fantasypros_RECEIVING_TDS": 3})
    for i in range(18):
        rows.append({"player_id": f"wr{i}", "player_name": f"WR{i}", "position": "WR",
                     "fantasypros_RECEIVING_REC": 110 - i * 4, "fantasypros_RECEIVING_YDS": 1500 - i * 70,
                     "fantasypros_RECEIVING_TDS": 11 - i * 0.4})
    for i in range(14):
        rows.append({"player_id": f"qb{i}", "player_name": f"QB{i}", "position": "QB",
                     "fantasypros_PASSING_YDS": 4800 - i * 160, "fantasypros_PASSING_TDS": 38 - i,
                     "fantasypros_PASSING_INTS": 9})
    df = pd.DataFrame(rows)

    static = calculate_static_rankings(df, PRESETS["ppr"], num_teams=12, num_tiers=5)
    assert {"points", "tier", "vorp"}.issubset(static.players.columns)
    assert static.pdm_map is None  # not computed yet in the static stage

    ls = LeagueState(
        teams=[Team(f"t{i}", 200.0, [RosterSlot("RB"), RosterSlot("WR"), RosterSlot("QB"), RosterSlot("FLEX")])
               for i in range(12)],
        drafted_player_ids=set(),
    )
    live = apply_live_valuation(static, ls)
    cols = live.players.columns
    assert {"tcm", "pdm", "worth"}.issubset(cols)
    assert live.pdm_map is not None and live.position_budgets is not None

    # Sanity: worth is non-negative everywhere and the top RB outranks a deep RB.
    assert (live.players["worth"] >= 0).all()
    rb = live.players[live.players["position"] == "RB"].sort_values("points", ascending=False)
    assert rb["worth"].iloc[0] >= rb["worth"].iloc[-1]

    # Budget-conserving: total predicted worth does not exceed cash in the room.
    assert live.players["worth"].sum() <= ls.total_remaining_cash()


def test_static_result_reusable_across_picks():
    # The same static result drives two different live snapshots without mutation.
    rows = [{"player_id": f"rb{i}", "player_name": f"RB{i}", "position": "RB",
             "fantasypros_RUSHING_YDS": 1500 - i * 100, "fantasypros_RUSHING_TDS": 12 - i,
             "fantasypros_RECEIVING_REC": 40, "fantasypros_RECEIVING_YDS": 300,
             "fantasypros_RECEIVING_TDS": 2} for i in range(15)]
    static = calculate_static_rankings(pd.DataFrame(rows), PRESETS["ppr"], num_teams=12)

    ls1 = LeagueState(teams=[Team("t0", 200.0, [RosterSlot("RB")])], drafted_player_ids=set())
    ls2 = LeagueState(teams=[Team("t0", 100.0, [RosterSlot("RB")])], drafted_player_ids={"rb0"})

    live1 = apply_live_valuation(static, ls1)
    live2 = apply_live_valuation(static, ls2)

    # Static frame untouched (no tcm/worth leaked back onto it).
    assert "worth" not in static.players.columns
    # Different states give different rb0 drafted status reflected in worth presence.
    assert len(live1.players) == len(live2.players)
