"""Minimal in-memory model of a draft in progress.

Just enough state to drive the live valuation pieces (tcm/pdm/inflation/worth):
which players are gone, each team's empty roster slots, each team's remaining
bankroll. Not a persisted backend -- a plain snapshot handed to the live
functions on demand (e.g. after each pick).
"""

from dataclasses import dataclass, field


@dataclass
class RosterSlot:
    pos: str  # "QB" | "RB" | "WR" | "TE" | "FLEX" | "BENCH" | "K" | "DST"
    player_id: str | None = None  # None = empty slot


@dataclass
class Team:
    team_id: str
    bankroll: float
    roster: list[RosterSlot] = field(default_factory=list)

    def empty_slot_counts(self) -> dict[str, int]:
        """Count of unfilled slots per slot label (incl. "FLEX"/"BENCH")."""
        counts: dict[str, int] = {}
        for slot in self.roster:
            if slot.player_id is None:
                counts[slot.pos] = counts.get(slot.pos, 0) + 1
        return counts


@dataclass
class LeagueState:
    teams: list[Team] = field(default_factory=list)
    drafted_player_ids: set[str] = field(default_factory=set)
    starting_bankroll: float = 200.0  # per-team starting budget, for market-heat

    def initial_cash(self) -> float:
        return len(self.teams) * self.starting_bankroll

    def is_drafted(self, player_id: str) -> bool:
        return player_id in self.drafted_player_ids

    def total_remaining_cash(self) -> float:
        return float(sum(t.bankroll for t in self.teams))

    def empty_slots_by_pos(self) -> dict[str, int]:
        """Empty slots aggregated across every team, including "FLEX"."""
        agg: dict[str, int] = {}
        for team in self.teams:
            for pos, count in team.empty_slot_counts().items():
                agg[pos] = agg.get(pos, 0) + count
        return agg
