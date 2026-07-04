import json

from src.ingestion.fantasypros_adp_fetcher import FantasyProsADPFetcher


def _page(rows):
    config = {"type": "nfl_adp", "table": {"fields": [], "rows": rows}}
    return f"<html><script>\n    window.FP = window.FP || {{}};\n    window.FP.reportConfig = {json.dumps(config)};\n</script></html>"


def _row(rank, name, team_bye, pos, avg):
    return {"id": rank, "rank": rank, "player": {"id": rank, "name": name, "team": team_bye},
            "pos": pos, "avg": avg}


def test_parse_report_html_extracts_players():
    html = _page([
        _row(1, "Jahmyr Gibbs", "DET (6)", "RB1", 1.0),
        _row(2, "Ja'Marr Chase", "CIN (6)", "WR1", 3.2),
        _row(3, "Houston Texans", "HOU (8)", "DST1", 160.5),
    ])
    df = FantasyProsADPFetcher.parse_report_html(html)

    assert len(df) == 3
    gibbs = df.iloc[0]
    assert (gibbs["player_name"], gibbs["team"], gibbs["position"]) == ("Jahmyr Gibbs", "DET", "RB")
    assert gibbs["adp"] == 1.0 and gibbs["pos_rank"] == 1 and gibbs["bye"] == 6
    assert df.iloc[2]["position"] == "DST"


def test_parse_report_html_handles_missing_config():
    assert FantasyProsADPFetcher.parse_report_html("<html>no data</html>").empty


def test_fetch_discards_registration_fenced_teaser(monkeypatch):
    # Anonymous visitors get a ~5-row teaser; that must not be treated as real
    # ADP coverage (it would give 5 players an ADP and everyone else none).
    class _Resp:
        status_code = 200
        text = _page([_row(i, f"P{i}", "SF (8)", f"RB{i}", float(i)) for i in range(1, 6)])

        def raise_for_status(self):
            pass

    class _Session:
        headers = {}

        def get(self, url, timeout=None):
            return _Resp()

    df = FantasyProsADPFetcher(session=_Session()).fetch()
    assert df.empty
