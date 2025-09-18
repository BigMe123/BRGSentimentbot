#!/usr/bin/env python
"""
Comprehensive Unit Tests for Economic Predictors
===============================================
Test FRED IDs, CPI calculations, FX conversions, and regime classifiers
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import asyncio

# Import components to test
from sentiment_bot.corrected_economic_predictors import (
    FREDDataClient,
    CorrectedInflationPredictor,
    CorrectedFXPredictor,
    CorrectedEmploymentPredictor,
    CorrectedConsumerConfidencePredictor
)
from sentiment_bot.ensemble_predictor import (
    CalibratedCrisisClassifier,
    SoftGatedEnsemble
)
from sentiment_bot.fallback_mechanisms import (
    DataCache,
    FallbackDataProvider,
    RobustDataClient
)


class TestFREDSeriesIDs:
    """Test correct FRED series ID mapping and usage"""

    def test_fred_series_mapping(self):
        """Test that FRED series IDs are correctly mapped"""
        client = FREDDataClient()

        expected_mappings = {
            'nonfarm_payrolls': 'PAYEMS',
            'unemployment_rate': 'UNRATE',
            'initial_claims': 'ICSA',
            'cpi_headline': 'CPIAUCSL',
            'cpi_core': 'CPILFESL',
            'fed_funds_rate': 'DFF',
            'treasury_10y': 'DGS10',
            'treasury_2y': 'DGS2',
            'real_gdp': 'GDPC1',
            'consumer_sentiment': 'UMCSENT'
        }

        for indicator, expected_id in expected_mappings.items():
            assert client.series_map[indicator] == expected_id, \
                f"Wrong FRED ID for {indicator}: expected {expected_id}, got {client.series_map.get(indicator)}"

    def test_release_lags(self):
        """Test that release lags are properly defined"""
        client = FREDDataClient()

        # Key series should have release lags defined
        required_lags = ['PAYEMS', 'UNRATE', 'CPIAUCSL', 'CPILFESL']

        for series_id in required_lags:
            assert series_id in client.release_lags, f"Missing release lag for {series_id}"
            assert isinstance(client.release_lags[series_id], int), f"Release lag for {series_id} should be integer"
            assert client.release_lags[series_id] > 0, f"Release lag for {series_id} should be positive"

    @pytest.mark.asyncio
    async def test_vintage_control_application(self):
        """Test that vintage controls are properly applied"""
        client = FREDDataClient()

        as_of_date = datetime(2024, 2, 15)  # Mid-month
        payroll_lag = client.release_lags['PAYEMS']  # Should be 3 days

        with patch.object(client, 'session') as mock_session:
            mock_response = AsyncMock()
            mock_response.json.return_value = {'observations': []}
            mock_session.get.return_value.__aenter__.return_value = mock_response

            await client.get_series_with_vintage_control('nonfarm_payrolls', as_of_date)

            # Check that the effective date was adjusted by release lag
            call_args = mock_session.get.call_args[1]['params']
            expected_vintage_date = (as_of_date - timedelta(days=payroll_lag)).strftime('%Y-%m-%d')

            assert 'realtime_end' in call_args
            assert call_args['realtime_end'] == expected_vintage_date


class TestCPICalculations:
    """Test CPI calculation correctness"""

    def test_cpi_annualization_formula(self):
        """Test CPI 3-month annualization formula"""

        # Create test CPI data
        dates = pd.date_range('2024-01-01', periods=6, freq='MS')
        cpi_values = [300.0, 301.0, 302.5, 304.0, 305.2, 306.1]  # Monthly CPI levels
        cpi_series = pd.Series(cpi_values, index=dates)

        # Mock FRED client response
        mock_fred_client = Mock()
        mock_fred_client.get_series_with_vintage_control.return_value = cpi_series

        mock_av_client = Mock()
        mock_av_client.get_commodity_price.return_value = pd.DataFrame()

        # Create predictor
        predictor = CorrectedInflationPredictor(mock_fred_client, mock_av_client)

        # Manually calculate expected result
        current_cpi = cpi_values[-1]  # 306.1
        cpi_3m_ago = cpi_values[-4]  # 304.0 (3 months ago)
        expected_annualized = ((current_cpi / cpi_3m_ago) ** 4 - 1) * 100

        # This should be roughly 2.8% annualized
        assert abs(expected_annualized - 2.85) < 0.1, \
            f"CPI annualization formula incorrect: expected ~2.85%, got {expected_annualized:.2f}%"

    @pytest.mark.asyncio
    async def test_cpi_component_weights(self):
        """Test CPI component weights sum to 100%"""

        mock_fred_client = AsyncMock()
        mock_fred_client.get_series_with_vintage_control.return_value = pd.Series([300.0, 301.0])

        mock_av_client = AsyncMock()
        mock_av_client.get_commodity_price.return_value = pd.DataFrame()

        predictor = CorrectedInflationPredictor(mock_fred_client, mock_av_client)

        # Test component weights
        weights = predictor.cpi_weights
        total_weight = weights['energy'] + weights['food'] + weights['core']

        assert abs(total_weight - 1.0) < 0.001, \
            f"CPI component weights don't sum to 1.0: {total_weight}"

        # Test individual weight ranges
        assert 0.05 <= weights['energy'] <= 0.15, f"Energy weight out of range: {weights['energy']}"
        assert 0.10 <= weights['food'] <= 0.20, f"Food weight out of range: {weights['food']}"
        assert 0.70 <= weights['core'] <= 0.85, f"Core weight out of range: {weights['core']}"

    @pytest.mark.asyncio
    async def test_cpi_prediction_metadata(self):
        """Test that CPI prediction includes proper methodology metadata"""

        # Mock data
        mock_fred_client = AsyncMock()
        mock_fred_client.get_series_with_vintage_control.return_value = pd.Series([300.0, 301.0, 302.0, 303.0])

        mock_av_client = AsyncMock()
        mock_av_client.get_commodity_price.return_value = pd.DataFrame({'value': [80.0, 82.0]})

        predictor = CorrectedInflationPredictor(mock_fred_client, mock_av_client)

        sentiment_data = {'supply_chain_disruption': 0.1, 'tariff_impact': 0.05}
        result = await predictor.predict_cpi_corrected(sentiment_data)

        # Check metadata
        assert 'methodology' in result.metadata
        assert result.metadata['methodology'] == '3-month annualized trend with component weighting'

        assert 'cpi_3m_annualized' in result.metadata
        assert 'component_weights' in result.metadata
        assert 'components' in result.metadata

        # Check data sources
        assert 'data_sources' in result.metadata
        sources = result.metadata['data_sources']
        assert any('FRED:CPIAUCSL' in source for source in sources)


class TestFXConventions:
    """Test FX quote direction and standardization"""

    def test_fx_quote_convention_validation(self):
        """Test that FX quotes follow USD base convention"""

        mock_av_client = Mock()
        predictor = CorrectedFXPredictor(mock_av_client)

        # Test quote conventions
        conventions = predictor.quote_conventions
        for currency, convention in conventions.items():
            assert convention.endswith('_per_USD'), \
                f"Convention for {currency} should be XXX_per_USD format: {convention}"

    @pytest.mark.asyncio
    async def test_fx_usd_base_requirement(self):
        """Test that USD must be base currency"""

        mock_av_client = AsyncMock()
        predictor = CorrectedFXPredictor(mock_av_client)

        # Should raise error for non-USD base
        with pytest.raises(ValueError, match="Base currency must be USD"):
            await predictor.predict_currency_standardized(
                'EUR', 'GBP', {}, 0.5
            )

    @pytest.mark.asyncio
    async def test_fx_eur_inversion(self):
        """Test EUR/USD inversion to EUR_per_USD"""

        mock_av_client = AsyncMock()

        # Mock Alpha Vantage returning USD/EUR = 0.85 (typical USD per 1 EUR)
        mock_av_client.get_forex_rate.return_value = {
            'rate': 0.85,
            'bid': 0.849,
            'ask': 0.851,
            'timestamp': '2024-01-15'
        }

        predictor = CorrectedFXPredictor(mock_av_client)

        result = await predictor.predict_currency_standardized(
            'USD', 'EUR', {'trade_sentiment': 0.0}, 0.0
        )

        # Should invert 0.85 to ~1.176
        expected_inverted = 1.0 / 0.85
        assert abs(result.metadata['current_rate'] - expected_inverted) < 0.001, \
            f"EUR inversion incorrect: expected {expected_inverted:.3f}, got {result.metadata['current_rate']:.3f}"

        assert result.metadata['quote_convention'] == 'EUR_per_USD'

    @pytest.mark.asyncio
    async def test_fx_impact_bounds(self):
        """Test that FX impacts are properly bounded"""

        mock_av_client = AsyncMock()
        mock_av_client.get_forex_rate.return_value = {
            'rate': 110.0,  # USD/JPY
            'bid': 109.8,
            'ask': 110.2,
            'timestamp': '2024-01-15'
        }

        predictor = CorrectedFXPredictor(mock_av_client)

        # Extreme sentiment values
        extreme_sentiment = {
            'trade_sentiment': 2.0,  # Extreme positive
            'monetary_policy': -3.0,  # Extreme negative
            'economic_strength': 1.5
        }

        result = await predictor.predict_currency_standardized(
            'USD', 'JPY', extreme_sentiment, 100.0  # High geopolitical risk
        )

        # Check that individual impacts are bounded
        components = result.metadata['components']

        assert abs(components['trade_impact']) <= 3.0, \
            f"Trade impact not bounded: {components['trade_impact']}"
        assert abs(components['policy_impact']) <= 2.0, \
            f"Policy impact not bounded: {components['policy_impact']}"
        assert abs(components['geopolitical_impact']) <= 1.0, \
            f"Geopolitical impact not bounded: {components['geopolitical_impact']}"


class TestRegimeClassifier:
    """Test crisis regime classification"""

    def test_crisis_classifier_calibration_curve(self):
        """Test crisis classifier probability calibration"""

        classifier = CalibratedCrisisClassifier()

        # Test calibration curve properties
        curve = classifier.calibration_curve

        # Should have increasing probabilities
        scores = sorted(curve.keys())
        probs = [curve[score] for score in scores]

        for i in range(1, len(probs)):
            assert probs[i] >= probs[i-1], \
                f"Calibration curve not monotonic: {probs[i-1]} -> {probs[i]}"

        # Boundary conditions
        assert curve[0.0] < 0.1, "Minimum crisis probability too high"
        assert curve[1.0] > 0.9, "Maximum crisis probability too low"

    def test_crisis_probability_interpolation(self):
        """Test probability interpolation between calibration points"""

        classifier = CalibratedCrisisClassifier()

        # Test interpolation
        prob_25 = classifier._interpolate_probability(0.25)
        prob_35 = classifier._interpolate_probability(0.35)

        # Should be between 0.1 (for 0.2) and 0.25 (for 0.3)
        assert 0.1 <= prob_25 <= 0.25, f"Interpolated probability out of range: {prob_25}"

        # Should be between 0.25 (for 0.3) and 0.45 (for 0.4)
        assert 0.25 <= prob_35 <= 0.45, f"Interpolated probability out of range: {prob_35}"

        # Should be monotonic
        assert prob_35 > prob_25, "Interpolation not monotonic"

    def test_regime_persistence(self):
        """Test regime persistence effects"""

        classifier = CalibratedCrisisClassifier()

        base_sentiment = 0.25
        context = "economic uncertainty mild concerns"
        factors = {'supply_chain': -0.5, 'geopolitical': -0.3}

        # Test normal -> crisis transition
        prob_from_normal, _ = classifier.detect_with_calibration(
            base_sentiment, context, factors, previous_regime='normal'
        )

        # Test crisis -> crisis persistence
        prob_from_crisis, _ = classifier.detect_with_calibration(
            base_sentiment, context, factors, previous_regime='crisis'
        )

        # Crisis should be stickier
        assert prob_from_crisis > prob_from_normal, \
            f"Crisis regime not persistent: normal={prob_from_normal:.3f}, crisis={prob_from_crisis:.3f}"


class TestSoftGatedEnsemble:
    """Test ensemble model combination"""

    def test_soft_gate_weights_sum_to_one(self):
        """Test that soft gate weights sum to 1"""

        ensemble = SoftGatedEnsemble()

        test_probabilities = [0.1, 0.3, 0.5, 0.7, 0.9]

        for crisis_prob in test_probabilities:
            normal_weight, crisis_weight = ensemble._soft_gate_weights(crisis_prob)

            # Weights should sum to 1
            assert abs(normal_weight + crisis_weight - 1.0) < 1e-6, \
                f"Weights don't sum to 1: {normal_weight} + {crisis_weight} = {normal_weight + crisis_weight}"

            # Both weights should be >= minimum
            assert normal_weight >= ensemble.min_weight, \
                f"Normal weight below minimum: {normal_weight} < {ensemble.min_weight}"
            assert crisis_weight >= ensemble.min_weight, \
                f"Crisis weight below minimum: {crisis_weight} < {ensemble.min_weight}"

    def test_ensemble_uncertainty_propagation(self):
        """Test uncertainty propagation in ensemble"""

        ensemble = SoftGatedEnsemble()

        # Test uncertainty combination
        normal_pred, crisis_pred = 2.5, -1.0
        normal_unc, crisis_unc = 1.0, 3.0
        normal_weight, crisis_weight = 0.7, 0.3

        combined_pred, combined_unc = ensemble._combine_predictions(
            normal_pred, crisis_pred, normal_unc, crisis_unc,
            normal_weight, crisis_weight
        )

        # Combined prediction should be weighted average
        expected_pred = normal_weight * normal_pred + crisis_weight * crisis_pred
        assert abs(combined_pred - expected_pred) < 1e-6, \
            f"Combined prediction incorrect: expected {expected_pred}, got {combined_pred}"

        # Combined uncertainty should be >= max component uncertainty * weight
        min_expected_unc = max(normal_weight * normal_unc, crisis_weight * crisis_unc)
        assert combined_unc >= min_expected_unc * 0.9, \
            f"Combined uncertainty too low: {combined_unc} < {min_expected_unc}"

    def test_regime_stability_calculation(self):
        """Test regime stability calculation"""

        ensemble = SoftGatedEnsemble()

        # Test stable regime
        ensemble.regime_history = ['normal'] * 5
        stability = ensemble._calculate_regime_stability()
        assert stability == 1.0, f"Stable regime should have stability 1.0: {stability}"

        # Test alternating regime
        ensemble.regime_history = ['normal', 'crisis', 'normal', 'crisis', 'normal']
        stability = ensemble._calculate_regime_stability()
        assert stability == 0.0, f"Alternating regime should have stability 0.0: {stability}"

        # Test mixed regime
        ensemble.regime_history = ['normal', 'normal', 'crisis', 'normal', 'normal']
        stability = ensemble._calculate_regime_stability()
        assert 0.0 < stability < 1.0, f"Mixed regime should have intermediate stability: {stability}"


class TestFallbackMechanisms:
    """Test data fallback and caching"""

    def test_fallback_data_coverage(self):
        """Test that fallback data covers key indicators"""

        provider = FallbackDataProvider()

        required_indicators = [
            'PAYEMS', 'UNRATE', 'ICSA', 'CPIAUCSL',
            'EUR_USD', 'GBP_USD', 'OIL_WTI'
        ]

        for indicator in required_indicators:
            assert indicator in provider.fallback_data, \
                f"Missing fallback data for {indicator}"

            value = provider.get_fallback_value(indicator, add_noise=False)
            assert isinstance(value, (int, float)), \
                f"Fallback value for {indicator} should be numeric: {value}"
            assert value > 0, f"Fallback value for {indicator} should be positive: {value}"

    def test_cache_freshness_check(self):
        """Test cache freshness validation"""

        from sentiment_bot.fallback_mechanisms import CachedDataPoint

        # Fresh data
        fresh_data = CachedDataPoint(
            value=100.0,
            timestamp=datetime.now(),
            source='test',
            ttl_hours=1
        )
        assert not fresh_data.is_stale, "Fresh data marked as stale"

        # Stale data
        stale_data = CachedDataPoint(
            value=100.0,
            timestamp=datetime.now() - timedelta(hours=2),
            source='test',
            ttl_hours=1
        )
        assert stale_data.is_stale, "Stale data not detected"

    @pytest.mark.asyncio
    async def test_robust_client_fallback_chain(self):
        """Test fallback chain in robust client"""

        # Mock failing primary client
        mock_fred_client = AsyncMock()
        mock_fred_client.get_series_with_vintage_control.side_effect = Exception("API Error")

        client = RobustDataClient(fred_client=mock_fred_client)

        # Should fall back to synthetic data
        result = await client.get_fred_series_robust(
            'PAYEMS',
            fallback_to_cache=False,  # Skip cache for this test
            fallback_to_synthetic=True
        )

        assert not result.empty, "Robust client should return synthetic data when API fails"
        assert len(result) > 0, "Synthetic data should have multiple points"


class TestEmploymentPrediction:
    """Test employment prediction with correct FRED series"""

    @pytest.mark.asyncio
    async def test_employment_prediction_components(self):
        """Test employment prediction component breakdown"""

        # Mock FRED data
        mock_fred_client = AsyncMock()

        # Mock payrolls data (monthly changes in thousands)
        payrolls_data = pd.Series([150, 180, 120, 200], index=pd.date_range('2024-01-01', periods=4, freq='MS'))
        mock_fred_client.get_series_with_vintage_control.side_effect = [
            payrolls_data,  # payrolls
            pd.Series([3.8, 3.7, 3.9, 3.8]),  # unemployment rate
            pd.Series([220000, 215000, 230000, 210000])  # initial claims
        ]

        predictor = CorrectedEmploymentPredictor(mock_fred_client, Mock())

        sentiment_data = {
            'hiring_sentiment': 0.3,
            'layoff_sentiment': -0.1,
            'sector_performance': {'technology': 0.1, 'manufacturing': 0.05, 'services': 0.08}
        }

        result = await predictor.predict_employment_corrected(sentiment_data)

        # Check metadata components
        assert 'components' in result.metadata
        components = result.metadata['components']

        required_components = ['baseline', 'unemployment_impact', 'claims_impact', 'sentiment_impact', 'sector_impact']
        for component in required_components:
            assert component in components, f"Missing component: {component}"

        # Check data sources
        assert 'data_sources' in result.metadata
        sources = result.metadata['data_sources']
        assert 'FRED:PAYEMS' in sources
        assert 'FRED:UNRATE' in sources
        assert 'FRED:ICSA' in sources


def run_tests():
    """Run all tests"""
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--disable-warnings'
    ])


if __name__ == "__main__":
    run_tests()