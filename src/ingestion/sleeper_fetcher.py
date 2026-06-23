import pandas as pd
import requests

from src.ingestion.base import Fetcher

POSITION_WHITELIST = {"QB", "RB", "WR", "TE", "K", "DEF"}


class SleeperFetcher(Fetcher):
    source_name = "sleeper"

    PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def fetch(self, **kwargs) -> pd.DataFrame:
        """
        Fetches Sleeper's full NFL player pool in one free, unauthenticated call.
        Returns normalized player_name/team/position/source plus injury_status and
        Sleeper's own player_id (kept as sleeper_player_id so it doesn't collide
        with the canonical player_id assigned in merge.py).
        """
        try:
            response = self.session.get(self.PLAYERS_URL, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching Sleeper player pool: {e}")
            return pd.DataFrame()

        try:
            raw = response.json()
        except ValueError:
            return pd.DataFrame()

        rows = []
        for sleeper_player_id, player in raw.items():
            position = player.get("position")
            if position not in POSITION_WHITELIST:
                continue

            position_normalized = "DST" if position == "DEF" else position

            first_name = player.get("first_name") or ""
            last_name = player.get("last_name") or ""
            player_name = (player.get("full_name") or f"{first_name} {last_name}").strip()
            if not player_name and position_normalized == "DST":
                player_name = player.get("team")
            if not player_name:
                continue

            rows.append(
                {
                    "player_name": player_name,
                    "team": player.get("team") or "FA",
                    "position": position_normalized,
                    "source": self.source_name,
                    "sleeper_player_id": sleeper_player_id,
                    "injury_status": player.get("injury_status"),
                    "age": player.get("age"),
                    "years_exp": player.get("years_exp"),
                    "status": player.get("status"),
                }
            )

        return pd.DataFrame(rows)
