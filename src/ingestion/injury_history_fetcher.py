import nflreadpy as nfl
import pandas as pd

from src.ingestion.base import Fetcher

OUT_STATUSES = {"Out", "Doubtful"}


class InjuryHistoryFetcher(Fetcher):
    """
    Aggregates nflverse's weekly injury report data (free, no key) into a
    per-player history summary across the requested seasons: how many weeks
    they carried any game-status report, and how many of those were "Out" or
    "Doubtful" (the closest free proxy for games actually missed). This is
    multi-season history, distinct from sleeper_fetcher's current-week
    injury_status snapshot.
    """

    source_name = "nflverse_injuries"

    def fetch(self, seasons=None, **kwargs) -> pd.DataFrame:
        try:
            polars_df = nfl.load_injuries(seasons=seasons)
        except Exception as e:
            print(f"Error fetching nflverse injury reports: {e}")
            return pd.DataFrame()

        df = polars_df.to_pandas()
        df = df.dropna(subset=["full_name"])
        if df.empty:
            return df

        # A player can have multiple report rows per week (one per practice
        # day); keep only the most recently modified row per (player, season,
        # week) so weekly counts aren't inflated.
        df = df.sort_values("date_modified")
        weekly = df.drop_duplicates(subset=["full_name", "season", "week"], keep="last")

        latest_identity = (
            df.drop_duplicates(subset=["full_name"], keep="last")
            .loc[:, ["full_name", "team", "position"]]
        )

        weekly = weekly.copy()
        weekly.loc[:, "is_out_or_doubtful"] = weekly["report_status"].isin(OUT_STATUSES)

        summary = (
            weekly.groupby("full_name")
            .agg(
                weeks_with_injury_report=("week", "size"),
                weeks_out_or_doubtful=("is_out_or_doubtful", "sum"),
                seasons_with_injury_report=("season", "nunique"),
            )
            .reset_index()
        )

        result = summary.merge(latest_identity, on="full_name", how="left")
        result = result.rename(columns={"full_name": "player_name"})
        result.loc[:, "source"] = self.source_name
        return result
