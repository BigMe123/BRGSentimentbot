#!/usr/bin/env python
"""
Country-First Economic Prediction API
No US bias - each country gets appropriate model tier
"""

from flask import Flask, request, jsonify
from typing import Dict, Optional, Any
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all components
from core.country_adapter_base import DataTier
from adapters.country_adapters import USAdapter, UKAdapter, GermanyAdapter, BrazilAdapter
from models.universal_regime_detector import UniversalRegimeDetector
from models.model_bundles import LiteBundle, StandardBundle, PlusBundle
from models.confidence_intervals import ConfidenceIntervalEstimator
from models.recovery_scaler import IntegratedScaler
from evaluation.rolling_cv_evaluator import RollingCVEvaluator
from data_sources.wdi_data_fetcher import WDIDataFetcher

app = Flask(__name__)

# Global components
COUNTRY_ADAPTERS = {
    'US': USAdapter(),
    'UK': UKAdapter(),
    'DE': GermanyAdapter(),
    'BR': BrazilAdapter()
}

REGIME_DETECTOR = UniversalRegimeDetector(precision_target=0.8)
SCALER = IntegratedScaler()
CI_ESTIMATOR = ConfidenceIntervalEstimator(target_coverage=0.8)
DATA_FETCHER = WDIDataFetcher()

# Model cache per country
MODEL_CACHE = {}


def get_country_tier(country_code: str) -> DataTier:
    """
    Determine data tier for country
    """
    # Tier A: Rich data countries
    tier_a = ['US', 'UK', 'DE', 'FR', 'JP', 'CA', 'AU']
    # Tier B: Medium data
    tier_b = ['BR', 'IN', 'CN', 'MX', 'RU', 'KR', 'IT', 'ES']

    if country_code in tier_a:
        return DataTier.TIER_A
    elif country_code in tier_b:
        return DataTier.TIER_B
    else:
        return DataTier.TIER_C


def get_model_bundle(country_code: str) -> Any:
    """
    Get appropriate model bundle for country
    """
    if country_code in MODEL_CACHE:
        return MODEL_CACHE[country_code]

    tier = get_country_tier(country_code)

    if tier == DataTier.TIER_A:
        model = PlusBundle()
    elif tier == DataTier.TIER_B:
        model = StandardBundle()
    else:
        model = LiteBundle()

    MODEL_CACHE[country_code] = model
    return model


@app.route('/predict/<country_code>', methods=['POST'])
def predict_gdp(country_code: str):
    """
    Main prediction endpoint
    
    POST /predict/UK
    {
        "horizon": "Q1-2024",
        "features": {
            "pmi_services": 52.5,
            "pmi_manufacturing": 48.2,
            "sentiment_score": -0.15,
            "article_volume": 1250
        }
    }
    """
    try:
        data = request.json
        horizon = data.get('horizon', 'next_quarter')
        features = data.get('features', {})

        # Get country adapter
        if country_code in COUNTRY_ADAPTERS:
            adapter = COUNTRY_ADAPTERS[country_code]
        else:
            # Generic adapter for other countries
            from core.country_adapter_base import CountryAdapterBase
            adapter = CountryAdapterBase(country_code)

        # Load recent data
        end_date = datetime.now()
        start_date = datetime(end_date.year - 2, end_date.month, 1)
        
        # Try to get real data first
        try:
            indicators = DATA_FETCHER.fetch_country_data(
                country_code, start_date, end_date
            )
        except:
            # Fall back to adapter's data
            indicators = adapter.load_monthly_indicators(start_date, end_date)

        # Normalize features
        normalized_features = adapter.normalize_indicators(indicators)

        # Detect regime
        regime_features = {
            'article_volume_zscore': features.get('article_volume', 1000) / 1000,
            'sentiment_variance': abs(features.get('sentiment_score', 0)) * 2,
            'pmi_shock': features.get('pmi_services', 50) - 50,
            'fx_shock': features.get('fx_change', 0),
            'vix_level': features.get('vix', 20)
        }

        regime, crisis_prob, is_crisis = REGIME_DETECTOR.detect_regime(
            indicators, regime_features
        )

        # Get model and make prediction
        model = get_model_bundle(country_code)
        
        # Prepare features for model
        X = pd.DataFrame([normalized_features.iloc[-1]])
        
        # Base prediction
        base_prediction = model.predict(X)[0]

        # Get confidence intervals
        intervals = CI_ESTIMATOR.combine_intervals(
            X.values[0], regime, features.get('residual_variance')
        )

        # Apply recovery scaling
        scaled_result = SCALER.process_prediction(
            base_prediction, regime, country_code,
            regime_features, 
            (intervals['calibrated']['lower'], intervals['calibrated']['upper'])
        )

        # Prepare response
        response = {
            'country': country_code,
            'horizon': horizon,
            'prediction': {
                'point': round(scaled_result['final_prediction'], 2),
                'confidence_interval': {
                    'lower': round(scaled_result['confidence'][0], 2),
                    'upper': round(scaled_result['confidence'][1], 2),
                    'level': 0.8
                }
            },
            'regime': {
                'current': regime,
                'crisis_probability': round(crisis_prob, 3),
                'is_crisis': is_crisis
            },
            'model_info': {
                'tier': get_country_tier(country_code).value,
                'scaling_applied': scaled_result['scaling_applied'],
                'smoothing_applied': scaled_result['smoothing_applied']
            },
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'api_version': '2.0',
                'model_version': 'production_v1'
            }
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'error': str(e),
            'country': country_code
        }), 500


