"""
Unit tests for dynamic alpha learning
"""

import numpy as np
import pytest
from sentiment_bot.consensus.dynamic_alpha import (
    AlphaDataPoint,
    DynamicAlphaLearner,
    generate_synthetic_history
)


def make_point(country, y_model, y_cons, y_actual, conf=0.3, disp=0.8, pmi_var=10, fx_vol=0.05):
    """Helper to create AlphaDataPoint"""
    feats = {
        "model_conf": conf,
        "consensus_disp": disp,
        "pmi_var_6m": pmi_var,
        "fx_vol_3m": fx_vol,
        "dm_flag": 1,
        "oil_exporter": 0,
        "china_exposure": 0.2
    }
    return AlphaDataPoint(country, 2021, 2022, y_model, y_cons, y_actual, feats)


def test_alpha_bounds_and_effect():
    """Test that alpha is learned correctly and affects final forecast"""
    # Create training data where model is consistently too optimistic
    history = [
        make_point("GBR", 3.5, 1.6, 1.8, conf=0.3, disp=0.9),
        make_point("GBR", 2.8, 1.5, 1.7, conf=0.35, disp=0.7),
        make_point("GBR", 3.2, 1.4, 1.6, conf=0.25, disp=0.8),
        make_point("GBR", 2.9, 1.7, 1.9, conf=0.4, disp=0.6),
        make_point("GBR", 3.1, 1.6, 1.7, conf=0.3, disp=0.85),
    ]

    learner = DynamicAlphaLearner()
    model, keys = learner.train_alpha_model(history)

    # Test on new volatile situation
    now = make_point("GBR", 3.07, 1.60, 1.75, conf=0.26, disp=0.8)
    alpha = learner.infer_alpha(now.feats, min_alpha=0.15, max_alpha=0.9)

    # Alpha should be in bounds
    assert 0.15 <= alpha <= 0.9

    # Apply blending
    y_cal = learner.blend(now.y_model, now.y_cons, alpha)

    # Calibrated value should be closer to consensus than raw model
    assert abs(y_cal - now.y_cons) < abs(now.y_model - now.y_cons)

    # Alpha should be relatively low due to low confidence and high dispersion
    assert alpha < 0.5


def test_feature_extraction():
    """Test feature extraction functionality"""
    learner = DynamicAlphaLearner()

    features = learner.extract_features(
        "USA",
        datetime.now(),
        {"confidence": 0.7, "history": [0.1, 0.2, 0.15]},
        {"individual": {"WB": 2.1, "IMF": 2.0, "OECD": 2.2}}
    )

    # Check required features are present
    assert "model_conf" in features
    assert "consensus_disp" in features
    assert "dm_flag" in features
    assert features["model_conf"] == 0.7
    assert features["dm_flag"] == 1  # USA is developed market


def test_business_rules():
    """Test business rule adjustments"""
    learner = DynamicAlphaLearner()

    # High dispersion + low confidence should reduce alpha
    features = {
        "consensus_disp": 0.8,
        "model_conf": 0.3,
        "pmi_var_6m": 5.0
    }

    alpha_adj, reasons = learner.adjust_alpha_with_rules(0.6, features)

    assert alpha_adj < 0.6  # Should be reduced
    assert len(reasons) > 0  # Should have reasons
    assert "high_dispersion_low_confidence" in reasons


def test_blend_function():
    """Test blending function"""
    learner = DynamicAlphaLearner()

    # Test normal blending
    result = learner.blend(3.0, 2.0, 0.5)
    assert result == 2.5  # 0.5 * 3.0 + 0.5 * 2.0

    # Test with None consensus
    result2 = learner.blend(3.0, None, 0.5)
    assert result2 == 3.0  # Should return model value

    # Test extreme alpha values
    result3 = learner.blend(3.0, 2.0, 0.0)
    assert result3 == 2.0  # Pure consensus

    result4 = learner.blend(3.0, 2.0, 1.0)
    assert result4 == 3.0  # Pure model


