import nflreadpy as nfl
import pandas as pd

from src.ingestion.base import Fetcher


class NflverseFetcher(Fetcher):
    """
    Wraps nflreadpy (free, CC-BY-4.0 licensed nflverse data) for real, played-out
    stats: target_share, air_yards_share, wopr (the opportunity-share inputs),
    plus full season counting stats. This is historical-only -- it has nothing
    for rookies or offseason context changes, which is why ECR sources
    (fantasypros, ffc) stay in the pipeline alongside it rather than being
    replaced by it.
    """

    source_name = "nflverse"

    def fetch(self, seasons=None, summary_level="reg", **kwargs) -> pd.DataFrame:
        try:
            polars_df = nfl.load_player_stats(seasons=seasons, summary_level=summary_level)
        except Exception as e:
            print(f"Error fetching nflverse player stats: {e}")
            return pd.DataFrame()

        df = polars_df.to_pandas()
        if df.empty:
            return df

        # player_name here is nflverse's abbreviated form ("A.Rodgers"); drop it in
        # favor of player_display_name ("Aaron Rodgers") so name matching against
        # other sources in id_mapping.py behaves consistently.
        df = df.drop(columns=["player_name"], errors="ignore")
        df = df.rename(columns={"player_display_name": "player_name"})

        # Season-level aggregates (summary_level="reg"/"post"/"reg+post") name the
        # column "recent_team" instead of "team" -- normalize so the identity
        # contract (player_name, team, position) holds regardless of summary_level.
        if "team" not in df.columns and "recent_team" in df.columns:
            df = df.rename(columns={"recent_team": "team"})

        df["source"] = self.source_name
        return df
