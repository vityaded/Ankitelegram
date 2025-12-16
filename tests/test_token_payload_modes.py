from app.services.token_service import parse_payload


def test_legacy_payload():
    assert parse_payload("deck_ABC") == ("ABC", "anki")


def test_new_payloads():
    assert parse_payload("deckw_ABC") == ("ABC", "watch")


def test_dot_payloads():
    assert parse_payload("deck.anki.ABC") == ("ABC", "anki")
    assert parse_payload("deck.watch.ABC") == ("ABC", "watch")


def test_invalid_payload():
    assert parse_payload("deck.bad.ABC") is None
    assert parse_payload(None) is None
