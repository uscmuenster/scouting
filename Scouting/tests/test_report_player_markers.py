from scripts import report


def test_is_player_totals_marker_variants() -> None:
    assert report._is_player_totals_marker("Spieler insgesamt")
    assert report._is_player_totals_marker("Spieler gesamt")
    assert report._is_player_totals_marker("Spieler insgesamt / Players total")
    assert report._is_player_totals_marker("Players Total")
    assert report._is_player_totals_marker("Players total / Spieler gesamt")
    assert not report._is_player_totals_marker("Spielerinnen Übersicht")
