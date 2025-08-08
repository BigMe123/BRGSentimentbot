import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import aggregate
from sentiment_bot.fetcher import Article


def test_aggregate_regions_and_keywords() -> None:
    art = Article(
        title="Paris protests escalate",
        url="u",
        text="Mass protests in Paris",
        published=None,
        source="test",
    )
    art.volatility = 0.5
    res = aggregate.aggregate([art], keywords=["protests"])
    assert "Europe" in res["regions"]
    region = res["regions"]["Europe"]
    assert region["count"] == 1
    assert region["keywords"][0]["name"] == "protests"

