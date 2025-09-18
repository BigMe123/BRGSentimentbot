#!/usr/bin/env python3
"""
Demo script showing reason codes and offline mode banners in CLI/API context
"""

import sys
sys.path.append('.')

from sentiment_bot.consensus.dynamic_alpha import DynamicAlphaLearner, generate_synthetic_history
from sentiment_bot.utils.offline_banner import generate_offline_banner, get_cache_summary
import json
from datetime import datetime, timedelta

def create_mock_data_sources():
    """Create mock data sources with different cache states"""
    now = datetime.now()

    return [
        {
            'country': 'USA',
            'source': 'World Bank',
            'data': {2024: 2.3, 2025: 2.1},
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
            'source': 'IMF WEO',
            'data': {2024: 2.1, 2025: 2.2},
            '_cache_info': {
                'source': 'live_api',
                'provider': 'imf',
                'fetched_at': now.isoformat(),
                'age_hours': 0.0,
                'offline_mode': False
            }
        },
        {
            'country': 'USA',
            'source': 'OECD EO',
            'data': {2024: 2.2, 2025: 2.0},
            '_cache_info': {
                'source': 'cache',
                'provider': 'oecd',
                'cached_at': (now - timedelta(hours=18)).isoformat(),
                'age_hours': 18.0,
                'offline_mode': True
            }
        }
    ]


def demo_api_response():
    """
    Simulate API response with reason codes and offline banners
    """
    print("🔍 GDP Forecast Calibration API Demo")
    print("=" * 50)

    # Demonstrate offline mode banner
    print("\n📦 OFFLINE MODE DETECTION")
    print("-" * 30)

    mock_sources = create_mock_data_sources()
    offline_banner = generate_offline_banner(mock_sources)
    cache_summary = get_cache_summary(mock_sources)

    print(offline_banner)
    print(f"\nCache Summary: {cache_summary['cache_percentage']}% cached "
          f"({cache_summary['cached_sources']}/{cache_summary['total_sources']} sources)")

    print("\n" + "=" * 50)

    # Initialize and train learner
    learner = DynamicAlphaLearner()
    history = generate_synthetic_history(["USA", "GBR", "DEU"], n_years=6)
    model, _ = learner.train_alpha_model(history, model_type='huber')

    # Simulate API requests for different countries/scenarios
    api_requests = [
        {
            "country": "USA",
            "model_forecast": 2.1,
            "consensus_forecast": 2.3,
            "features": {
                "model_conf": 0.75,
                "consensus_disp": 0.25,
                "pmi_var_6m": 5.2,
                "fx_vol_3m": 0.08,
                "dm_flag": 1
            }
        },
        {
            "country": "GBR",
            "model_forecast": 3.2,
            "consensus_forecast": 1.8,
            "features": {
                "model_conf": 0.28,
                "consensus_disp": 0.75,
                "pmi_var_6m": 15.2,
                "fx_vol_3m": 0.22,
                "dm_flag": 1
            }
        },
        {
            "country": "BRA",
            "model_forecast": 1.8,
            "consensus_forecast": 2.2,
            "features": {
                "model_conf": 0.55,
                "consensus_disp": 0.45,
                "pmi_var_6m": 8.5,
                "fx_vol_3m": 0.18,
                "dm_flag": 0,  # Emerging market
                "china_exposure": 0.35
            }
        },
        {
            "country": "TUR",
            "model_forecast": 8.5,  # Extreme growth prediction
            "consensus_forecast": 3.2,
            "features": {
                "model_conf": 0.65,
                "consensus_disp": 0.8,  # High disagreement
                "pmi_var_6m": 14.0,    # High volatility
                "fx_vol_3m": 0.35,     # High FX volatility
                "dm_flag": 0           # Emerging market
            }
        },
        {
            "country": "ARG",
            "model_forecast": -6.2,  # Deep recession
            "consensus_forecast": -2.8,
            "features": {
                "model_conf": 0.25,    # Low confidence
                "consensus_disp": 0.9,  # Very high disagreement
                "pmi_var_6m": 18.0,    # Crisis-level volatility
                "fx_vol_3m": 0.45,     # Extreme FX volatility
                "dm_flag": 0           # Emerging market
            }
        }
    ]

    for i, request in enumerate(api_requests, 1):
        print(f"\n📊 Request {i}: {request['country']} GDP Forecast")
        print("-" * 40)

        # Get calibrated forecast with full reasoning and guardrails
        alpha, reasons = learner.infer_alpha(request['features'], return_reasons=True)
        alpha_adj, rule_reasons = learner.adjust_alpha_with_rules(alpha, request['features'])

        # Apply guardrails for extreme scenarios
        alpha_final, y_final, guardrail_reasons = learner.apply_guardrails(
            request['model_forecast'],
            request['consensus_forecast'],
            alpha_adj,
            request['features']
        )

        all_reasons = reasons + rule_reasons + guardrail_reasons

        # Get uncertainty bands
        bands = learner.calculate_uncertainty_bands(y_final, request['features'])

        # Format reason codes
        reason_summary = learner.format_reason_codes(all_reasons)

        # API response format
        api_response = {
            "country": request['country'],
            "input": {
                "model_forecast": request['model_forecast'],
                "consensus_forecast": request['consensus_forecast']
            },
            "output": {
                "calibrated_forecast": round(y_final, 2),
                "alpha_weight": round(alpha_final, 3),
                "uncertainty_bands": {
                    "p10": bands['p10'],
                    "p50": bands['p50'],
                    "p90": bands['p90']
                }
            },
            "reasoning": {
                "summary": reason_summary,
                "alpha_path": f"{alpha:.3f} → {alpha_adj:.3f} → {alpha_final:.3f}",
                "raw_codes": all_reasons[:6],  # First 6 for API brevity
                "confidence_factors": {
                    "model_confidence": request['features']['model_conf'],
                    "consensus_dispersion": request['features']['consensus_disp'],
                    "macro_volatility": request['features']['pmi_var_6m']
                },
                "guardrails_triggered": len(guardrail_reasons) > 0
            },
            "risk_assessment": bands['uncertainty']
        }

        # Display formatted response
        print(f"Input:  Model={request['model_forecast']:.1f}%, Consensus={request['consensus_forecast']:.1f}%")
        print(f"Output: Calibrated={api_response['output']['calibrated_forecast']:.1f}% (α={api_response['output']['alpha_weight']:.3f})")
        print(f"Range:  [{api_response['output']['uncertainty_bands']['p10']:.1f}%, {api_response['output']['uncertainty_bands']['p90']:.1f}%]")
        print(f"💡 Why: {api_response['reasoning']['summary']}")

        if rule_reasons:
            print(f"🔧 Rules: {', '.join(rule_reasons)}")

        if guardrail_reasons:
            print(f"🚨 Guardrails: {', '.join(guardrail_reasons)}")

        print(f"📈 Alpha: {api_response['reasoning']['alpha_path']}")
        print(f"🎯 Risk: {api_response['risk_assessment']:.1f} (uncertainty)")

        # Show JSON response (what API would return)
        if i == 1:  # Show full JSON for first example
            print(f"\n📋 Full API Response (JSON):")
            print(json.dumps(api_response, indent=2))

    print(f"\n✅ All forecasts include reasoning by default!")
    print("💡 This transparency helps users understand calibration decisions")

if __name__ == "__main__":
    demo_api_response()