import pandas as pd

from src.rankings.league_state import LeagueState, RosterSlot, Team
from src.rankings.scoring import PRESETS
from src.rankings.valuation import (
    apply_live_valuation,
    calculate_price,
    calculate_static_rankings,
    calculate_value,
)


# ---- Value (stable salary-cap dollars) --------------------------------------

def test_value_conserves_to_budget():
    # Discretionary pool (budget - slots = 185) is split by VORP share, +$1 each.
    df = pd.DataFrame([
        {"player_id": "a", "position": "RB", "vorp": 100.0},
        {"player_id": "b", "position": "WR", "vorp": 60.0},
        {"player_id": "c", "position": "TE", "vorp": 40.0},
    ])
    v = calculate_value(df, budget=200, total_slots=15)
    assert abs(int(v.sum()) - (3 + 185)) <= 2         # conserves (within rounding)
    assert v.iloc[0] > v.iloc[1] > v.iloc[2]          # more VORP -> more value


def test_k_dst_and_replacement_get_zero_value():
    df = pd.DataFrame([
        {"player_id": "k", "position": "K", "vorp": 50.0},
        {"player_id": "d", "position": "DST", "vorp": 50.0},
        {"player_id": "r", "position": "RB", "vorp": 0.0},   # replacement level
        {"player_id": "a", "position": "RB", "vorp": 80.0},
    ])
    vv = dict(zip(df["player_id"], calculate_value(df, 200, 15)))
    assert vv["k"] == 0 and vv["d"] == 0 and vv["r"] == 0 and vv["a"] > 0


def test_missing_vorp_gives_zero_value():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_value(df, 200, 15).iloc[0] == 0


# ---- Price (Value scaled by live inflation) ---------------------------------

def _pf(value, pos="RB"):
    return pd.DataFrame([{"player_id": "p0", "position": pos, "value": value}])


def test_price_equals_value_at_inflation_one():
    assert calculate_price(_pf(40), 1.0, set()).iloc[0] == 40


def test_price_deflates_below_one():
    # 1 + (40-1)*0.5 = 20.5 -> 20
    assert calculate_price(_pf(40), 0.5, set()).iloc[0] == 20


def test_dollar_value_stays_a_dollar_regardless_of_inflation():
    assert calculate_price(_pf(1), 1.8, set()).iloc[0] == 1


def test_price_k_dst_zero():
    assert calculate_price(_pf(30, "K"), 1.0, set()).iloc[0] == 0
    assert calculate_price(_pf(30, "DST"), 1.0, set()).iloc[0] == 0


def test_price_drafted_zero():
    assert calculate_price(_pf(40), 1.0, {"p0"}).iloc[0] == 0


def test_price_missing_value_zero():
    df = pd.DataFrame([{"player_id": "p0", "position": "RB"}])
    assert calculate_price(df, 1.0, set()).iloc[0] == 0


# ---- End to end -------------------------------------------------------------

def _synthetic_board():
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
    return pd.DataFrame(rows)


def test_end_to_end_static_then_live():
    static = calculate_static_rankings(_synthetic_board(), PRESETS["ppr"], num_teams=12, num_tiers=5)
    assert {"points", "tier", "vorp"}.issubset(static.players.columns)
    assert static.pdm_map is None

    roster = ["RB", "RB", "WR", "WR", "QB", "TE", "FLEX"] + ["BENCH"] * 8
    ls = LeagueState(
        teams=[Team(f"t{i}", 200.0, [RosterSlot(p) for p in roster]) for i in range(12)],
        drafted_player_ids=set(), starting_bankroll=200.0,
    )
    live = apply_live_valuation(static, ls)
    assert {"value", "worth", "bargain", "tcm", "pdm"}.issubset(live.players.columns)
    assert live.pdm_map is not None and live.inflation is not None

    priced = live.players[live.players["value"] > 0]
    # At draft start inflation is ~1.0, so Price == Value and Bargain == 0.
    assert round(live.inflation, 3) == 1.0 or abs(live.inflation - 1.0) < 0.05
    assert (priced["worth"] == priced["value"]).all()
    assert (priced["bargain"] == 0).all()
    # Value is budget-conserving: total never exceeds the cash in the room.
    assert live.players["value"].sum() <= ls.total_remaining_cash()
    # The top-VORP RB is the priciest RB.
    rb = live.players[live.players["position"] == "RB"].sort_values("vorp", ascending=False)
    assert rb["worth"].iloc[0] >= rb["worth"].iloc[-1]


