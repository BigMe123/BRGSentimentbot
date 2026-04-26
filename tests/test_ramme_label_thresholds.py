from sentiment_bot.analyzers.finance_pipeline import RAMMEResult, _label_from_score
from sentiment_bot.analyzers.sentiment_router import _ramme_to_legacy


def _result(score: float, label: str = "neutral") -> RAMMEResult:
    return RAMMEResult(
        score=score,
        label=label,
        confidence=0.8,
        raw_confidence=0.8,
        risk_score=score,
        domain="general",
        primary_model="test",
    )


def test_ramme_labels_match_dashboard_thresholds():
    assert _label_from_score(0.06) == "positive"
    assert _label_from_score(-0.06) == "negative"
    assert _label_from_score(0.03) == "neutral"


def test_legacy_adapter_relabels_from_final_score():
    assert _ramme_to_legacy(_result(0.06)).label == "positive"
    assert _ramme_to_legacy(_result(-0.06)).label == "negative"
    assert _ramme_to_legacy(_result(0.03)).label == "neutral"


def test_legacy_adapter_keeps_abstain_neutral():
    r = _result(0.20, label="abstain")
    r.abstain = True
    assert _ramme_to_legacy(r).label == "neutral"
