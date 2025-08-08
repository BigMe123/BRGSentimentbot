from sentiment_bot.interactive import parse_multi_selection, parse_single_selection


def test_multi_all():
    assert parse_multi_selection("all", ["all", "africa"]) == []


def test_multi_list():
    assert parse_multi_selection("2,3", ["all", "africa", "asia"]) == [
        "africa",
        "asia",
    ]


def test_single_ok():
    assert parse_single_selection("2", ["all", "day"]) == "day"
