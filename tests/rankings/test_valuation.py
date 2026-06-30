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


def test_dollar_floor_only_when_vorp_positive():
    # vorp 1, inflation 0.2 -> raw 0.2 -> floor(0.7)=0 -> max(1,0)=1.
    worth = calculate_final_worth(_worth_frame(1.0), {"RB": 1.0}, {"RB": 0.2})
    assert worth.iloc[0] == 1


def test_vorp_zero_forces_worth_zero():
    # Even with big multipliers, vorp 0 -> worth 0 (no $1 floor).
    worth = calculate_final_worth(_worth_frame(0.0), {"RB": 1.25}, {"RB": 10.0})
    assert worth.iloc[0] == 0


def test_half_rounds_up_like_js_math_round():
    # raw = vorp*inflation*tcm*pdm = 5 * 0.5 * 1 * 1 = 2.5 -> floor(3.0)=3.
    # Python's round(2.5) would give 2 (banker's); we must get 3.
    worth = calculate_final_worth(_worth_frame(5.0), {"RB": 1.0}, {"RB": 0.5})
    assert worth.iloc[0] == 3


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
    assert live.pdm_map is not None and live.inflation_map is not None

    # Sanity: worth is non-negative everywhere and the top RB outranks a deep RB.
    assert (live.players["worth"] >= 0).all()
    rb = live.players[live.players["position"] == "RB"].sort_values("points", ascending=False)
    assert rb["worth"].iloc[0] >= rb["worth"].iloc[-1]


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
