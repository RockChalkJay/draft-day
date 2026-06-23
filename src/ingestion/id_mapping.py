import re

SUFFIX_PATTERN = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]")

# DST rows are inconsistent across sources: some give the full team name
# ("San Francisco 49ers"), some give just the abbreviation ("SF"). Both must
# collapse to the same canonical_player_id, so team names are normalized here.
TEAM_NAME_TO_ABBR = {
    "arizona cardinals": "ARI", "atlanta falcons": "ATL", "baltimore ravens": "BAL",
    "buffalo bills": "BUF", "carolina panthers": "CAR", "chicago bears": "CHI",
    "cincinnati bengals": "CIN", "cleveland browns": "CLE", "dallas cowboys": "DAL",
    "denver broncos": "DEN", "detroit lions": "DET", "green bay packers": "GB",
    "houston texans": "HOU", "indianapolis colts": "IND", "jacksonville jaguars": "JAC",
    "kansas city chiefs": "KC", "las vegas raiders": "LV", "los angeles chargers": "LAC",
    "los angeles rams": "LAR", "miami dolphins": "MIA", "minnesota vikings": "MIN",
    "new england patriots": "NE", "new orleans saints": "NO", "new york giants": "NYG",
    "new york jets": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT",
    "san francisco 49ers": "SF", "seattle seahawks": "SEA", "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN", "washington commanders": "WAS",
}


def normalize_name(name: str) -> str:
    name = name.lower()
    name = SUFFIX_PATTERN.sub("", name)
    name = NON_ALNUM_PATTERN.sub("", name)
    return name.strip()


def normalize_dst_name(player_name: str) -> str:
    lookup = player_name.lower().strip()
    return TEAM_NAME_TO_ABBR.get(lookup, player_name)


def canonical_player_id(player_name: str, position: str) -> str:
    """
    Deterministic stand-in for a real cross-source ID crosswalk (e.g. nflverse's
    player ID mapping table). Until that crosswalk is wired in, identity is derived
    from normalized name + position so the same player from different sources
    collapses to one row in merge.py. DST rows are normalized to their team
    abbreviation first since sources disagree on full-name vs. abbreviation.
    """
    pos = position.upper()
    name = normalize_dst_name(player_name) if pos == "DST" else player_name
    return f"{normalize_name(name)}_{pos.lower()}"
