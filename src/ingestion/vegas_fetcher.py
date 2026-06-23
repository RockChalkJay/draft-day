import nflreadpy as nfl
import pandas as pd


class VegasFetcher:
    """
    Derives team scoring-environment context from nflverse's free, no-API-key
    schedule data (closing spread_line/total_line) instead of a paid,
    rate-limited odds API. Sign convention verified against actual scores:
    positive spread_line means the home team was favored by that many points.

    implied_total = (total_line +/- spread_line) / 2, home gets "+".

    This only covers seasons with completed games -- it's a historical average
    used as a proxy for a team's offensive environment heading into a new
    season, not a live in-season feed of upcoming lines.

    Team-level, not player-level, so this intentionally does not implement the
    Fetcher contract -- it's joined onto the merged player table by `team` in
    the rankings module, not merged by player_id like the other sources.
    """

    source_name = "vegas"

    def fetch(self, seasons=None) -> pd.DataFrame:
        try:
            polars_df = nfl.load_schedules(seasons=seasons)
        except Exception as e:
            print(f"Error fetching schedules for Vegas implied totals: {e}")
            return pd.DataFrame()

        df = polars_df.to_pandas()
        df = df.dropna(subset=["spread_line", "total_line"])
        if df.empty:
            return pd.DataFrame()

        home = pd.DataFrame(
            {
                "team": df["home_team"],
                "implied_total": (df["total_line"] + df["spread_line"]) / 2,
            }
        )
        away = pd.DataFrame(
            {
                "team": df["away_team"],
                "implied_total": (df["total_line"] - df["spread_line"]) / 2,
            }
        )

        long_form = pd.concat([home, away], ignore_index=True)
        summary = (
            long_form.groupby("team")["implied_total"]
            .mean()
            .round(2)
            .reset_index()
            .rename(columns={"implied_total": "vegas_implied_team_total"})
        )
        summary["source"] = self.source_name
        return summary
