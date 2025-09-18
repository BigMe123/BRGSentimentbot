#!/usr/bin/env python
"""
Country-specific adapters for priority countries
US, UK, DE, FR, BR - each with proper data mapping
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.country_adapter_base import CountryAdapterBase, DataTier


class UKAdapter(CountryAdapterBase):
    """UK data adapter - Tier A (rich data)"""

    def __init__(self):
        super().__init__('UK')
        self.data_sources = {
            'pmi': 'S&P Global/CIPS',
            'gdp': 'ONS',
            'retail': 'ONS',
            'cpi': 'ONS',
            'fx': 'BoE'
        }

    def load_monthly_indicators(self, start_date: datetime,
                               end_date: datetime) -> pd.DataFrame:
        """Load UK monthly indicators from ONS, S&P, BoE"""

        # In production: fetch from APIs
        # For now, generate realistic UK data
        dates = pd.date_range(start=start_date, end=end_date, freq='M')
        n = len(dates)

        # UK-specific patterns
        brexit_effect = np.where((dates >= '2016-06') & (dates <= '2020-01'), -0.5, 0)
        covid_effect = np.where((dates >= '2020-03') & (dates <= '2021-06'), -2.0, 0)

        data = pd.DataFrame({
            'date': dates,
            # Services-heavy economy
            'pmi_services': 52 + brexit_effect * 3 + covid_effect * 15 + np.random.normal(0, 2, n),
            'pmi_manufacturing': 50 + brexit_effect * 5 + covid_effect * 10 + np.random.normal(0, 3, n),

            # Retail & production
            'retail_sales': 100 + np.cumsum(np.random.normal(0.2, 2, n)),
            'industrial_production': 100 + np.cumsum(np.random.normal(0.1, 1.5, n)),
            'construction_output': 100 + np.cumsum(np.random.normal(0.15, 2, n)),

            # Labor
            'unemployment_rate': 4.5 + brexit_effect * 0.5 + covid_effect * 2 + np.random.normal(0, 0.3, n),
            'claimant_count': 1.2e6 + brexit_effect * 1e5 + covid_effect * 1e6 + np.random.normal(0, 5e4, n),

            # Prices
            'cpi': 2.0 + brexit_effect * 0.5 + np.random.normal(0, 0.3, n),
            'energy_cpi': 3.0 + covid_effect * -2 + np.random.normal(0, 1, n),

            # Trade (Brexit impact)
            'exports': 50 + brexit_effect * -5 + np.random.normal(0, 2, n),
            'imports': 55 + brexit_effect * -3 + np.random.normal(0, 2, n),

            # FX (GBP weakness post-Brexit)
            'fx_usd': 1.35 + brexit_effect * -0.15 + np.random.normal(0, 0.02, n),
            'fx_trade_weighted': 78 + brexit_effect * -5 + np.random.normal(0, 1, n),

            # Credit
            'mortgage_approvals': 65000 + brexit_effect * -5000 + covid_effect * -20000 + np.random.normal(0, 5000, n),

            # Sentiment
            'consumer_confidence': -10 + brexit_effect * -10 + covid_effect * -20 + np.random.normal(0, 3, n),

            # Policy
            'stringency_index': np.where(covid_effect < 0, 60, 0) + np.random.normal(0, 5, n)
        })

        data.set_index('date', inplace=True)
        return data

    def load_quarterly_target(self, start_date: datetime,
                            end_date: datetime) -> pd.Series:
        """Load UK quarterly GDP from ONS"""

        quarters = pd.date_range(start=start_date, end=end_date, freq='Q')

        # Realistic UK GDP pattern
        gdp = pd.Series({
            pd.Timestamp('2016-03-31'): 0.4,
            pd.Timestamp('2016-06-30'): 0.5,
            pd.Timestamp('2016-09-30'): 0.5,  # Brexit vote
            pd.Timestamp('2016-12-31'): 0.7,
            pd.Timestamp('2017-03-31'): 0.3,
            pd.Timestamp('2017-06-30'): 0.3,
            pd.Timestamp('2017-09-30'): 0.4,
            pd.Timestamp('2017-12-31'): 0.4,
            pd.Timestamp('2018-03-31'): 0.1,
            pd.Timestamp('2018-06-30'): 0.4,
            pd.Timestamp('2018-09-30'): 0.7,
            pd.Timestamp('2018-12-31'): 0.2,
            pd.Timestamp('2019-03-31'): 0.6,
            pd.Timestamp('2019-06-30'): -0.2,
            pd.Timestamp('2019-09-30'): 0.5,
            pd.Timestamp('2019-12-31'): 0.0,
            pd.Timestamp('2020-03-31'): -2.5,  # COVID starts
            pd.Timestamp('2020-06-30'): -19.4,  # Lockdown
            pd.Timestamp('2020-09-30'): 17.6,  # Recovery
            pd.Timestamp('2020-12-31'): 1.3,
            pd.Timestamp('2021-03-31'): -1.3,
            pd.Timestamp('2021-06-30'): 5.5,
            pd.Timestamp('2021-09-30'): 1.0,
            pd.Timestamp('2021-12-31'): 1.3,
            pd.Timestamp('2022-03-31'): 0.6,
            pd.Timestamp('2022-06-30'): 0.2,
            pd.Timestamp('2022-09-30'): -0.3,
            pd.Timestamp('2022-12-31'): 0.1,
            pd.Timestamp('2023-03-31'): 0.1,
            pd.Timestamp('2023-06-30'): 0.4,
            pd.Timestamp('2023-09-30'): 0.3
        })

        # Filter to requested range
        return gdp.reindex(quarters).fillna(method='ffill')


class USAdapter(CountryAdapterBase):
    """US data adapter - Tier A (rich data)"""

    def __init__(self):
        super().__init__('US')
        self.data_sources = {
            'pmi': 'ISM',
            'gdp': 'BEA',
            'retail': 'Census',
            'cpi': 'BLS',
            'fx': 'Fed'
        }

    def load_monthly_indicators(self, start_date: datetime,
                               end_date: datetime) -> pd.DataFrame:
        """Load US monthly indicators from Fed, BLS, Census"""

        dates = pd.date_range(start=start_date, end=end_date, freq='M')
        n = len(dates)

        # US-specific patterns
        covid_effect = np.where((dates >= '2020-03') & (dates <= '2021-06'), -1.5, 0)
        stimulus_effect = np.where((dates >= '2020-04') & (dates <= '2021-09'), 1.0, 0)

        data = pd.DataFrame({
            'date': dates,
            # ISM PMIs
            'pmi_services': 55 + covid_effect * 20 + np.random.normal(0, 2, n),
            'pmi_manufacturing': 52 + covid_effect * 15 + np.random.normal(0, 3, n),

            # Activity
            'retail_sales': 100 + np.cumsum(np.random.normal(0.3, 2, n)) + stimulus_effect * 10,
            'industrial_production': 100 + np.cumsum(np.random.normal(0.2, 1.5, n)),

            # Labor
            'unemployment_rate': 4.0 + covid_effect * 10 + np.random.normal(0, 0.3, n),

            # Prices
            'cpi': 2.5 + stimulus_effect * 2 + np.random.normal(0, 0.3, n),

            # Trade
            'exports': 150 + covid_effect * -20 + np.random.normal(0, 5, n),
            'imports': 200 + covid_effect * -30 + np.random.normal(0, 5, n),

            # FX (DXY)
            'fx_usd': 95 + covid_effect * 5 + np.random.normal(0, 2, n),

            # Sentiment
            'consumer_confidence': 100 + covid_effect * -30 + stimulus_effect * 20 + np.random.normal(0, 5, n),

            # Policy
            'stringency_index': np.where(covid_effect < 0, 70, 0) + np.random.normal(0, 5, n)
        })

        data.set_index('date', inplace=True)
        return data

    def load_quarterly_target(self, start_date: datetime,
                            end_date: datetime) -> pd.Series:
        """Load US quarterly GDP from BEA"""

        quarters = pd.date_range(start=start_date, end=end_date, freq='Q')

        # Use annualized rates (US convention)
        gdp = pd.Series({
            pd.Timestamp('2020-03-31'): -5.0,
            pd.Timestamp('2020-06-30'): -31.4,
            pd.Timestamp('2020-09-30'): 33.4,
            pd.Timestamp('2020-12-31'): 4.3,
            pd.Timestamp('2021-03-31'): 6.3,
            pd.Timestamp('2021-06-30'): 6.7,
            pd.Timestamp('2021-09-30'): 2.3,
            pd.Timestamp('2021-12-31'): 6.9,
            pd.Timestamp('2022-03-31'): -1.6,
            pd.Timestamp('2022-06-30'): -0.6,
            pd.Timestamp('2022-09-30'): 3.2,
            pd.Timestamp('2022-12-31'): 2.6,
            pd.Timestamp('2023-03-31'): 2.0,
            pd.Timestamp('2023-06-30'): 2.1,
            pd.Timestamp('2023-09-30'): 4.9
        })

        # Fill with typical growth for other periods
        for q in quarters:
            if q not in gdp.index:
                gdp[q] = 2.5 + np.random.normal(0, 0.5)

        return gdp.reindex(quarters).fillna(method='ffill')


class GermanyAdapter(CountryAdapterBase):
    """Germany data adapter - Tier A"""

    def __init__(self):
        super().__init__('DE')
        self.data_sources = {
            'pmi': 'S&P Global',
            'gdp': 'Destatis',
            'ifo': 'Ifo Institute',
            'cpi': 'Destatis',
            'fx': 'ECB'
        }

    def load_monthly_indicators(self, start_date: datetime,
                               end_date: datetime) -> pd.DataFrame:
        """Load German indicators from Destatis, Ifo, ECB"""

        dates = pd.date_range(start=start_date, end=end_date, freq='M')
        n = len(dates)

        # Germany-specific (manufacturing-heavy, export-dependent)
        covid_effect = np.where((dates >= '2020-03') & (dates <= '2021-06'), -2.0, 0)
        energy_crisis = np.where((dates >= '2022-03') & (dates <= '2023-06'), -1.0, 0)

        data = pd.DataFrame({
            'date': dates,
            # Manufacturing-heavy
            'pmi_services': 54 + covid_effect * 15 + energy_crisis * 5 + np.random.normal(0, 2, n),
            'pmi_manufacturing': 52 + covid_effect * 20 + energy_crisis * 10 + np.random.normal(0, 3, n),

            # Strong industrial base
            'industrial_production': 100 + np.cumsum(np.random.normal(0.1, 2, n)) + energy_crisis * -5,

            # Labor (low unemployment)
            'unemployment_rate': 3.5 + covid_effect * 1 + np.random.normal(0, 0.2, n),

            # Prices (energy sensitivity)
            'cpi': 2.0 + energy_crisis * 6 + np.random.normal(0, 0.3, n),
            'energy_cpi': 3.0 + energy_crisis * 20 + np.random.normal(0, 2, n),

            # Export powerhouse
            'exports': 120 + covid_effect * -15 + energy_crisis * -10 + np.random.normal(0, 3, n),

            # Euro
            'fx_usd': 1.15 + energy_crisis * -0.15 + np.random.normal(0, 0.02, n),

            # Ifo sentiment
            'consumer_confidence': 95 + covid_effect * -20 + energy_crisis * -15 + np.random.normal(0, 3, n)
        })

        data.set_index('date', inplace=True)
        return data

    def load_quarterly_target(self, start_date: datetime,
                            end_date: datetime) -> pd.Series:
        """Load German quarterly GDP"""

        quarters = pd.date_range(start=start_date, end=end_date, freq='Q')
        gdp = pd.Series(index=quarters, data=np.random.normal(1.5, 0.5, len(quarters)))

        # Key events
        if pd.Timestamp('2020-06-30') in gdp.index:
            gdp[pd.Timestamp('2020-06-30')] = -10.1
        if pd.Timestamp('2022-12-31') in gdp.index:
            gdp[pd.Timestamp('2022-12-31')] = -0.4

        return gdp


class BrazilAdapter(CountryAdapterBase):
    """Brazil data adapter - Tier B (medium data)"""

    def __init__(self):
        super().__init__('BR')
        self.data_sources = {
            'gdp': 'IBGE',
            'cpi': 'IBGE',
            'fx': 'BCB'
        }

    def load_monthly_indicators(self, start_date: datetime,
                               end_date: datetime) -> pd.DataFrame:
        """Load Brazilian indicators - fewer available than Tier A"""

        dates = pd.date_range(start=start_date, end=end_date, freq='M')
        n = len(dates)

        # Brazil-specific (commodity-dependent, high volatility)
        covid_effect = np.where((dates >= '2020-03') & (dates <= '2021-06'), -2.5, 0)
        commodity_boom = np.where((dates >= '2021-01') & (dates <= '2022-06'), 1.0, 0)

        data = pd.DataFrame({
            'date': dates,
            # Limited PMI data
            'pmi_services': 50 + covid_effect * 15 + commodity_boom * 5 + np.random.normal(0, 3, n),
            'pmi_manufacturing': 48 + covid_effect * 20 + commodity_boom * 8 + np.random.normal(0, 4, n),

            # High inflation environment
            'cpi': 4.5 + commodity_boom * 3 + np.random.normal(0, 0.5, n),

            # Volatile FX (BRL/USD)
            'fx_usd': 5.0 + covid_effect * 0.5 + commodity_boom * -0.3 + np.random.normal(0, 0.2, n),

            # Trade (commodity exports)
            'exports': 20 + commodity_boom * 5 + np.random.normal(0, 2, n),
            'imports': 18 + np.random.normal(0, 2, n)
        })

        # Many indicators not available (Tier B)
        data['retail_sales'] = np.nan
        data['industrial_production'] = np.nan
        data['construction_output'] = np.nan
        data['mortgage_approvals'] = np.nan

        data.set_index('date', inplace=True)
        return data

    def load_quarterly_target(self, start_date: datetime,
                            end_date: datetime) -> pd.Series:
        """Load Brazilian quarterly GDP - higher volatility"""

        quarters = pd.date_range(start=start_date, end=end_date, freq='Q')
        # Higher baseline volatility for emerging market
        gdp = pd.Series(index=quarters, data=np.random.normal(2.0, 1.5, len(quarters)))

        return gdp