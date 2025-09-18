#!/usr/bin/env python
"""
Base Country Adapter Interface
Core abstraction for country-specific data mapping
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime
from enum import Enum


class DataTier(Enum):
    """Data availability tiers"""
    TIER_A = "rich"      # Full indicators: PMIs, retail, IP, construction, etc.
    TIER_B = "medium"    # PMIs + CPI + trade + FX + one of retail/IP
    TIER_C = "lean"      # CPI + FX + trade headlines + sentiment


class CountryAdapterBase(ABC):
    """
    Base interface for country adapters
    Maps country-specific data to common schema
    """

    def __init__(self, country_code: str):
        self.country_code = country_code
        self.tier = None
        self.data_sources = {}
        self.revision_history = []
        self.rolling_window = 60  # months for z-score normalization

        # Common schema fields
        self.indicator_schema = {
            # PMIs
            'pmi_services': {'required': ['A', 'B'], 'aggregation': 'mean'},
            'pmi_manufacturing': {'required': ['A', 'B'], 'aggregation': 'mean'},

            # Activity
            'retail_sales': {'required': ['A'], 'aggregation': 'sum'},
            'industrial_production': {'required': ['A'], 'aggregation': 'mean'},
            'construction_output': {'required': ['A'], 'aggregation': 'sum'},

            # Labor
            'unemployment_rate': {'required': ['A', 'B'], 'aggregation': 'latest'},
            'claimant_count': {'required': ['A'], 'aggregation': 'latest'},

            # Prices
            'cpi': {'required': ['A', 'B', 'C'], 'aggregation': 'latest'},
            'energy_cpi': {'required': ['A', 'B'], 'aggregation': 'latest'},

            # Trade
            'exports': {'required': ['A', 'B'], 'aggregation': 'sum'},
            'imports': {'required': ['A', 'B'], 'aggregation': 'sum'},

            # Financial
            'fx_usd': {'required': ['A', 'B', 'C'], 'aggregation': 'latest'},
            'fx_trade_weighted': {'required': ['A', 'B'], 'aggregation': 'latest'},
            'credit_approvals': {'required': ['A'], 'aggregation': 'sum'},
            'mortgage_approvals': {'required': ['A'], 'aggregation': 'sum'},

            # Sentiment
            'consumer_confidence': {'required': ['A'], 'aggregation': 'mean'},

            # Policy
            'stringency_index': {'required': ['A', 'B', 'C'], 'aggregation': 'max'},
            'mobility_index': {'required': ['A', 'B'], 'aggregation': 'mean'}
        }

    @abstractmethod
    def load_monthly_indicators(self, start_date: datetime,
                               end_date: datetime) -> pd.DataFrame:
        """
        Load monthly indicators available for this country

        Returns:
            DataFrame with columns matching indicator_schema keys
            Missing indicators should be NaN
        """
        pass

    @abstractmethod
    def load_quarterly_target(self, start_date: datetime,
                            end_date: datetime) -> pd.Series:
        """
        Load quarterly GDP data (YoY and/or QoQ)

        Returns:
            Series with quarterly GDP growth rates
        """
        pass

    def calendar(self) -> pd.DataFrame:
        """
        Optional: Load holiday/calendar adjustments

        Returns:
            DataFrame with holiday flags and adjustments
        """
        return pd.DataFrame()  # Default: no adjustments

    def detect_tier(self) -> DataTier:
        """
        Auto-detect data tier based on available indicators
        """
        # Load sample data to check availability
        test_date = datetime.now()
        sample = self.load_monthly_indicators(
            test_date - pd.DateOffset(months=3),
            test_date
        )

        available = sample.columns[sample.notna().any()].tolist()

        # Check tier requirements
        tier_a_required = {'pmi_services', 'pmi_manufacturing', 'retail_sales',
                          'industrial_production', 'unemployment_rate', 'cpi'}
        tier_b_required = {'pmi_services', 'pmi_manufacturing', 'cpi', 'fx_usd'}
        tier_c_required = {'cpi', 'fx_usd'}

        if tier_a_required.issubset(available):
            self.tier = DataTier.TIER_A
        elif tier_b_required.issubset(available):
            self.tier = DataTier.TIER_B
        else:
            self.tier = DataTier.TIER_C

        return self.tier

    def normalize_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Per-country rolling z-score normalization
        Removes US-centric scale bias
        """
        normalized = data.copy()

        for col in data.columns:
            if col in ['date', 'quarter']:
                continue

            # Rolling z-score
            rolling = data[col].rolling(window=self.rolling_window, min_periods=12)
            mean = rolling.mean()
            std = rolling.std()

            # Avoid division by zero
            std = std.replace(0, 1)

            normalized[col] = (data[col] - mean) / std

        return normalized

    def bridge_to_quarterly(self, monthly_data: pd.DataFrame) -> pd.DataFrame:
        """
        Bridge monthly indicators to quarterly frequency
        Uses appropriate aggregation for each indicator
        """
        # Group by quarter
        monthly_data['quarter'] = pd.PeriodIndex(monthly_data.index, freq='Q')

        quarterly = pd.DataFrame()

        for indicator, config in self.indicator_schema.items():
            if indicator not in monthly_data.columns:
                continue

            agg_method = config['aggregation']

            if agg_method == 'mean':
                quarterly[indicator] = monthly_data.groupby('quarter')[indicator].mean()
            elif agg_method == 'sum':
                quarterly[indicator] = monthly_data.groupby('quarter')[indicator].sum()
            elif agg_method == 'latest':
                quarterly[indicator] = monthly_data.groupby('quarter')[indicator].last()
            elif agg_method == 'max':
                quarterly[indicator] = monthly_data.groupby('quarter')[indicator].max()

        return quarterly

    def handle_revisions(self, new_data: pd.DataFrame,
                        release_date: datetime) -> pd.DataFrame:
        """
        Handle data revisions and maintain history
        """
        # Store revision
        self.revision_history.append({
            'release_date': release_date,
            'data_snapshot': new_data.copy()
        })

        # Keep both raw and revised views
        if len(self.revision_history) > 1:
            previous = self.revision_history[-2]['data_snapshot']
            revisions = new_data - previous

            # Flag significant revisions
            significant_revisions = (abs(revisions) > 0.5).any(axis=1)
            new_data['revised'] = significant_revisions

        return new_data

    def get_data_quality_metrics(self) -> Dict:
        """
        Assess data quality and coverage
        """
        # Load recent data
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(months=24)
        data = self.load_monthly_indicators(start_date, end_date)

        metrics = {
            'tier': self.tier.value if self.tier else 'unknown',
            'coverage': {},
            'timeliness': {},
            'revisions': len(self.revision_history)
        }

        # Coverage metrics
        for col in data.columns:
            if col in ['date', 'quarter']:
                continue
            coverage = data[col].notna().mean()
            metrics['coverage'][col] = round(coverage, 3)

            # Timeliness (how recent is last non-null)
            last_valid = data[col].last_valid_index()
            if last_valid:
                days_lag = (datetime.now() - last_valid).days
                metrics['timeliness'][col] = days_lag

        return metrics

    def yoy_to_qoq(self, yoy_series: pd.Series) -> pd.Series:
        """
        Convert YoY growth to QoQ seasonally adjusted
        """
        # Simple approximation: QoQ ≈ YoY/4 with seasonal adjustment
        qoq = yoy_series / 4

        # Apply basic seasonal adjustment
        if len(qoq) >= 8:
            from statsmodels.tsa.seasonal import STL
            stl = STL(qoq, seasonal=5)
            result = stl.fit()
            qoq = result.trend + result.resid

        return qoq

    def handle_ragged_edge(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing recent data points
        Uses last observation carried forward with decay
        """
        filled = data.copy()

        for col in data.columns:
            if col in ['date', 'quarter']:
                continue

            # Find last valid index
            last_valid_idx = data[col].last_valid_index()

            if last_valid_idx and last_valid_idx < len(data) - 1:
                # Carry forward with decay
                last_value = data.loc[last_valid_idx, col]
                decay_factor = 0.95  # 5% decay per period

                for i in range(last_valid_idx + 1, len(data)):
                    filled.loc[i, col] = last_value * (decay_factor ** (i - last_valid_idx))
                    filled.loc[i, f'{col}_imputed'] = True

        return filled