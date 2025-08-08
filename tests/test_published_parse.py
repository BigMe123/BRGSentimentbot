from sentiment_bot.cli import _try_parse_iso


def test_iso_ok():
    assert _try_parse_iso("2025-08-08T10:00:00+00:00")


def test_naive_gets_utc():
    assert _try_parse_iso("2025-08-08T10:00:00").tzinfo is not None


def test_bad_returns_none():
    assert _try_parse_iso("not-a-date") is None
