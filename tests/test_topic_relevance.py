from sentiment_bot.cli_unified import _keyword_filter
from sentiment_bot.topic_relevance import score_article_relevance


def article(title, body="", source="Reuters"):
    return {
        "title": title,
        "description": body,
        "content": body,
        "domain": source,
    }


def test_microchips_keeps_international_semiconductor_policy():
    a = article(
        "US expands China chip export controls as ASML faces new limits",
        "The rules target advanced semiconductors, EUV lithography, Nvidia GPUs, TSMC supply chains and Taiwan foundries.",
    )
    decision = score_article_relevance(a, topic="microchips", strict=True)
    assert decision.keep
    assert decision.topic == "microchips"
    assert decision.score >= 0.62


def test_microchips_drops_incidental_comics_reference():
    a = article(
        "Punisher brings back Microchip in new comic arc",
        "The story focuses on Marvel characters and streaming adaptations with no semiconductor industry relevance.",
    )
    decision = score_article_relevance(a, topic="microchips", strict=True)
    assert not decision.keep
    assert "context" in decision.reason or "international" in decision.reason


def test_microchips_drops_food_and_blue_chip_noise():
    noisy = [
        article("Best potato chips for summer cooking", "A recipe column tests salt and vinegar snacks."),
        article("Blue chip stocks edge higher before Fed decision", "Generic market coverage with no semiconductor supply chain angle."),
        article("Blue-chip stocks edge higher before Fed decision", "Generic market coverage with no semiconductor supply chain angle."),
    ]
    kept = _keyword_filter(noisy, topic="microchips", strict=True)
    assert kept == []


def test_microchips_requires_international_context():
    a = article(
        "Intel opens new chip packaging lab in Ohio",
        "The local facility focuses on domestic hiring and regional development.",
    )
    decision = score_article_relevance(a, topic="microchips", strict=True)
    assert not decision.keep
    assert "international" in decision.reason


def test_microchip_sanctions_keeps_export_control_story():
    a = article(
        "U.S. tightens ASML chip export restrictions to China",
        "The export controls affect advanced lithography equipment, EUV tools and semiconductor fabrication.",
    )
    decision = score_article_relevance(a, topic="microchip sanctions", strict=True)
    assert decision.keep
    assert decision.topic == "microchip_sanctions"


def test_wokeness_keeps_policy_culture_war_story():
    a = article(
        "UK ministers attack woke DEI policies in universities",
        "The government said education policy and free speech rules would become an election issue.",
    )
    decision = score_article_relevance(a, topic="wokeness", strict=True)
    assert decision.keep
    assert decision.topic == "wokeness"


def test_wokeness_drops_ordinary_woke_phrase():
    a = article(
        "Family woke up early for holiday travel",
        "The article is about airport delays and sleep schedules.",
    )
    decision = score_article_relevance(a, topic="wokeness", strict=True)
    assert not decision.keep


def test_comma_topic_uses_or_semantics_for_iran_hormuz_oil():
    articles = [
        article(
            "Iran threatens Hormuz shipping as crude futures jump",
            "Oil traders cited tanker disruption, Brent prices and energy market risk.",
        ),
        article(
            "Olive oil recipe wins cooking award",
            "Food writers tested salads and pantry staples.",
        ),
    ]
    kept = _keyword_filter(articles, topic="Iran, Hormuz, Oil", strict=True)
    assert kept == [articles[0]]
