"""
Model vs Consensus Comparator
Compares model predictions with consensus forecasts and assigns grades
"""

import math
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ComparisonResult:
    """Result of comparing model vs consensus"""
    country: str
    year: int
    model_value: float
    consensus_value: float
    delta: float
    delta_pct: float
    grade: str
    sources_used: list
    confidence: Optional[float] = None
    flag: bool = False
    assessment: str = ""


def compare(model_forecast: Dict, consensus_forecast: Dict,
           abs_tol: float = 0.8, rel_tol: float = 0.35) -> Dict:
    """
    Compare model prediction with consensus forecast

    Args:
        model_forecast: Dict with model prediction data
        consensus_forecast: Dict with consensus data
        abs_tol: Absolute tolerance for flagging (percentage points)
        rel_tol: Relative tolerance for flagging (fraction)

    Returns:
        Dict with comparison results and grade
    """
    # Extract values
    country = model_forecast.get('country', 'Unknown')
    year = model_forecast.get('year', 2025)
    model_value = model_forecast.get('gdp_growth_pct')
    consensus_value = consensus_forecast.get('consensus_growth_pct')
    confidence = model_forecast.get('confidence')
    sources_used = consensus_forecast.get('sources_used', [])

    if model_value is None or consensus_value is None:
        return {
            'country': country,
            'year': year,
            'error': 'Missing model or consensus value',
            'grade': 'N/A'
        }

    # Calculate differences
    delta = model_value - consensus_value
    delta_pct = (delta / abs(consensus_value)) * 100 if consensus_value != 0 else 0

    # Assign grade based on absolute deviation
    abs_delta = abs(delta)

    if abs_delta < 0.3:
        grade = 'A'
        assessment = 'Excellent alignment'
    elif abs_delta < 0.5:
        grade = 'B'
        assessment = 'Good alignment'
    elif abs_delta < 0.8:
        grade = 'C'
        assessment = 'Moderate deviation'
    else:
        grade = 'D'
        assessment = 'Large deviation - CHECK'

    # Flag if both absolute and relative deviations are large
    flag = abs_delta > abs_tol and abs(delta_pct) > rel_tol

    return {
        'country': country,
        'year': year,
        'model_value': model_value,
        'consensus_value': consensus_value,
        'delta': delta,
        'delta_pct': delta_pct,
        'grade': grade,
        'assessment': assessment,
        'sources_used': sources_used,
        'confidence': confidence,
        'flag': flag,
        'abs_delta': abs_delta
    }


def format_comparison_line(comparison: Dict, verbose: bool = False) -> str:
    """
    Format comparison result as a single line

    Args:
        comparison: Comparison result dict
        verbose: Include additional details

    Returns:
        Formatted string
    """
    country = comparison['country']
    year = comparison['year']
    model_val = comparison['model_value']
    cons_val = comparison['consensus_value']
    delta = comparison['delta']
    grade = comparison['grade']
    confidence = comparison.get('confidence')
    sources = comparison.get('sources_used', [])
    flag = comparison.get('flag', False)

    # Format confidence
    conf_str = f" ({confidence*100:.0f}%)" if confidence else ""

    # Format sources
    sources_str = ','.join(sources) if sources else 'None'

    # Format flag
    flag_str = " ⚠️ CHECK" if flag else ""

    # Basic format
    line = (f"{country} {year} | model={model_val:.2f}%{conf_str} | "
           f"consensus={cons_val:.2f}% [{sources_str}] | "
           f"Δ={delta:+.2f} → grade {grade}{flag_str}")

    if verbose:
        assessment = comparison.get('assessment', '')
        line += f" ({assessment})"

    return line


def batch_compare(model_forecasts: Dict[str, Dict], consensus_forecasts: Dict[str, Dict],
                 abs_tol: float = 0.8, rel_tol: float = 0.35) -> Dict[str, Dict]:
    """
    Compare multiple model forecasts with consensus

    Args:
        model_forecasts: Dict mapping country to model forecast
        consensus_forecasts: Dict mapping country to consensus forecast
        abs_tol: Absolute tolerance for flagging
        rel_tol: Relative tolerance for flagging

    Returns:
        Dict mapping country to comparison result
    """
    results = {}

    for country in model_forecasts:
        model_forecast = model_forecasts[country]
        consensus_forecast = consensus_forecasts.get(country, {})

        # Add country to forecast data if not present
        model_forecast['country'] = country
        consensus_forecast['country'] = country

        result = compare(model_forecast, consensus_forecast, abs_tol, rel_tol)
        results[country] = result

    return results


def calculate_summary_stats(comparisons: Dict[str, Dict]) -> Dict:
    """
    Calculate summary statistics from comparison results

    Args:
        comparisons: Dict mapping country to comparison result

    Returns:
        Dict with summary statistics
    """
    valid_comparisons = [c for c in comparisons.values()
                        if 'error' not in c and 'delta' in c]

    if not valid_comparisons:
        return {'error': 'No valid comparisons'}

    deltas = [c['delta'] for c in valid_comparisons]
    abs_deltas = [abs(d) for d in deltas]
    grades = [c['grade'] for c in valid_comparisons]

    stats = {
        'total_countries': len(valid_comparisons),
        'mean_delta': sum(deltas) / len(deltas),
        'mean_abs_delta': sum(abs_deltas) / len(abs_deltas),
        'max_abs_delta': max(abs_deltas),
        'min_abs_delta': min(abs_deltas),
        'grade_distribution': {
            'A': grades.count('A'),
            'B': grades.count('B'),
            'C': grades.count('C'),
            'D': grades.count('D')
        },
        'flagged_countries': len([c for c in valid_comparisons if c.get('flag', False)]),
        'countries_within_0_5pp': len([d for d in abs_deltas if d < 0.5]),
        'countries_within_1_0pp': len([d for d in abs_deltas if d < 1.0])
    }

    # Success rate
    stats['success_rate_0_5pp'] = stats['countries_within_0_5pp'] / len(valid_comparisons) * 100
    stats['success_rate_1_0pp'] = stats['countries_within_1_0pp'] / len(valid_comparisons) * 100

    return stats


def rank_countries_by_accuracy(comparisons: Dict[str, Dict]) -> list:
    """
    Rank countries by forecast accuracy (smallest absolute delta first)

    Args:
        comparisons: Dict mapping country to comparison result

    Returns:
        List of (country, abs_delta, grade) tuples sorted by accuracy
    """
    valid_comparisons = [(country, comp) for country, comp in comparisons.items()
                        if 'error' not in comp and 'delta' in comp]

    # Sort by absolute delta
    ranked = sorted(valid_comparisons, key=lambda x: abs(x[1]['delta']))

    return [(country, abs(comp['delta']), comp['grade'])
            for country, comp in ranked]