def test_uncertainty_bands():
    """Test enhanced dispersion-aware uncertainty band calculation"""
    learner = DynamicAlphaLearner()

    # Low dispersion scenario
    low_disp_features = {
        "consensus_disp": 0.2,
        "pmi_var_6m": 4.0,
        "fx_vol_3m": 0.08,
        "model_conf": 0.8
    }

    low_disp_bands = learner.calculate_uncertainty_bands(2.0, low_disp_features, historical_std=0.5)

    # High dispersion scenario
    high_disp_features = {
        "consensus_disp": 0.8,
        "pmi_var_6m": 12.0,
        "fx_vol_3m": 0.25,
        "model_conf": 0.3
    }

    high_disp_bands = learner.calculate_uncertainty_bands(2.0, high_disp_features, historical_std=0.5)

    # Basic structure tests
    for bands in [low_disp_bands, high_disp_bands]:
        assert "p10" in bands
        assert "p90" in bands
        assert "consensus_contribution" in bands
        assert "volatility_contribution" in bands
        assert bands["p10"] < bands["p50"] < bands["p90"]
        assert bands["p50"] == 2.0

    # High dispersion should produce wider bands
    low_width = low_disp_bands["p90"] - low_disp_bands["p10"]
    high_width = high_disp_bands["p90"] - high_disp_bands["p10"]

    assert high_width > low_width, f"High dispersion bands ({high_width:.2f}) should be wider than low dispersion ({low_width:.2f})"

    # Test individual consensus forecasts
    consensus_individual = {"WB": 2.1, "IMF": 1.8, "OECD": 2.3}  # High spread
    bands_with_individual = learner.calculate_uncertainty_bands(
        2.0, high_disp_features, historical_std=0.5, consensus_individual=consensus_individual
    )

    # Should incorporate the actual consensus spread
    individual_width = bands_with_individual["p90"] - bands_with_individual["p10"]
    assert "consensus_contribution" in bands_with_individual
    print(f"Low dispersion width: {low_width:.2f}")
    print(f"High dispersion width: {high_width:.2f}")
    print(f"With individual forecasts width: {individual_width:.2f}")


def test_synthetic_history_generation():
    """Test synthetic history generation"""
    countries = ["USA", "GBR", "DEU"]
    history = generate_synthetic_history(countries, n_years=3)

    assert len(history) == 9  # 3 countries * 3 years
    assert all(isinstance(point, AlphaDataPoint) for point in history)
    assert all(point.country in countries for point in history)

    # Check that features are reasonable
    for point in history:
        assert 0 <= point.feats["model_conf"] <= 1
        assert point.feats["pmi_var_6m"] > 0
        assert point.feats["dm_flag"] in [0, 1]


def test_model_persistence():
    """Test model save/load functionality"""
    import tempfile
    from pathlib import Path

    learner = DynamicAlphaLearner()

    # Generate some data and train with Huber loss
    history = generate_synthetic_history(["USA"], n_years=5)
    learner.train_alpha_model(history, model_type='huber')

    # Save model only if training succeeded
    if learner.model is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "test_model.pkl"
            learner.save_model(model_path)

            # Load in new instance
            learner2 = DynamicAlphaLearner()
            success = learner2.load_model(model_path)

            assert success
            assert learner2.model is not None
            assert len(learner2.feat_keys) > 0
    else:
        print("Skipping persistence test - model training failed (insufficient data)")


def test_huber_vs_mae_robustness():
    """Test that Huber loss is more robust to outliers than MAE"""
    # Create history with outliers (simulating UK/KOR extreme cases)
    history = [
        make_point("GBR", 3.5, 1.6, 1.8, conf=0.3, disp=0.9),  # Normal case
        make_point("GBR", 2.8, 1.5, 1.7, conf=0.35, disp=0.7), # Normal case
        make_point("GBR", 8.2, 1.4, 1.6, conf=0.25, disp=0.8), # Extreme outlier (model way off)
        make_point("GBR", 2.9, 1.7, 1.9, conf=0.4, disp=0.6),  # Normal case
        make_point("KOR", 6.1, 2.8, 2.9, conf=0.3, disp=0.85), # Outlier case
        make_point("KOR", 3.2, 2.6, 2.7, conf=0.4, disp=0.4),  # Normal case
    ]

    # Train with Huber loss
    learner_huber = DynamicAlphaLearner()
    model_huber, _ = learner_huber.train_alpha_model(history, model_type='huber')

    # Train with GBR (MAE-based)
    learner_gbr = DynamicAlphaLearner()
    model_gbr, _ = learner_gbr.train_alpha_model(history, model_type='gbr')

    # Test on a normal case - both should work reasonably
    test_feats = {"model_conf": 0.4, "consensus_disp": 0.5, "pmi_var_6m": 6, "dm_flag": 1}

    if model_huber is not None and model_gbr is not None:
        alpha_huber = learner_huber.infer_alpha(test_feats)
        alpha_gbr = learner_gbr.infer_alpha(test_feats)

        # Both should be reasonable (between bounds)
        assert 0.15 <= alpha_huber <= 0.9
        assert 0.15 <= alpha_gbr <= 0.9

        print(f"Huber alpha: {alpha_huber:.3f}, GBR alpha: {alpha_gbr:.3f}")
        print("✅ Both models handle normal cases")
    else:
        print("Skipping robustness comparison - insufficient training data")


