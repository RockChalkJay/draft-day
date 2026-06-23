from src.ingestion.id_mapping import canonical_player_id, normalize_dst_name, normalize_name


def test_normalize_name_strips_suffix_and_punctuation():
    assert normalize_name("Patrick Mahomes") == normalize_name("Patrick Mahomes Jr.")
    assert normalize_name("A.J. Brown") == normalize_name("AJ Brown")


def test_normalize_dst_name_maps_full_name_to_abbr():
    assert normalize_dst_name("San Francisco 49ers") == "SF"
    assert normalize_dst_name("SF") == "SF"


def test_canonical_player_id_collapses_name_variants():
    assert canonical_player_id("Patrick Mahomes", "QB") == canonical_player_id("Patrick Mahomes Jr.", "QB")


def test_canonical_player_id_collapses_dst_variants():
    assert canonical_player_id("San Francisco 49ers", "DST") == canonical_player_id("SF", "DST")


def test_canonical_player_id_distinguishes_position():
    assert canonical_player_id("Travis Kelce", "TE") != canonical_player_id("Travis Kelce", "WR")