def test_overpay_deflates_and_opens_bargains():
    static = calculate_static_rankings(_synthetic_board(), PRESETS["ppr"], num_teams=12)
    roster = ["RB", "RB", "WR", "WR", "QB", "TE", "FLEX"] + ["BENCH"] * 8

    def live(t0_cash, drafted):
        teams = [Team("t0", t0_cash, [RosterSlot(p) for p in roster])]
        teams += [Team(f"t{i}", 200.0, [RosterSlot(p) for p in roster]) for i in range(1, 12)]
        return apply_live_valuation(static, LeagueState(teams=teams, drafted_player_ids=set(drafted),
                                                        starting_bankroll=200.0))

    start = live(200.0, [])
    top = start.players.sort_values("value", ascending=False).iloc[0]
    # A team pays $60 over the top player's value -> money drains -> board deflates.
    after = live(200.0 - (int(top["value"]) + 60), [top["player_id"]])
    assert after.inflation < start.inflation
    # With prices down, still-priced players show positive bargains.
    ap = after.players[after.players["worth"] > 0]
    assert (ap["bargain"] >= 0).all() and (ap["bargain"] > 0).any()


def test_value_override_renormalized_so_draft_opens_at_par():
    # Override values come from an external sheet calibrated to *its* assumed
    # league. Raw, they break the budget identity: inflation would open away
    # from 1.0 and every Bargain would open red before a single bid. After
    # renormalization the draft must open at par regardless of the sheet's scale.
    static = calculate_static_rankings(_synthetic_board(), PRESETS["ppr"], num_teams=12)
    # A sheet on a wildly different scale (e.g. a $100-budget league's values),
    # covering only some players -- the rest keep computed values.
    static.players["value_override"] = pd.NA
    rb_ids = static.players["position"] == "RB"
    static.players.loc[rb_ids, "value_override"] = (
        static.players.loc[rb_ids, "vorp"].rank(ascending=False).map(lambda r: max(0, 35 - 3 * r))
    )

    roster = ["RB", "RB", "WR", "WR", "QB", "TE", "FLEX"] + ["BENCH"] * 8
    ls = LeagueState(
        teams=[Team(f"t{i}", 200.0, [RosterSlot(p) for p in roster]) for i in range(12)],
        drafted_player_ids=set(), starting_bankroll=200.0,
    )
    live = apply_live_valuation(static, ls)

    assert abs(live.inflation - 1.0) < 0.05
    priced = live.players[live.players["worth"] > 0]
    assert (priced["bargain"].abs() <= 1).all()  # par, within $1 int rounding
    # The sheet's own relative order is preserved by the (monotone) rescale.
    # (Only within the overridden subset: players the sheet doesn't cover keep
    # computed values on their own scale, so cross-source order isn't defined.)
    overridden = live.players[pd.to_numeric(live.players["value_override"], errors="coerce") > 0]
    overridden = overridden.sort_values("value_override", ascending=False)
    assert overridden["value"].is_monotonic_decreasing


def test_value_override_ignored_for_k_dst():
    # Sheets price K/DST at $1-2; this app never prices them, and letting a
    # sheet value through would leak into inflation's denominator.
    static = calculate_static_rankings(_synthetic_board(), PRESETS["ppr"], num_teams=12)
    k_row = pd.DataFrame([{"player_id": "k0", "player_name": "K0", "position": "K",
                           "points": 140.0, "tier": 1, "vorp": 0.0}])
    static.players = pd.concat([static.players, k_row], ignore_index=True)
    static.players["value_override"] = pd.NA
    static.players.loc[static.players["player_id"] == "k0", "value_override"] = 2

    ls = LeagueState(
        teams=[Team("t0", 200.0, [RosterSlot(p) for p in ("RB", "K", "BENCH")])],
        drafted_player_ids=set(), starting_bankroll=200.0,
    )
    live = apply_live_valuation(static, ls)
    k = live.players[live.players["player_id"] == "k0"].iloc[0]
    assert k["value"] == 0 and k["worth"] == 0


def test_static_result_reusable_across_picks():
    rows = [{"player_id": f"rb{i}", "player_name": f"RB{i}", "position": "RB",
             "fantasypros_RUSHING_YDS": 1500 - i * 100, "fantasypros_RUSHING_TDS": 12 - i,
             "fantasypros_RECEIVING_REC": 40, "fantasypros_RECEIVING_YDS": 300,
             "fantasypros_RECEIVING_TDS": 2} for i in range(15)]
    static = calculate_static_rankings(pd.DataFrame(rows), PRESETS["ppr"], num_teams=12)

    ls1 = LeagueState(teams=[Team("t0", 200.0, [RosterSlot("RB")])], drafted_player_ids=set())
    ls2 = LeagueState(teams=[Team("t0", 100.0, [RosterSlot("RB")])], drafted_player_ids={"rb0"})
    live1 = apply_live_valuation(static, ls1)
    live2 = apply_live_valuation(static, ls2)

    assert "worth" not in static.players.columns  # static frame untouched
    assert len(live1.players) == len(live2.players)
