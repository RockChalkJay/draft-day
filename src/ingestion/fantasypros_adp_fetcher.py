"""FantasyPros consensus ADP (https://www.fantasypros.com/nfl/adp/ppr-overall.php).

The page embeds its full table as JSON (``window.FP.reportConfig``), but for
anonymous visitors it is registration-fenced to a ~5-row teaser. A free
FantasyPros login unlocks the full table; since the login flow itself is
captcha-protected, this fetcher takes the already-authenticated browser cookie
instead: set ``DRAFTDAY_FP_COOKIE`` to the ``Cookie`` request-header value from
a logged-in fantasypros.com browser tab (DevTools -> Network -> any request ->
Request Headers -> Cookie). Without it the fetch still works but is treated as
fenced and discarded by the pipeline, which falls back to the rankings-sheet
import and then FFC for ADP.
"""

import json
import os
import re

import pandas as pd

from src.ingestion.base import Fetcher
from src.ingestion.fantasypros_fetcher import FantasyProsFetcher

# Below this many rows the payload is assumed to be the registration-fenced
# teaser rather than real data.
FENCE_THRESHOLD = 50

POS_RANK_RE = re.compile(r"^([A-Z]+)(\d+)$")
TEAM_BYE_RE = re.compile(r"^([A-Z]{2,3})\s*\((\d+)\)$")


class FantasyProsADPFetcher(Fetcher):
    source_name = "fantasypros_adp"

    URL = "https://www.fantasypros.com/nfl/adp/{scoring_format}-overall.php"
    SCORING_PATHS = {"ppr": "ppr", "half_ppr": "half-point-ppr", "standard": "standard"}

    def __init__(self, session=None):
        import requests

        self.session = session or requests.Session()
        self.session.headers.update(FantasyProsFetcher.HEADERS)
        cookie = os.environ.get("DRAFTDAY_FP_COOKIE")
        if cookie:
            self.session.headers["Cookie"] = cookie

    def fetch(self, scoring_format="ppr", **kwargs) -> pd.DataFrame:
        url = self.URL.format(scoring_format=self.SCORING_PATHS.get(scoring_format, "ppr"))
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching FantasyPros ADP page: {e}")
            return pd.DataFrame()

        df = self.parse_report_html(response.text)
        if len(df) < FENCE_THRESHOLD:
            # Anonymous teaser (registration fence) -- not real coverage.
            print(
                f"FantasyPros ADP page returned only {len(df)} rows (registration fence); "
                "set DRAFTDAY_FP_COOKIE from a logged-in browser session for the full table."
            )
            return pd.DataFrame()
        return df

    @staticmethod
    def parse_report_html(html_text: str) -> pd.DataFrame:
        """Extract ``window.FP.reportConfig``'s table rows. Each row looks like
        ``{"rank": 1, "player": {"name": ..., "team": "DET (6)"}, "pos": "RB1",
        "avg": 1.0}`` -- position and positional rank ride together in ``pos``,
        team and bye together in ``team``."""
        marker = "window.FP.reportConfig = "
        start = html_text.find(marker)
        if start == -1:
            return pd.DataFrame()
        start += len(marker)

        depth = 0
        end = None
        for i in range(start, len(html_text)):
            char = html_text[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            return pd.DataFrame()

        try:
            config = json.loads(html_text[start:end])
        except ValueError:
            return pd.DataFrame()

        rows = []
        for row in (config.get("table") or {}).get("rows", []):
            player = row.get("player") or {}
            name = player.get("name")
            if not name:
                continue
            pos_match = POS_RANK_RE.match(str(row.get("pos") or ""))
            team_match = TEAM_BYE_RE.match(str(player.get("team") or ""))
            position = pos_match.group(1) if pos_match else None
            rows.append({
                "player_name": name,
                "team": team_match.group(1) if team_match else "FA",
                "position": "DST" if position == "DST" else position,
                "source": FantasyProsADPFetcher.source_name,
                "adp": row.get("avg"),
                "adp_rank": row.get("rank"),
                "pos_rank": int(pos_match.group(2)) if pos_match else None,
                "bye": int(team_match.group(2)) if team_match else None,
            })
        df = pd.DataFrame(rows)
        return df.dropna(subset=["position"]) if not df.empty else df
