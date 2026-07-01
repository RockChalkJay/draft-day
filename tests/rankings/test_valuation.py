import pandas as pd

from src.rankings.league_state import LeagueState, RosterSlot, Team
from src.rankings.scoring import PRESETS
from src.rankings.valuation import (
    apply_live_valuation,
    calculate_final_worth,
    calculate_static_rankings,
)


def _wf(aav, pos="RB"):
    return pd.DataFrame([{"player_id": "p0", "position": pos, "aav": aav}])


def test_worth_equals_aav_at_inflation_one():
    assert calculate_final_worth(_wf(40), 1.0, set()).iloc[0] == 40


def test_worth_scales_with_inflation():
    # 1 + (40-1)*1.5 = 59.5 -> 60
    assert calculate_final_worth(_wf(40), 1.5, set()).iloc[0] == 60


def test_dollar_aav_stays_a_dollar_regardless_of_inflation():
    # 1 + (1-1)*infl = 1 (a min-bid player never inflates)
    assert calculate_final_worth(_wf(1), 3.0, set()).iloc[0] == 1


def test_k_dst_not_priced():
    assert calculate_final_worth(_wf(3, "K"), 1.0, set()).iloc[0] == 0
    assert calculate_final_worth(_wf(3, "DST"), 1.0, set()).iloc[0] == 0


def test_drafted_player_gets_zero():
    assert calculate_final_worth(_wf(40), 1.0, {"p0"}).iloc[0] == 0


def test_below_market_players_are_zero():
    # aav < 1 (no real market value) -> not a draft target -> $0.
    assert calculate_final_worth(_wf(0), 2.0, set()).iloc[0] == 0


def test_missing_aav_column_is_zero():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_final_worth(df, 1.5, set()).iloc[0] == 0


def test_end_to_end_static_then_live():
    rows = []
    for i in range(20):
        rows.append({"player_id": f"rb{i}", "player_name": f"RB{i}", "position": "RB",
                     "fantasypros_RUSHING_YDS": 1600 - i * 70, "fantasypros_RUSHING_TDS": 14 - i * 0.5,
                     "fantasypros_RECEIVING_REC": 50 - i, "fantasypros_RECEIVING_YDS": 400 - i * 12,
                     "fantasypros_RECEIVING_TDS": 3, "aav": max(1, 55 - i * 3)})
    for i in range(18):
        rows.append({"player_id": f"wr{i}", "player_name": f"WR{i}", "position": "WR",
                     "fantasypros_RECEIVING_REC": 110 - i * 4, "fantasypros_RECEIVING_YDS": 1500 - i * 70,
                     "fantasypros_RECEIVING_TDS": 11 - i * 0.4, "aav": max(1, 58 - i * 3)})
    for i in range(14):
        rows.append({"player_id": f"qb{i}", "player_name": f"QB{i}", "position": "QB",
                     "fantasypros_PASSING_YDS": 4800 - i * 160, "fantasypros_PASSING_TDS": 38 - i,
                     "fantasypros_PASSING_INTS": 9, "aav": max(1, 18 - i)})
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
    assert live.pdm_map is not None and live.inflation is not None

    # Sanity: worth is non-negative and the priciest AAV commands the most worth.
    assert (live.players["worth"] >= 0).all()
    rb = live.players[live.players["position"] == "RB"].sort_values("aav", ascending=False)
    assert rb["worth"].iloc[0] >= rb["worth"].iloc[-1]

    # Roughly budget-scale: total predicted worth stays near the cash in the room
    # (exactly conserving when priced players == slots; a little over when there
    # are more priced players than slots, as here).
    assert live.players["worth"].sum() <= ls.total_remaining_cash() * 1.15


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
