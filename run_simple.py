"""Offline demonstration of the sentiment analyzer on sample texts."""

from sentiment_bot import analyzer


def main() -> None:
    texts = [
        "Markets had a great day with excellent earnings and investors happy.",
        "The outlook was terrible and investors faced a bad recession.",
    ]
    analyses = [analyzer.analyze(t) for t in texts]
    snap = analyzer.aggregate(analyses)
    # Sanity checks
    assert 0 < snap.volatility < 1, "volatility should be within (0, 1)"
    assert 0 < snap.confidence < 1, "confidence should be within (0, 1)"
    assert snap.alert_level == "normal", "expected normal alert level"
    print(f"Volatility {snap.volatility:.3f} (confidence {snap.confidence:.2f})")


if __name__ == "__main__":
    main()