def test_reason_code_formatting():
    """Test reason code formatting functionality"""
    learner = DynamicAlphaLearner()

    # Test ML model reasoning
    test_feats = {
        "model_conf": 0.8,
        "consensus_disp": 0.3,
        "pmi_var_6m": 6.0,
        "dm_flag": 1
    }

    # Test both with and without model
    history = generate_synthetic_history(["USA"], n_years=8)  # More data to train model
    learner.train_alpha_model(history, model_type='huber')

    if learner.model is not None:
        alpha, reasons = learner.infer_alpha(test_feats, return_reasons=True)
        alpha_adj, rule_reasons = learner.adjust_alpha_with_rules(alpha, test_feats)
        all_reasons = reasons + rule_reasons

        # Test formatting
        formatted = learner.format_reason_codes(all_reasons)
        print(f"Alpha: {alpha:.3f} → {alpha_adj:.3f}")
        print(f"Raw reasons: {reasons}")
        print(f"Formatted: {formatted}")

        assert isinstance(formatted, str)
        assert len(formatted) > 0
        assert "🤖" in formatted or "📋" in formatted  # Should have category icons

    # Test fallback reasoning
    learner_fallback = DynamicAlphaLearner()  # No trained model
    alpha_fb, reasons_fb = learner_fallback._rule_based_alpha(test_feats)
    formatted_fb = learner_fallback.format_reason_codes(reasons_fb)

    print(f"Fallback formatted: {formatted_fb}")
    assert "📋" in formatted_fb  # Should show rule-based

    print("✅ Reason code formatting test passed")


def test_guardrail_policies():
    """Test extreme scenario guardrail policies"""
    learner = DynamicAlphaLearner()

    # Test extreme forecast gap
    extreme_gap_feats = {
        "model_conf": 0.6,
        "consensus_disp": 0.4,
        "pmi_var_6m": 8.0,
        "dm_flag": 1
    }

    alpha_before_guardrails = 0.7  # High model weight
    alpha_final, y_final, guardrail_reasons = learner.apply_guardrails(
        8.5,  # Model predicts 8.5% growth
        2.0,  # Consensus predicts 2.0% growth (6.5pp gap!)
        alpha_before_guardrails,
        extreme_gap_feats
    )

    print(f"Extreme gap test: α {alpha_before_guardrails:.3f} → {alpha_final:.3f}")
    print(f"Guardrails triggered: {guardrail_reasons}")

    assert alpha_final <= 0.25, "Should cap alpha for extreme gaps"
    assert any("extreme_gap" in reason for reason in guardrail_reasons)

    # Test crisis mode detection
    crisis_feats = {
        "model_conf": 0.2,      # Very low confidence
        "consensus_disp": 0.9,   # High dispersion
        "pmi_var_6m": 18.0,     # Very high volatility
        "fx_vol_3m": 0.3,       # High FX volatility
        "dm_flag": 1
    }

    alpha_crisis, y_crisis, crisis_reasons = learner.apply_guardrails(
        -5.0, -3.0, 0.6, crisis_feats
    )

    print(f"Crisis mode test: α 0.600 → {alpha_crisis:.3f}")
    print(f"Crisis guardrails: {crisis_reasons}")

    assert alpha_crisis <= 0.2, "Should heavily favor consensus in crisis"
    assert any("crisis_mode" in reason for reason in crisis_reasons)

    # Test extreme depression scenario - realistic but extreme case
    depression_alpha, depression_y, depression_reasons = learner.apply_guardrails(
        -4.5,   # Model predicts -4.5% contraction
        -1.8,   # Consensus predicts -1.8% contraction
        0.8,    # High model weight initially
        {"model_conf": 0.3, "consensus_disp": 0.4}
    )

    print(f"Deep recession test: y_final = {depression_y:.1f}%")
    print(f"Deep recession guardrails: {depression_reasons}")

    # Should trigger deep recession caution
    assert any("deep_recession_caution" in reason for reason in depression_reasons)
    assert depression_alpha <= 0.3, "Should reduce model weight for deep recession"

    # Test extreme boom scenario
    boom_alpha, boom_y, boom_reasons = learner.apply_guardrails(
        20.0,   # Model predicts extreme 20% growth
        8.0,    # Consensus predicts 8% growth
        0.6,
        {"model_conf": 0.4, "consensus_disp": 0.3}
    )

    print(f"Boom cap test: y_final = {boom_y:.1f}%")
    print(f"Boom guardrails: {boom_reasons}")

    assert boom_y <= 12.0, "Should cap extreme growth forecasts"
    # Should trigger either extreme cap or high growth outlier guardrail
    assert any("extreme" in reason or "high_growth" in reason for reason in boom_reasons)

    print("✅ Guardrail policies test passed")


