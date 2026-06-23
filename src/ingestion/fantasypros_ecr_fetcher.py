import json

import pandas as pd
import requests

from src.ingestion.base import Fetcher
from src.ingestion.fantasypros_fetcher import FantasyProsFetcher

SCORING_PREFIXES = {
    "standard": "",
    "ppr": "ppr-",
    "half_ppr": "half-point-ppr-",
}

NUMERIC_COLUMNS = ["rank_ecr", "rank_min", "rank_max", "rank_ave", "rank_std", "tier", "bye"]


class FantasyProsECRFetcher(Fetcher):
    """
    FantasyPros' draft cheat-sheet page embeds a JSON blob (`ecrData`) blending
    every contributing expert's individual ranking for each player, with
    rank_min/rank_max/rank_ave/rank_std already computed across all of them --
    this is the real multi-expert variance signal the floor/ceiling calculation
    needs, and isn't derivable from a single projection source. One call covers
    every position plus FantasyPros' own tier and bye week.
    """

    source_name = "fantasypros_ecr"

    BASE_URL = "https://www.fantasypros.com/nfl/rankings/{prefix}overall-cheatsheets.php"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(FantasyProsFetcher.HEADERS)

    def fetch(self, scoring_format="standard", **kwargs) -> pd.DataFrame:
        prefix = SCORING_PREFIXES.get(scoring_format, "")
        url = self.BASE_URL.format(prefix=prefix)

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching FantasyPros ECR data: {e}")
            return pd.DataFrame()

        raw_json = self._extract_ecr_json(response.text)
        if raw_json is None:
            print("Could not find ecrData on FantasyPros ECR page")
            return pd.DataFrame()

        try:
            payload = json.loads(raw_json)
        except ValueError:
            return pd.DataFrame()

        players = payload.get("players", [])
        if not players:
            return pd.DataFrame()

        df = pd.DataFrame(players).copy()
        df = df.rename(
            columns={
                "player_team_id": "team",
                "player_position_id": "position",
                "player_bye_week": "bye",
            }
        )

        for col in NUMERIC_COLUMNS:
            if col in df.columns:
                df.loc[:, col] = pd.to_numeric(df[col], errors="coerce")

        df.loc[:, "total_experts"] = payload.get("total_experts")
        df.loc[:, "source"] = self.source_name

        keep = [
            "player_name", "team", "position", "source",
            "rank_ecr", "rank_min", "rank_max", "rank_ave", "rank_std",
            "pos_rank", "tier", "bye", "total_experts",
        ]
        return df[[c for c in keep if c in df.columns]]

    @staticmethod
    def _extract_ecr_json(html_text):
        """
        ecrData is a JS variable assignment, not a clean <script type="json">
        block, so it's pulled out by brace-counting from the raw HTML rather
        than a regex -- a non-greedy regex truncates on the first "}" inside
        the nested JSON, which is wrong here since the payload nests objects.
        """
        marker = "var ecrData = "
        start = html_text.find(marker)
        if start == -1:
            return None
        start += len(marker)

        depth = 0
        for i in range(start, len(html_text)):
            char = html_text[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return html_text[start : i + 1]
        return None