@app.route('/evaluate/<country_code>', methods=['GET'])
def evaluate_model(country_code: str):
    """
    Evaluate model performance for a country
    
    GET /evaluate/UK?start=2020-01&end=2023-12
    """
    try:
        start = request.args.get('start', '2020-01-01')
        end = request.args.get('end', '2023-12-31')

        # Get adapter and data
        if country_code in COUNTRY_ADAPTERS:
            adapter = COUNTRY_ADAPTERS[country_code]
        else:
            return jsonify({'error': 'Country not supported'}), 404

        # Load data
        start_date = pd.to_datetime(start)
        end_date = pd.to_datetime(end)
        
        indicators = adapter.load_monthly_indicators(start_date, end_date)
        gdp = adapter.load_quarterly_target(start_date, end_date)

        # Bridge to quarterly
        X_quarterly = adapter.bridge_to_quarterly(indicators)
        
        # Align with target
        common_dates = X_quarterly.index.intersection(gdp.index)
        X = X_quarterly.loc[common_dates]
        y = gdp.loc[common_dates]

        # Get model
        model = get_model_bundle(country_code)

        # Evaluate
        evaluator = RollingCVEvaluator(min_train_size=12, test_size=3)
        results = evaluator.evaluate_model(model, X, y, REGIME_DETECTOR)

        # Format response
        response = {
            'country': country_code,
            'evaluation_period': f"{start} to {end}",
            'metrics': results['overall'].to_dict() if results['overall'] else {},
            'by_regime': results['by_regime'],
            'extreme_events': {
                'total': len(results['extreme_events']),
                'captured': sum(1 for e in results['extreme_events'] if e['captured']),
                'details': results['extreme_events'][:5]  # Top 5
            },
            'model_tier': get_country_tier(country_code).value
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'error': str(e),
            'country': country_code
        }), 500


@app.route('/countries', methods=['GET'])
def list_countries():
    """
    List supported countries and their tiers
    """
    countries = {
        'tier_a': {
            'countries': ['US', 'UK', 'DE', 'FR', 'JP', 'CA', 'AU'],
            'description': 'Rich data - full indicators',
            'model': 'PlusBundle with interaction terms'
        },
        'tier_b': {
            'countries': ['BR', 'IN', 'CN', 'MX', 'RU', 'KR', 'IT', 'ES'],
            'description': 'Medium data - PMIs, CPI, trade',
            'model': 'StandardBundle with DFM'
        },
        'tier_c': {
            'countries': ['Others'],
            'description': 'Lean data - CPI, FX, headlines',
            'model': 'LiteBundle with ElasticNet'
        }
    }
    
    return jsonify(countries)


@app.route('/regime/<country_code>', methods=['GET'])
def get_regime(country_code: str):
    """
    Get current regime detection for a country
    """
    try:
        # Get latest indicators
        if country_code in COUNTRY_ADAPTERS:
            adapter = COUNTRY_ADAPTERS[country_code]
        else:
            return jsonify({'error': 'Country not supported'}), 404

        end_date = datetime.now()
        start_date = datetime(end_date.year - 1, end_date.month, 1)
        
        indicators = adapter.load_monthly_indicators(start_date, end_date)

        # Simple features from latest data
        latest = indicators.iloc[-1]
        features = {
            'pmi_shock': latest.get('pmi_services', 50) - 50,
            'article_volume_zscore': 0,  # Would need real article data
            'sentiment_variance': 0.15,
            'vix_level': 20
        }

        regime, crisis_prob, is_crisis = REGIME_DETECTOR.detect_regime(
            indicators, features
        )

        response = {
            'country': country_code,
            'regime': regime,
            'crisis_probability': round(crisis_prob, 3),
            'is_crisis': is_crisis,
            'stage_a_anomalies': REGIME_DETECTOR.detect_stage_a_changepoints(indicators),
            'stage_b_probability': round(crisis_prob, 3),
            'timestamp': datetime.now().isoformat()
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'error': str(e),
            'country': country_code
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    API health check
    """
    return jsonify({
        'status': 'healthy',
        'components': {
            'adapters': list(COUNTRY_ADAPTERS.keys()),
            'regime_detector': 'ready',
            'scaler': 'ready',
            'ci_estimator': 'ready'
        },
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    print("🌍 COUNTRY-FIRST ECONOMIC PREDICTION API")
    print("="*60)
    print("Endpoints:")
    print("  POST /predict/<country>  - Get GDP prediction")
    print("  GET  /evaluate/<country> - Evaluate model performance")
    print("  GET  /regime/<country>   - Get current regime")
    print("  GET  /countries          - List supported countries")
    print("  GET  /health            - Health check")
    print("\nStarting server on http://localhost:5000")
    print("="*60)
    
    app.run(debug=True, port=5000)