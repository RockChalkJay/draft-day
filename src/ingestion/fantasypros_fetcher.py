import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.ingestion.base import Fetcher
from src.ingestion.id_mapping import TEAM_NAME_TO_ABBR

NAME_SUFFIXES = {"II", "III", "IV", "JR", "SR"}


class FantasyProsFetcher(Fetcher):
    source_name = "fantasypros"

    BASE_URL = "https://www.fantasypros.com/nfl/projections/{position}.php"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _parse_player_team(self, player_cell_text):
        """
        Parses player name and team from FantasyPros' player cell text, which has
        used at least three formats: "Patrick Mahomes (KC)" (older, parenthesized),
        "Jalen Hurts PHI" (current, trailing abbreviation), and "Denver Broncos"
        (DST rows, full team name with no abbreviation in the cell at all).
        """
        text = player_cell_text.strip()

        match = re.search(r"^(.*?)\s*\(([A-Z]{2,3})\)\s*$", text)
        if match:
            return match.group(1).strip(), match.group(2).strip()

        match = re.search(r"^(.*\S)\s+([A-Z]{2,3})$", text)
        if match and match.group(2) not in NAME_SUFFIXES:
            return match.group(1).strip(), match.group(2).strip()

        abbr = TEAM_NAME_TO_ABBR.get(text.lower())
        if abbr:
            return text, abbr

        return text, "FA"

    def _build_grouped_headers(self, header_rows):
        """
        Tables with stat groups (e.g. QB's PASSING/RUSHING/MISC) render the group
        labels in a row above the leaf column names, using colspan to span the
        leaf columns each group covers. Leaf names alone collide across groups
        (RUSHING YDS vs RECEIVING YDS both render as "YDS"), so leaf headers are
        prefixed with their group label to disambiguate.
        """
        group_labels = []
        for cell in header_rows[0].find_all(["th", "td"]):
            colspan = int(cell.get("colspan", 1))
            group_labels.extend([cell.text.strip()] * colspan)

        leaf_headers = [th.text.strip() for th in header_rows[-1].find_all("th")]

        if len(group_labels) != len(leaf_headers):
            return leaf_headers

        return [
            f"{group}_{leaf}" if group and leaf != "Player" else leaf
            for group, leaf in zip(group_labels, leaf_headers)
        ]

    def fetch(self, position):
        """
        Fetches projections for a given position ('qb', 'rb', 'wr', 'te', 'k', 'dst').
        Returns a normalized DataFrame with player_name, team, position, source columns
        plus the raw FantasyPros stat columns for that position.
        """
        pos = position.lower()
        url = self.BASE_URL.format(position=pos)

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"Error fetching data for {position}: {e}")
            return pd.DataFrame()

        soup = BeautifulSoup(response.text, "lxml")
        table = soup.find("table", {"id": "data"})
        if not table:
            table = soup.find("table")
            if not table:
                print(f"No table found for {position}")
                return pd.DataFrame()

        headers = []
        thead = table.find("thead")
        if thead:
            rows = thead.find_all("tr")
            if len(rows) > 1:
                headers = self._build_grouped_headers(rows)
            else:
                headers = [th.text.strip() for th in rows[0].find_all("th")]
        else:
            headers = [th.text.strip() for th in table.find_all("th")]

        if not headers:
            print(f"Could not parse headers for {position}")
            return pd.DataFrame()

        data_rows = []
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in rows:
            cols = row.find_all("td")
            if not cols:
                continue

            row_data = [col.text.strip() for col in cols]

            if len(row_data) == len(headers):
                data_rows.append(row_data)
            elif len(row_data) > len(headers):
                data_rows.append(row_data[: len(headers)])
            else:
                row_data += [""] * (len(headers) - len(row_data))
                data_rows.append(row_data)

        df = pd.DataFrame(data_rows, columns=headers)

        if "Player" in df.columns:
            player_info = df["Player"].apply(self._parse_player_team)
        else:
            player_info = df.iloc[:, 0].apply(self._parse_player_team)

        player_names = [info[0] for info in player_info]
        teams = [info[1] for info in player_info]

        df = df.assign(
            player_name=player_names,
            team=teams,
            position=position.upper(),
            source=self.source_name,
        )

        identity_columns = {"Player", "player_name", "team", "position", "source"}
        for i in range(len(df.columns)):
            col_name = df.columns[i]
            if col_name not in identity_columns:
                series = df.iloc[:, i].astype(str).str.replace(",", "", regex=False)
                numeric_series = pd.to_numeric(series, errors="coerce").fillna(0.0)
                df.iloc[:, i] = numeric_series

        if "Player" in df.columns:
            df = df.drop(columns=["Player"])

        return df


if __name__ == "__main__":
    fetcher = FantasyProsFetcher()
    print("Fetching QBs...")
    qb_df = fetcher.fetch("qb")
    print(qb_df.head())