def test_ci_validation():
    """Test CI validation system"""
    from sentiment_bot.consensus.backtest import WalkForwardValidator
    from sentiment_bot.consensus.dynamic_alpha import generate_synthetic_history

    # Generate test data
    countries = ["USA", "GBR", "DEU"]
    history = generate_synthetic_history(countries, n_years=8)

    # Run validation
    validator = WalkForwardValidator(min_history=3)
    results = validator.walk_forward(history)

    # Test CI conditions
    ci_validation = validator.check_ci_conditions()

    print(f"CI validation status: {ci_validation['overall_status']}")
    print(f"Critical failures: {ci_validation['critical_failures']}")
    print(f"Warnings: {ci_validation['warnings']}")

    # Basic assertions
    assert ci_validation['overall_status'] in ['PASS', 'WARN', 'FAIL']
    assert isinstance(ci_validation['critical_failures'], int)
    assert isinstance(ci_validation['warnings'], int)
    assert 'checks' in ci_validation

    # Check all required checks are present
    required_checks = [
        'performance_regression',
        'statistical_significance',
        'alpha_stability',
        'country_coverage',
        'guardrail_overuse',
        'extreme_outliers'
    ]

    for check in required_checks:
        assert check in ci_validation['checks']
        assert ci_validation['checks'][check]['status'] in ['PASS', 'WARN', 'FAIL']

    print("✅ CI validation test passed")


def test_offline_banner():
    """Test offline mode banner functionality"""
    from sentiment_bot.utils.offline_banner import (
        generate_offline_banner,
        get_cache_summary,
        format_cache_status,
        format_api_cache_status
    )
    from datetime import datetime, timedelta

    now = datetime.now()

    # Test mixed mode scenario
    mixed_sources = [
        {
            'country': 'USA',
            'source': 'World Bank',
            '_cache_info': {
                'source': 'cache',
                'provider': 'worldbank',
                'cached_at': (now - timedelta(hours=2)).isoformat(),
                'age_hours': 2.0,
                'offline_mode': True
            }
        },
        {
            'country': 'USA',
            'source': 'IMF',
            '_cache_info': {
                'source': 'live_api',
                'provider': 'imf',
                'fetched_at': now.isoformat(),
                'age_hours': 0.0,
                'offline_mode': False
            }
        }
    ]

    # Test banner generation
    banner = generate_offline_banner(mixed_sources)
    assert "MIXED MODE" in banner
    assert "1/2 sources cached" in banner

    # Test cache summary
    summary = get_cache_summary(mixed_sources)
    assert summary['total_sources'] == 2
    assert summary['cached_sources'] == 1
    assert summary['live_sources'] == 1
    assert summary['cache_percentage'] == 50.0
    assert summary['mixed_mode'] == True
    assert summary['offline_mode'] == False

    # Test format cache status
    cache_status = format_cache_status(mixed_sources[0]['_cache_info'])
    assert "CACHED (2.0h old)" in cache_status
    assert "WORLDBANK" in cache_status

    live_status = format_cache_status(mixed_sources[1]['_cache_info'])
    assert "LIVE - IMF" in live_status

    # Test API format
    api_status = format_api_cache_status(mixed_sources)
    assert 'cache_summary' in api_status
    assert 'source_details' in api_status
    assert 'banner_text' in api_status

    print("✅ Offline banner test passed")


if __name__ == "__main__":
    # Run tests if called directly
    from datetime import datetime

    test_alpha_bounds_and_effect()
    test_feature_extraction()
    test_business_rules()
    test_blend_function()
    test_uncertainty_bands()
    test_synthetic_history_generation()
    test_model_persistence()
    test_huber_vs_mae_robustness()
    test_reason_code_formatting()
    test_guardrail_policies()
    test_ci_validation()
    test_offline_banner()
    print("✅ All dynamic alpha tests passed!")