import pandas as pd
import requests

from src.ingestion.base import Fetcher


class FFCFetcher(Fetcher):
    """
    Fantasy Football Calculator's ADP REST API. Free for personal/commercial use
    (attribution requested); no API key. Also exposes adp.stdev/high/low, which
    is a second, independent variance signal alongside ECR spread for the
    floor/ceiling calculation.
    """

    source_name = "ffc"

    BASE_URL = "https://fantasyfootballcalculator.com/api/v1/adp/{scoring_format}"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def fetch(self, scoring_format="standard", teams=12, year=None, position="all", **kwargs) -> pd.DataFrame:
        params = {"teams": teams, "position": position}
        if year is not None:
            params["year"] = year

        url = self.BASE_URL.format(scoring_format=scoring_format)

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching FFC ADP data: {e}")
            return pd.DataFrame()

        try:
            payload = response.json()
        except ValueError:
            return pd.DataFrame()

        players = payload.get("players", [])
        if not players:
            print(f"FFC ADP request returned no data: {payload.get('errors', payload)}")
            return pd.DataFrame()

        df = pd.DataFrame(players)
        df = df.rename(columns={"name": "player_name"})
        df["source"] = self.source_name

        return df
