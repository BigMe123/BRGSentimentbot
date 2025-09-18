#!/usr/bin/env python3
"""
CI Validation Script for GDP Calibration System
Runs walk-forward validation and checks for regressions
Exit code 0 = PASS, 1 = WARN, 2 = FAIL
"""

import sys
import csv
from pathlib import Path
from sentiment_bot.consensus.dynamic_alpha import AlphaDataPoint
from sentiment_bot.consensus.backtest import WalkForwardValidator


def load_test_data(path: str) -> list:
    """Load test data for validation"""
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(AlphaDataPoint(
                r['country'], int(r['vintage_year']), int(r['target_year']),
                float(r['y_model']), float(r['y_cons']), float(r['y_actual']),
                {
                    'model_conf': float(r['model_conf']),
                    'consensus_disp': float(r['consensus_disp']),
                    'pmi_var_6m': float(r['pmi_var_6m']),
                    'fx_vol_3m': float(r['fx_vol_3m']),
                }
            ))
    rows.sort(key=lambda x: (x.country, x.vintage_year))
    return rows


def print_ci_results(ci_validation: dict):
    """Print CI results in a readable format"""
    overall_status = ci_validation["overall_status"]

    # Status emoji mapping
    status_emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}

    print(f"\n🔍 CI VALIDATION RESULTS")
    print("=" * 50)
    print(f"Overall Status: {status_emoji[overall_status]} {overall_status}")
    print(f"Summary: {ci_validation['summary']}")

    print(f"\n📋 Detailed Checks:")
    for check_name, check_data in ci_validation["checks"].items():
        status = check_data["status"]
        critical = check_data["critical"]
        message = check_data["message"]

        criticality = "🚨 CRITICAL" if critical else "💡 INFO"

        print(f"  {status_emoji[status]} {check_name}: {status}")
        if message:
            print(f"    {criticality}: {message}")

    return overall_status


def main():
    """Main CI validation function"""
    print("🚀 Starting CI Validation for GDP Calibration System")

    # Load test data
    data_path = "data/backtest_samples.csv"
    if not Path(data_path).exists():
        print(f"❌ ERROR: Test data file {data_path} not found")
        sys.exit(2)

    try:
        test_points = load_test_data(data_path)
        print(f"📊 Loaded {len(test_points)} test observations")

        # Run walk-forward validation
        print("🔄 Running walk-forward validation...")
        validator = WalkForwardValidator(min_history=5)
        results = validator.walk_forward(test_points)

        print(f"✅ Processed {len(results)} forecasts")

        # Calculate metrics and run CI checks
        print("📈 Calculating performance metrics...")
        metrics = validator.calculate_metrics()

        # Print performance summary
        print(f"\n📊 PERFORMANCE SUMMARY")
        print("-" * 30)
        for method, m in metrics.items():
            if isinstance(m, dict) and 'mae' in m:
                print(f"{method:>12}: MAE={m['mae']:.3f}, RMSE={m['rmse']:.3f}")

        # Key performance indicators
        cal_mae = metrics['calibrated']['mae']
        cons_mae = metrics['consensus']['mae']
        model_mae = metrics['model']['mae']

        improvement_vs_model = ((model_mae - cal_mae) / model_mae * 100)
        improvement_vs_consensus = ((cons_mae - cal_mae) / cons_mae * 100)

        print(f"\n🎯 KEY METRICS:")
        print(f"   Model improvement:     {improvement_vs_model:+.1f}%")
        print(f"   Consensus improvement: {improvement_vs_consensus:+.1f}%")

        # Run CI validation checks
        print(f"\n🔍 Running CI validation checks...")
        ci_validation = validator.check_ci_conditions()

        # Print results
        overall_status = print_ci_results(ci_validation)

        # Generate full report
        report_path = "data/ci_validation_report.json"
        report = validator.generate_report(Path(report_path))
        print(f"\n📄 Full report saved to: {report_path}")

        # Exit with appropriate code
        if overall_status == "PASS":
            print(f"\n🎉 CI VALIDATION PASSED - All checks successful!")
            sys.exit(0)
        elif overall_status == "WARN":
            print(f"\n⚠️  CI VALIDATION WARNING - Some issues detected but not critical")
            sys.exit(1)
        else:  # FAIL
            print(f"\n💥 CI VALIDATION FAILED - Critical issues detected!")
            print("🚨 This build should NOT be deployed to production")
            sys.exit(2)

    except Exception as e:
        print(f"❌ ERROR during CI validation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()