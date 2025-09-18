"""
Unit tests for consensus comparator
"""

import math
import pytest
from sentiment_bot.consensus.comparator import compare, batch_compare, calculate_summary_stats


def test_grade_thresholds():
    """Test that grade thresholds work correctly"""
    # A-grade: small delta
    result = compare(
        {
            "country": "USA",
            "year": 2025,
            "gdp_growth_pct": 2.05,
            "confidence": 0.7
        },
        {
            "country": "USA",
            "year": 2025,
            "consensus_growth_pct": 2.10,
            "sources_used": ["WB", "IMF", "OECD"]
        }
    )
    assert result["grade"] == "A"
    assert abs(result["delta"] - (-0.05)) < 0.001  # Allow for floating point precision
    assert math.isfinite(result["delta"])

    # D-grade: large deviation
    result2 = compare(
        {
            "country": "GBR",
            "year": 2025,
            "gdp_growth_pct": 3.07,
            "confidence": 0.26
        },
        {
            "country": "GBR",
            "year": 2025,
            "consensus_growth_pct": 1.60,
            "sources_used": ["WB", "IMF", "OECD"]
        }
    )
    assert result2["grade"] in ("C", "D")
    assert math.isfinite(result2["delta"])
    assert result2["flag"] == True  # Should be flagged as large deviation


def test_edge_cases():
    """Test edge cases in comparison"""
    # Missing consensus
    result = compare(
        {"country": "XXX", "year": 2025, "gdp_growth_pct": 2.0},
        {"country": "XXX", "year": 2025, "consensus_growth_pct": None}
    )
    assert "error" in result

    # Zero consensus (relative percentage handling)
    result2 = compare(
        {"country": "ZZZ", "year": 2025, "gdp_growth_pct": 1.0},
        {"country": "ZZZ", "year": 2025, "consensus_growth_pct": 0.0}
    )
    assert result2["delta_pct"] == 0  # Should handle division by zero


def test_batch_compare():
    """Test batch comparison functionality"""
    model_forecasts = {
        "USA": {"gdp_growth_pct": 1.86, "confidence": 0.67},
        "DEU": {"gdp_growth_pct": 1.52, "confidence": 0.51}
    }

    consensus_forecasts = {
        "USA": {"consensus_growth_pct": 2.10, "sources_used": ["WB", "IMF"]},
        "DEU": {"consensus_growth_pct": 1.30, "sources_used": ["WB", "OECD"]}
    }

    results = batch_compare(model_forecasts, consensus_forecasts)

    assert len(results) == 2
    assert "USA" in results
    assert "DEU" in results
    assert results["USA"]["grade"] in ["A", "B", "C", "D"]
    assert results["DEU"]["grade"] in ["A", "B", "C", "D"]


def test_summary_stats():
    """Test summary statistics calculation"""
    comparisons = {
        "USA": {
            "delta": -0.24,
            "grade": "A",
            "flag": False
        },
        "DEU": {
            "delta": 0.22,
            "grade": "A",
            "flag": False
        },
        "JPN": {
            "delta": -1.05,
            "grade": "D",
            "flag": True
        }
    }

    stats = calculate_summary_stats(comparisons)

    assert stats["total_countries"] == 3
    assert stats["grade_distribution"]["A"] == 2
    assert stats["grade_distribution"]["D"] == 1
    assert stats["flagged_countries"] == 1
    assert "mean_abs_delta" in stats


def test_confidence_handling():
    """Test that confidence is properly handled"""
    result = compare(
        {
            "country": "FRA",
            "year": 2025,
            "gdp_growth_pct": 0.63,
            "confidence": 0.632
        },
        {
            "country": "FRA",
            "year": 2025,
            "consensus_growth_pct": 1.30,
            "sources_used": ["WB", "IMF", "OECD"]
        }
    )

    assert result["confidence"] == 0.632
    assert "confidence" in result


if __name__ == "__main__":
    # Run tests if called directly
    test_grade_thresholds()
    test_edge_cases()
    test_batch_compare()
    test_summary_stats()
    test_confidence_handling()
    print("✅ All comparator tests passed!")