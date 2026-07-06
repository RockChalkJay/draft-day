"""ESPN's public fantasy-football player universe (no API key, no login).

ESPN exposes a league-less player endpoint that anyone can call -- unlike
FantasyPros' ADP page (registration-fenced to a ~5-row teaser without a paid
or free-account login), this needs no authentication at all. Since ESPN is
itself one of the largest fantasy platforms, its consensus draft rank,
auction value, and ownership% are drawn from real ESPN leagues/drafts at
scale, refreshed continuously through the season -- a genuine second
market-consensus source alongside FFC's ADP.

Confirmed by hand (see the ingestion research this fetcher came out of):
  GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/players
      ?scoringPeriodId=0&view=kona_player_info
  Header: x-fantasy-filter: {"players": {"limit": N, "sortDraftRanks": {...}}}
returns, per player, draftRanksByRankType (rank + auctionValue per format)
and ownership (percentOwned/percentStarted/averageDraftPosition).
"""

import json

import pandas as pd
import requests

from src.ingestion.base import Fetcher

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

POSITION_ID_TO_NAME = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
RANK_TYPE_BY_SCORING = {"standard": "STANDARD", "half_ppr": "HALF_PPR", "ppr": "PPR"}
# ESPN's own team abbreviations differ from this project's convention
# (id_mapping.TEAM_NAME_TO_ABBR) for two teams.
_ESPN_TEAM_REMAP = {"WSH": "WAS", "JAX": "JAC"}

FETCH_LIMIT = 3000  # comfortably above the ~1700 rostered-relevant NFL players


class EspnFetcher(Fetcher):
    source_name = "espn"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def _team_map(self, year: int) -> dict[int, str]:
        """ESPN's own proTeamId -> abbreviation table, fetched live rather than
        hardcoded so an expansion/relocation never goes silently stale."""
        try:
            resp = self.session.get(
                BASE_URL.format(year=year), params={"view": "proTeamSchedules"}, timeout=15
            )
            resp.raise_for_status()
            teams = resp.json().get("settings", {}).get("proTeams", [])
        except Exception as e:
            print(f"Error fetching ESPN team map: {e}")
            return {}
        return {t["id"]: _ESPN_TEAM_REMAP.get(t["abbrev"], t["abbrev"]) for t in teams}

    def fetch(self, scoring_format="ppr", year=None, **kwargs) -> pd.DataFrame:
        import datetime

        year = year or datetime.date.today().year
        rank_type = RANK_TYPE_BY_SCORING.get(scoring_format, "PPR")
        team_map = self._team_map(year)

        url = BASE_URL.format(year=year) + "/players"
        params = {"scoringPeriodId": 0, "view": "kona_player_info"}
        filt = {
            "players": {
                "limit": FETCH_LIMIT,
                "sortDraftRanks": {"sortPriority": 1, "sortAsc": True, "value": rank_type},
            }
        }
        try:
            resp = self.session.get(
                url, params=params, headers={"x-fantasy-filter": json.dumps(filt)}, timeout=20
            )
            resp.raise_for_status()
            players = resp.json()
        except Exception as e:
            print(f"Error fetching ESPN player pool: {e}")
            return pd.DataFrame()

        rows = []
        for p in players:
            pos = POSITION_ID_TO_NAME.get(p.get("defaultPositionId"))
            if pos is None:
                continue
            ranks = (p.get("draftRanksByRankType") or {}).get(rank_type) or {}
            ownership = p.get("ownership") or {}
            rows.append({
                "player_name": p.get("fullName"),
                "team": team_map.get(p.get("proTeamId"), "FA"),
                "position": pos,
                "source": self.source_name,
                # Bare names: merge_sources prefixes every source's columns
                # with its source name (espn_), so these must NOT be
                # pre-prefixed here or the result double-prefixes
                # (espn_espn_adp) and silently vanishes from every downstream
                # lookup, same convention FFC/nflverse/Sleeper follow.
                "adp": ownership.get("averageDraftPosition"),
                "auction_value": ownership.get("auctionValueAverage") or ranks.get("auctionValue"),
                "overall_rank": ranks.get("rank"),  # ESPN's own overall rank, not positional
                "pct_owned": ownership.get("percentOwned"),
                "pct_started": ownership.get("percentStarted"),
            })
        df = pd.DataFrame(rows)
        return df.dropna(subset=["player_name"]) if not df.empty else df
