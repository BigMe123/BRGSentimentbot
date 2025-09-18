"""
Walk-Forward Validation Module
Validates calibrated forecasts against realized GDP
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from scipy import stats

from .dynamic_alpha import (
    DynamicAlphaLearner,
    AlphaDataPoint,
    generate_synthetic_history
)


class WalkForwardValidator:
    """
    Performs walk-forward validation of GDP forecasts
    Compares model, consensus, and calibrated forecasts against realized GDP
    """

    def __init__(self, min_history: int = 5):
        self.min_history = min_history
        self.results = []
        self.performance_metrics = {}

    def walk_forward(self, points: List[AlphaDataPoint],
                     expanding_window: bool = True) -> List[Dict]:
        """
        Walk-forward validation with dynamic alpha learning

        Args:
            points: Chronologically sorted list of AlphaDataPoint
            expanding_window: If True, use all prior data; if False, use fixed window

        Returns:
            List of forecast results with errors
        """
        # Sort by vintage year to ensure chronological order
        points = sorted(points, key=lambda p: (p.vintage_year, p.target_year))

        results = []

        for i in range(self.min_history, len(points)):
            # Training set
            if expanding_window:
                train_set = points[:i]  # All prior vintages
            else:
                # Fixed window (e.g., last 20 vintages)
                window_size = min(20, i)
                train_set = points[i-window_size:i]

            test_point = points[i]

            # Initialize learner for this vintage
            learner = DynamicAlphaLearner()

            # Train alpha model on historical data using Huber loss for outlier robustness
            model, feat_keys = learner.train_alpha_model(train_set, model_type='huber')

            if model is None:
                # Fallback to rule-based if insufficient data
                alpha, initial_reasons = learner._rule_based_alpha(test_point.feats)
            else:
                # Infer optimal alpha for test point with reasoning
                # Dynamic bounds based on confidence
                min_alpha = 0.15 if test_point.feats.get("model_conf", 0.5) >= 0.4 else 0.30
                alpha, initial_reasons = learner.infer_alpha(
                    test_point.feats, min_alpha=min_alpha, max_alpha=0.9, return_reasons=True
                )

            # Apply business rules
            alpha_adj, rule_reasons = learner.adjust_alpha_with_rules(alpha, test_point.feats)

            # Apply guardrails for extreme scenarios
            alpha_final, y_cal, guardrail_reasons = learner.apply_guardrails(
                test_point.y_model, test_point.y_cons, alpha_adj, test_point.feats
            )

            # Combine all reasoning codes
            all_reasons = initial_reasons + rule_reasons + guardrail_reasons

            # Calculate uncertainty bands
            # Get historical std from training set
            train_errors = [abs(p.y_actual - p.y_model) for p in train_set
                          if p.country == test_point.country and p.y_actual is not None]
            hist_std = np.std(train_errors) if train_errors else 0.8

            # Enhanced uncertainty bands with dispersion awareness
            bands = learner.calculate_uncertainty_bands(y_cal, test_point.feats, hist_std)

            # Store result with comprehensive reasoning and guardrails
            result = {
                "country": test_point.country,
                "vintage_year": test_point.vintage_year,
                "target_year": test_point.target_year,
                "y_actual": test_point.y_actual,
                "y_model": test_point.y_model,
                "y_cons": test_point.y_cons,
                "y_cal": y_cal,
                "alpha": alpha,
                "alpha_adj": alpha_adj,
                "alpha_final": alpha_final,
                "reason_codes": all_reasons,
                "rule_adjustments": rule_reasons,
                "guardrail_actions": guardrail_reasons,
                "bands": bands,
                "features": test_point.feats
            }

            results.append(result)

            # Print progress
            if i % 10 == 0:
                print(f"Processed {i}/{len(points)} vintages")

        self.results = results
        return results

    def calculate_metrics(self, results: List[Dict] = None) -> Dict:
        """
        Calculate performance metrics for each method
        """
        if results is None:
            results = self.results

        if not results:
            return {}

        # Extract errors
        errors = {
            'model': [],
            'consensus': [],
            'calibrated': []
        }

        for r in results:
            if r["y_actual"] is not None:
                if r["y_model"] is not None:
                    errors['model'].append(r["y_actual"] - r["y_model"])
                if r["y_cons"] is not None:
                    errors['consensus'].append(r["y_actual"] - r["y_cons"])
                if r["y_cal"] is not None:
                    errors['calibrated'].append(r["y_actual"] - r["y_cal"])

        # Calculate metrics
        metrics = {}

        for method, errs in errors.items():
            if errs:
                metrics[method] = {
                    'mae': float(np.mean(np.abs(errs))),
                    'rmse': float(np.sqrt(np.mean(np.square(errs)))),
                    'mape': float(np.mean(np.abs(errs / (np.array([r["y_actual"] for r in results
                                                                   if r["y_actual"] is not None]) + 0.01))) * 100),
                    'bias': float(np.mean(errs)),
                    'std': float(np.std(errs)),
                    'n': len(errs)
                }
            else:
                metrics[method] = {'mae': np.nan, 'rmse': np.nan, 'n': 0}

        # Calculate improvement
        if 'calibrated' in metrics and 'consensus' in metrics:
            if metrics['consensus']['mae'] > 0:
                metrics['improvement_vs_consensus'] = (
                    (metrics['consensus']['mae'] - metrics['calibrated']['mae']) /
                    metrics['consensus']['mae'] * 100
                )
            if metrics['model']['mae'] > 0:
                metrics['improvement_vs_model'] = (
                    (metrics['model']['mae'] - metrics['calibrated']['mae']) /
                    metrics['model']['mae'] * 100
                )

        self.performance_metrics = metrics
        return metrics

    def calculate_country_metrics(self, results: List[Dict] = None) -> Dict:
        """
        Calculate metrics by country
        """
        if results is None:
            results = self.results

        countries = set(r['country'] for r in results)
        country_metrics = {}

        for country in countries:
            country_results = [r for r in results if r['country'] == country]
            country_metrics[country] = self.calculate_metrics(country_results)

        return country_metrics

    def diebold_mariano_test(self, errors1: List[float], errors2: List[float],
                            horizon: int = 1) -> Tuple[float, float]:
        """
        Diebold-Mariano test for forecast accuracy comparison

        Returns:
            (DM statistic, p-value)
        """
        if len(errors1) != len(errors2):
            raise ValueError("Error series must have same length")

        # Calculate loss differential (using squared errors)
        d = np.square(errors1) - np.square(errors2)

        # Calculate test statistic
        mean_d = np.mean(d)
        var_d = np.var(d, ddof=1)

        # Adjust for forecast horizon if needed
        if horizon > 1:
            # Add autocorrelation adjustment
            acf_sum = sum([np.corrcoef(d[:-i], d[i:])[0, 1] for i in range(1, horizon)])
            var_d *= (1 + 2 * acf_sum)

        # DM statistic
        dm_stat = mean_d / np.sqrt(var_d / len(d))

        # Two-sided p-value
        p_value = 2 * (1 - stats.norm.cdf(abs(dm_stat)))

        return dm_stat, p_value

    def test_vs_consensus(self, results: List[Dict] = None) -> Dict:
        """
        Statistical test of calibrated vs consensus forecasts
        """
        if results is None:
            results = self.results

        # Extract paired errors
        paired_results = []
        for r in results:
            if all(v is not None for v in [r['y_actual'], r['y_cal'], r['y_cons']]):
                paired_results.append({
                    'err_cal': r['y_actual'] - r['y_cal'],
                    'err_cons': r['y_actual'] - r['y_cons']
                })

        if len(paired_results) < 10:
            return {'error': 'Insufficient paired observations'}

        errors_cal = [r['err_cal'] for r in paired_results]
        errors_cons = [r['err_cons'] for r in paired_results]

        # Diebold-Mariano test
        dm_stat, p_value = self.diebold_mariano_test(errors_cal, errors_cons)

        # Paired t-test as alternative
        t_stat, t_pvalue = stats.ttest_rel(
            np.abs(errors_cal),
            np.abs(errors_cons)
        )

        return {
            'diebold_mariano': {
                'statistic': dm_stat,
                'p_value': p_value,
                'significant': p_value < 0.10,
                'interpretation': 'Calibrated better' if dm_stat < 0 and p_value < 0.10
                                else 'No significant difference'
            },
            'paired_t_test': {
                'statistic': t_stat,
                'p_value': t_pvalue,
                'significant': t_pvalue < 0.05
            },
            'n_pairs': len(paired_results)
        }

    def calculate_alpha_stability(self, results: List[Dict] = None) -> Dict:
        """
        Analyze alpha stability over time
        """
        if results is None:
            results = self.results

        alphas = [r['alpha_adj'] for r in results if 'alpha_adj' in r]

        if not alphas:
            return {}

        return {
            'mean': np.mean(alphas),
            'std': np.std(alphas),
            'min': np.min(alphas),
            'max': np.max(alphas),
            'pct_at_bounds': sum(1 for a in alphas if a <= 0.15 or a >= 0.90) / len(alphas) * 100,
            'autocorrelation': np.corrcoef(alphas[:-1], alphas[1:])[0, 1] if len(alphas) > 1 else 0
        }

    def check_ci_conditions(self) -> Dict:
        """
        Check CI fail conditions for regression detection

        Returns:
            Dictionary with CI check results and pass/fail status
        """
        metrics = self.calculate_metrics()

        ci_checks = {
            "performance_regression": {"status": "PASS", "message": "", "critical": True},
            "statistical_significance": {"status": "PASS", "message": "", "critical": True},
            "alpha_stability": {"status": "PASS", "message": "", "critical": False},
            "country_coverage": {"status": "PASS", "message": "", "critical": True},
            "guardrail_overuse": {"status": "PASS", "message": "", "critical": False},
            "extreme_outliers": {"status": "PASS", "message": "", "critical": True}
        }

        # 1. Performance Regression Check
        cal_mae = metrics.get('calibrated', {}).get('mae', float('inf'))
        cons_mae = metrics.get('consensus', {}).get('mae', float('inf'))
        model_mae = metrics.get('model', {}).get('mae', float('inf'))

        # Critical: Calibrated must beat raw model by at least 2%
        if cal_mae >= model_mae * 0.98:
            ci_checks["performance_regression"]["status"] = "FAIL"
            ci_checks["performance_regression"]["message"] = f"Calibrated MAE ({cal_mae:.3f}) not significantly better than model ({model_mae:.3f})"

        # Warning: Should ideally beat consensus
        improvement_vs_consensus = ((cons_mae - cal_mae) / cons_mae * 100) if cons_mae > 0 else -100
        if improvement_vs_consensus < -5.0:  # Worse than 5% degradation vs consensus
            if ci_checks["performance_regression"]["status"] == "PASS":
                ci_checks["performance_regression"]["status"] = "WARN"
            ci_checks["performance_regression"]["message"] += f" Consensus degradation: {improvement_vs_consensus:.1f}%"

        # 2. Statistical Significance Check
        stat_tests = self.test_vs_consensus()
        dm_p = stat_tests.get("diebold_mariano", {}).get("p_value", 1.0)

        if dm_p > 0.10:  # Not even weakly significant
            ci_checks["statistical_significance"]["status"] = "FAIL"
            ci_checks["statistical_significance"]["message"] = f"DM test p-value {dm_p:.3f} > 0.10 (not significant)"
        elif dm_p > 0.05:
            ci_checks["statistical_significance"]["status"] = "WARN"
            ci_checks["statistical_significance"]["message"] = f"DM test p-value {dm_p:.3f} only weakly significant"

        # 3. Alpha Stability Check
        alpha_stats = self.calculate_alpha_stability()
        alpha_std = alpha_stats.get('std', 0)
        pct_at_bounds = alpha_stats.get('pct_at_bounds', 0)

        if alpha_std > 0.35:
            ci_checks["alpha_stability"]["status"] = "FAIL"
            ci_checks["alpha_stability"]["message"] = f"Alpha std {alpha_std:.3f} too high (>0.35)"
        elif pct_at_bounds > 60:
            ci_checks["alpha_stability"]["status"] = "WARN"
            ci_checks["alpha_stability"]["message"] = f"{pct_at_bounds:.1f}% of alphas at bounds"

        # 4. Country Coverage Check
        country_metrics = self.calculate_country_metrics()
        countries_beating_consensus = sum(1 for country, data in country_metrics.items()
                                        if data.get('calibrated', {}).get('mae', float('inf')) <
                                        data.get('consensus', {}).get('mae', float('inf')))

        total_countries = len(country_metrics)
        if total_countries > 0:
            success_rate = countries_beating_consensus / total_countries
            if success_rate < 0.25:  # Less than 25% of countries improved (critical regression)
                ci_checks["country_coverage"]["status"] = "FAIL"
                ci_checks["country_coverage"]["message"] = f"Only {countries_beating_consensus}/{total_countries} countries improved"
            elif success_rate < 0.35:  # Less than 35% of countries improved (warning)
                ci_checks["country_coverage"]["status"] = "WARN"
                ci_checks["country_coverage"]["message"] = f"Only {countries_beating_consensus}/{total_countries} countries improved"

        # 5. Guardrail Overuse Check
        guardrail_usage = sum(1 for r in self.results if r.get('guardrail_actions', [])) / len(self.results) * 100
        if guardrail_usage > 30:  # More than 30% of forecasts needed guardrails
            ci_checks["guardrail_overuse"]["status"] = "WARN"
            ci_checks["guardrail_overuse"]["message"] = f"Guardrails used in {guardrail_usage:.1f}% of forecasts"

        # 6. Extreme Outliers Check
        calibrated_forecasts = [r['y_cal'] for r in self.results if r.get('y_cal') is not None]
        if calibrated_forecasts:
            extreme_forecasts = sum(1 for y in calibrated_forecasts if abs(y) > 10) / len(calibrated_forecasts) * 100
            if extreme_forecasts > 5:  # More than 5% extreme forecasts
                ci_checks["extreme_outliers"]["status"] = "FAIL"
                ci_checks["extreme_outliers"]["message"] = f"{extreme_forecasts:.1f}% of forecasts are extreme (|y|>10%)"

        # Overall CI status
        critical_failures = sum(1 for check in ci_checks.values() if check["status"] == "FAIL" and check["critical"])
        warnings = sum(1 for check in ci_checks.values() if check["status"] == "WARN")

        overall_status = "FAIL" if critical_failures > 0 else ("WARN" if warnings > 0 else "PASS")

        return {
            "overall_status": overall_status,
            "critical_failures": critical_failures,
            "warnings": warnings,
            "checks": ci_checks,
            "summary": f"{critical_failures} critical failures, {warnings} warnings"
        }

    def generate_report(self, save_path: Optional[Path] = None) -> Dict:
        """
        Generate comprehensive validation report with CI checks
        """
        # CI validation checks
        ci_validation = self.check_ci_conditions()

        report = {
            'timestamp': datetime.now().isoformat(),
            'n_observations': len(self.results),
            'overall_metrics': self.calculate_metrics(),
            'country_metrics': self.calculate_country_metrics(),
            'statistical_tests': self.test_vs_consensus(),
            'alpha_stability': self.calculate_alpha_stability(),
            'success_criteria': self._check_success_criteria(),
            'ci_validation': ci_validation
        }

        if save_path:
            with open(save_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)

        return report

    def _check_success_criteria(self) -> Dict:
        """
        Check if success criteria are met
        """
        metrics = self.performance_metrics
        country_metrics = self.calculate_country_metrics()

        criteria = {
            'lower_mae_than_consensus': False,
            'mae_improvement_pct': 0,
            'countries_beating_consensus': 0,
            'statistical_significance': False,
            'alpha_stability': False
        }

        if 'calibrated' in metrics and 'consensus' in metrics:
            # Overall MAE comparison
            criteria['lower_mae_than_consensus'] = (
                metrics['calibrated']['mae'] < metrics['consensus']['mae']
            )

            # MAE improvement percentage
            if metrics['consensus']['mae'] > 0:
                criteria['mae_improvement_pct'] = (
                    (metrics['consensus']['mae'] - metrics['calibrated']['mae']) /
                    metrics['consensus']['mae'] * 100
                )

            # Countries where calibrated beats consensus
            countries_better = 0
            for country, c_metrics in country_metrics.items():
                if ('calibrated' in c_metrics and 'consensus' in c_metrics and
                    c_metrics['calibrated']['mae'] < c_metrics['consensus']['mae']):
                    countries_better += 1
            criteria['countries_beating_consensus'] = countries_better

        # Statistical significance
        test_results = self.test_vs_consensus()
        if 'diebold_mariano' in test_results:
            criteria['statistical_significance'] = test_results['diebold_mariano']['significant']

        # Alpha stability
        alpha_stats = self.calculate_alpha_stability()
        if alpha_stats:
            criteria['alpha_stability'] = alpha_stats.get('pct_at_bounds', 100) < 30

        # Overall success
        criteria['overall_success'] = (
            criteria['lower_mae_than_consensus'] and
            criteria['mae_improvement_pct'] > 10 and
            criteria['countries_beating_consensus'] >= len(country_metrics) * 0.6 and
            criteria['alpha_stability']
        )

        return criteria


def demo_walk_forward():
    """Demonstrate walk-forward validation"""
    print("=" * 80)
    print("WALK-FORWARD VALIDATION DEMONSTRATION")
    print("=" * 80)

    # Generate synthetic historical data
    countries = ['USA', 'DEU', 'JPN', 'GBR', 'FRA', 'KOR']
    history = generate_synthetic_history(countries, n_years=7)

    # Add some realized GDP data
    print(f"\nGenerated {len(history)} historical data points")

    # Initialize validator
    validator = WalkForwardValidator(min_history=10)

    # Run walk-forward validation
    print("\n1. Running Walk-Forward Validation")
    print("-" * 40)
    results = validator.walk_forward(history, expanding_window=True)

    # Calculate metrics
    print("\n2. Performance Metrics")
    print("-" * 40)
    metrics = validator.calculate_metrics()

    for method in ['model', 'consensus', 'calibrated']:
        if method in metrics:
            m = metrics[method]
            print(f"\n{method.upper()}:")
            print(f"  MAE:  {m['mae']:.3f}")
            print(f"  RMSE: {m['rmse']:.3f}")
            print(f"  Bias: {m['bias']:+.3f}")
            print(f"  N:    {m['n']}")

    # Improvement analysis
    if 'improvement_vs_consensus' in metrics:
        print(f"\nImprovement vs Consensus: {metrics['improvement_vs_consensus']:.1f}%")
    if 'improvement_vs_model' in metrics:
        print(f"Improvement vs Raw Model: {metrics['improvement_vs_model']:.1f}%")

    # Country-specific metrics
    print("\n3. Country-Specific Performance")
    print("-" * 40)
    country_metrics = validator.calculate_country_metrics()

    for country in sorted(country_metrics.keys()):
        c_metrics = country_metrics[country]
        if 'calibrated' in c_metrics and c_metrics['calibrated']['n'] > 0:
            print(f"\n{country}:")
            print(f"  Model MAE:      {c_metrics.get('model', {}).get('mae', np.nan):.3f}")
            print(f"  Consensus MAE:  {c_metrics.get('consensus', {}).get('mae', np.nan):.3f}")
            print(f"  Calibrated MAE: {c_metrics['calibrated']['mae']:.3f}")

    # Statistical tests
    print("\n4. Statistical Tests")
    print("-" * 40)
    test_results = validator.test_vs_consensus()

    if 'diebold_mariano' in test_results:
        dm = test_results['diebold_mariano']
        print(f"Diebold-Mariano Test:")
        print(f"  Statistic: {dm['statistic']:.3f}")
        print(f"  P-value:   {dm['p_value']:.3f}")
        print(f"  Result:    {dm['interpretation']}")

    # Alpha stability
    print("\n5. Alpha Stability Analysis")
    print("-" * 40)
    alpha_stats = validator.calculate_alpha_stability()

    if alpha_stats:
        print(f"Mean Alpha:    {alpha_stats['mean']:.3f}")
        print(f"Std Alpha:     {alpha_stats['std']:.3f}")
        print(f"Range:         [{alpha_stats['min']:.2f}, {alpha_stats['max']:.2f}]")
        print(f"At Bounds:     {alpha_stats['pct_at_bounds']:.1f}%")

    # Success criteria
    print("\n6. Success Criteria Check")
    print("-" * 40)
    criteria = validator._check_success_criteria()

    for criterion, value in criteria.items():
        if criterion != 'overall_success':
            status = "✅" if ((isinstance(value, bool) and value) or
                            (isinstance(value, (int, float)) and value > 0)) else "❌"
            print(f"{status} {criterion}: {value}")

    print(f"\n{'✅' if criteria['overall_success'] else '❌'} OVERALL SUCCESS: "
          f"{'PASSED' if criteria['overall_success'] else 'NEEDS IMPROVEMENT'}")

    # Generate report
    print("\n7. Saving Report")
    print("-" * 40)
    report_path = Path("data/walk_forward_report.json")
    report = validator.generate_report(report_path)
    print(f"Report saved to {report_path}")

    print("\n✅ Walk-forward validation complete!")


if __name__ == "__main__":
    demo_walk_forward()