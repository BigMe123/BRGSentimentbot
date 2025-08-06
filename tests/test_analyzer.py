import pathlib
import sys

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import analyzer


def test_analyze_vader_positive() -> None:
    res = analyzer.analyze("This is an amazing and wonderful day!")
    assert res.vader > 0
    assert isinstance(res.low_quality, bool)


def test_aggregate_basic() -> None:
    res1 = analyzer.Analysis(0.5, 0.0, [], "")
    res2 = analyzer.Analysis(-0.5, 0.0, [], "")
    snap = analyzer.aggregate([res1, res2])
    assert 0 <= snap.volatility <= 1
    assert 0 < snap.confidence < 1
