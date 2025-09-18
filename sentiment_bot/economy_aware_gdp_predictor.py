#!/usr/bin/env python3
"""
Economy-Aware GDP Predictor
===========================
Tailored GDP prediction models based on economy type and characteristics.
Different economies require different prediction approaches.
"""

import os
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
import pandas as pd
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class EconomyType(Enum):
    """Classification of economy types"""
    DEVELOPED = "developed"          # G7, advanced economies
    EMERGING = "emerging"             # BRICS, rapidly growing
    OIL_DEPENDENT = "oil_dependent"   # Saudi Arabia, UAE, Norway
    EXPORT_DRIVEN = "export_driven"   # Germany, South Korea, Netherlands
    SERVICE_BASED = "service_based"   # UK, Switzerland, Singapore
    MANUFACTURING = "manufacturing"    # China, Vietnam, Bangladesh
    COMMODITY = "commodity"           # Australia, Canada, Chile
    FRONTIER = "frontier"             # Vietnam, Nigeria, Kenya
    SMALL_OPEN = "small_open"         # Belgium, Ireland, Denmark


@dataclass
class EconomyProfile:
    """Profile of a country's economy"""
    primary_type: EconomyType
    secondary_type: Optional[EconomyType]
    key_indicators: List[str]
    volatility: float  # 0-1 scale
    external_dependency: float  # 0-1 scale
    growth_potential: float  # 0-1 scale


class EconomyAwareGDPPredictor:
    """GDP predictor that adapts to different economy types"""

    # Economy classifications with their characteristics
    ECONOMY_PROFILES = {
        'USA': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.SERVICE_BASED,
            key_indicators=['consumer_spending', 'tech_sector', 'fed_policy'],
            volatility=0.3,
            external_dependency=0.2,
            growth_potential=0.4
        ),
        'CHN': EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=EconomyType.MANUFACTURING,
            key_indicators=['industrial_production', 'exports', 'investment'],
            volatility=0.4,
            external_dependency=0.5,
            growth_potential=0.8
        ),
        'JPN': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.EXPORT_DRIVEN,
            key_indicators=['exports', 'manufacturing', 'demographics'],
            volatility=0.3,
            external_dependency=0.6,
            growth_potential=0.2
        ),
        'DEU': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.EXPORT_DRIVEN,
            key_indicators=['exports', 'manufacturing', 'eu_demand'],
            volatility=0.3,
            external_dependency=0.7,
            growth_potential=0.3
        ),
        'GBR': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.SERVICE_BASED,
            key_indicators=['services', 'finance', 'consumer_confidence'],
            volatility=0.4,
            external_dependency=0.5,
            growth_potential=0.3
        ),
        'IND': EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=EconomyType.SERVICE_BASED,
            key_indicators=['services', 'demographics', 'investment'],
            volatility=0.5,
            external_dependency=0.4,
            growth_potential=0.9
        ),
        'FRA': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.SERVICE_BASED,
            key_indicators=['services', 'tourism', 'consumer_spending'],
            volatility=0.3,
            external_dependency=0.5,
            growth_potential=0.3
        ),
        'BRA': EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=EconomyType.COMMODITY,
            key_indicators=['commodities', 'domestic_demand', 'inflation'],
            volatility=0.6,
            external_dependency=0.5,
            growth_potential=0.6
        ),
        'CAN': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.COMMODITY,
            key_indicators=['oil_prices', 'housing', 'us_demand'],
            volatility=0.4,
            external_dependency=0.7,
            growth_potential=0.4
        ),
        'RUS': EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=EconomyType.OIL_DEPENDENT,
            key_indicators=['oil_prices', 'sanctions', 'military_spending'],
            volatility=0.7,
            external_dependency=0.6,
            growth_potential=0.3
        ),
        'KOR': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.EXPORT_DRIVEN,
            key_indicators=['tech_exports', 'semiconductors', 'china_demand'],
            volatility=0.4,
            external_dependency=0.8,
            growth_potential=0.4
        ),
        'AUS': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.COMMODITY,
            key_indicators=['mining', 'china_demand', 'housing'],
            volatility=0.4,
            external_dependency=0.6,
            growth_potential=0.4
        ),
        'SAU': EconomyProfile(
            primary_type=EconomyType.OIL_DEPENDENT,
            secondary_type=None,
            key_indicators=['oil_prices', 'opec_policy', 'diversification'],
            volatility=0.6,
            external_dependency=0.7,
            growth_potential=0.5
        ),
        'MEX': EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=EconomyType.MANUFACTURING,
            key_indicators=['us_demand', 'manufacturing', 'remittances'],
            volatility=0.5,
            external_dependency=0.8,
            growth_potential=0.5
        ),
        'CHE': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.SERVICE_BASED,
            key_indicators=['finance', 'pharma', 'tourism'],
            volatility=0.2,
            external_dependency=0.6,
            growth_potential=0.3
        ),
        'SGP': EconomyProfile(
            primary_type=EconomyType.DEVELOPED,
            secondary_type=EconomyType.SMALL_OPEN,
            key_indicators=['trade', 'finance', 'tech'],
            volatility=0.4,
            external_dependency=0.9,
            growth_potential=0.4
        ),
        'NGA': EconomyProfile(
            primary_type=EconomyType.FRONTIER,
            secondary_type=EconomyType.OIL_DEPENDENT,
            key_indicators=['oil_prices', 'demographics', 'agriculture'],
            volatility=0.7,
            external_dependency=0.6,
            growth_potential=0.7
        ),
        'VNM': EconomyProfile(
            primary_type=EconomyType.FRONTIER,
            secondary_type=EconomyType.MANUFACTURING,
            key_indicators=['manufacturing', 'fdi', 'exports'],
            volatility=0.5,
            external_dependency=0.7,
            growth_potential=0.8
        ),
    }

    # Corrected FRED series mappings
    CORRECTED_FRED_SERIES = {
        'CHN': {
            'gdp': 'RGDPNACNA666NRUG',  # Real GDP China
            'cpi': 'CHNCPIALLMINMEI',
            'industrial': 'CHNPROINDMISMEI',
            'exports': 'XTEXVA01CNM659S',
            'imports': 'XTIMVA01CNM659S',
            'pmi': 'CHNLORSGPNOSTSAM'  # Leading indicators
        },
        'USA': {
            'gdp': 'GDPC1',
            'cpi': 'CPIAUCSL',
            'unemployment': 'UNRATE',
            'consumer_conf': 'UMCSENT',
            'retail_sales': 'RSXFS',
            'industrial': 'INDPRO',
            'housing': 'HOUST',
            'fed_funds': 'DFF'
        },
        'JPN': {
            'gdp': 'JPNRGDPEXP',
            'cpi': 'JPNCPIALLMINMEI',
            'unemployment': 'JPNURHARMMDSMEI',
            'industrial': 'JPNPROINDMISMEI',
            'exports': 'JPNXTEXVA01CXMLM',
            'tankan': 'JPNASITLSAXQ'  # Business confidence
        },
        'DEU': {
            'gdp': 'CLVMNACSCAB1GQDE',
            'cpi': 'DEUCPIALLMINMEI',
            'unemployment': 'DEUURHARMMDSMEI',
            'industrial': 'DEUPROINDMISMEI',
            'exports': 'DEUXTEXVA01CXMLM',
            'ifo': 'BSCICP03DEM460S'  # Business climate
        },
        'GBR': {
            'gdp': 'UKRGDPQDSNAQ',
            'cpi': 'GBRCPIALLMINMEI',
            'unemployment': 'LRHUTTTTGBM156S',
            'consumer_conf': 'CSCICP03GBM460S',
            'services': 'GBRSERPROINDMISMEI',
            'housing': 'GBRHPI'
        },
        'IND': {
            'gdp': 'RGDPNAINA666NRUG',
            'cpi': 'INDCPIALLMINMEI',
            'industrial': 'INDPROINDMISMEI',
            'pmi': 'INDLORSGPNOSTSAM',
            'exports': 'INDXTEXVA01CXMLM'
        },
        'BRA': {
            'gdp': 'BRALORSGPNOSTSAM',
            'cpi': 'BRACPIALLMINMEI',
            'unemployment': 'LRHUTTTTBRM156S',
            'industrial': 'BRAPROINDMISMEI',
            'commodity_index': 'PALLFNFINDEXQ'
        },
        'RUS': {
            'gdp': 'RGDPNARUS666NRUG',
            'cpi': 'RUSCPIALLMINMEI',
            'oil_production': 'RUSOILPRODM',
            'industrial': 'RUSPROINDMISMEI'
        },
        'SAU': {
            'gdp': 'RGDPNASAA666NRUG',
            'oil_production': 'SAUOILPRODM',
            'oil_price': 'DCOILWTICO',
            'non_oil_gdp': 'SAUNOILGDP'
        },
        'KOR': {
            'gdp': 'KORGDPQDSNAQ',
            'cpi': 'KORCPIALLMINMEI',
            'exports': 'KORXTEXVA01CXMLM',
            'industrial': 'KORPROINDMISMEI',
            'semiconductor': 'KORTECH'
        },
        'CAN': {
            'gdp': 'NAEXKP01CAQ652S',
            'cpi': 'CANCPIALLMINMEI',
            'unemployment': 'LRHUTTTTCAM156S',
            'housing': 'CANHPI',
            'oil_price': 'DCOILWTICO'
        },
        'AUS': {
            'gdp': 'AUSGDPQDSNAQ',
            'cpi': 'AUSCPIALLMINMEI',
            'unemployment': 'LRHUTTTTAUM156S',
            'mining': 'AUSMININGPROD',
            'housing': 'AUSHPI'
        },
    }

    def __init__(self):
        """Initialize economy-aware predictor"""
        self.logger = logging.getLogger(__name__)

        # Initialize data integration
        from sentiment_bot.ml_foundation import ModelConfig, DataIntegration
        self.config = ModelConfig()
        self.config.fred_api_key = os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
        self.data_integration = DataIntegration(self.config)

        logger.info("Economy-aware GDP predictor initialized")

    def get_economy_profile(self, country_code: str) -> EconomyProfile:
        """Get economy profile for a country"""

        if country_code in self.ECONOMY_PROFILES:
            return self.ECONOMY_PROFILES[country_code]

        # Default profile for unknown countries
        return EconomyProfile(
            primary_type=EconomyType.EMERGING,
            secondary_type=None,
            key_indicators=['gdp', 'inflation', 'trade'],
            volatility=0.5,
            external_dependency=0.5,
            growth_potential=0.5
        )

    async def predict_gdp(self, country_code: str) -> Dict:
        """Predict GDP based on economy type"""

        profile = self.get_economy_profile(country_code)

        result = {
            'country_code': country_code,
            'economy_type': profile.primary_type.value,
            'timestamp': datetime.now().isoformat(),
            'prediction': None,
            'confidence': 0.0,
            'methodology': None,
            'factors': {}
        }

        # Select prediction method based on economy type
        if profile.primary_type == EconomyType.DEVELOPED:
            prediction = await self._predict_developed_economy(country_code, profile)
        elif profile.primary_type == EconomyType.EMERGING:
            prediction = await self._predict_emerging_economy(country_code, profile)
        elif profile.primary_type == EconomyType.OIL_DEPENDENT:
            prediction = await self._predict_oil_economy(country_code, profile)
        elif profile.primary_type == EconomyType.EXPORT_DRIVEN:
            prediction = await self._predict_export_economy(country_code, profile)
        elif profile.primary_type == EconomyType.FRONTIER:
            prediction = await self._predict_frontier_economy(country_code, profile)
        else:
            prediction = await self._predict_generic_economy(country_code, profile)

        result.update(prediction)
        return result

    async def _predict_developed_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Prediction model for developed economies"""

        factors = {}
        weights = {}

        # Get relevant data
        series = self.CORRECTED_FRED_SERIES.get(country_code, {})

        # 1. Historical GDP trend (40% weight)
        if 'gdp' in series:
            try:
                gdp_data = self.data_integration.get_fred_data(series['gdp'])
                if not gdp_data.empty:
                    # Calculate trend growth
                    recent_growth = gdp_data.pct_change(periods=4).iloc[-5:].mean() * 100
                    factors['historical_trend'] = recent_growth
                    weights['historical_trend'] = 0.4
            except Exception as e:
                logger.error(f"Failed to get GDP data for {country_code}: {e}")

        # 2. Consumer indicators (20% weight)
        if 'consumer_conf' in series:
            try:
                consumer_data = self.data_integration.get_fred_data(series['consumer_conf'])
                if not consumer_data.empty:
                    # Consumer confidence change
                    consumer_trend = consumer_data.pct_change(periods=3).iloc[-1]
                    factors['consumer'] = consumer_trend * 10  # Scale to GDP impact
                    weights['consumer'] = 0.2
            except:
                pass

        # 3. Industrial/Service sector (20% weight)
        if profile.secondary_type == EconomyType.SERVICE_BASED:
            # Service sector indicators
            factors['sector'] = 2.5  # Base service growth
            weights['sector'] = 0.2
        else:
            # Industrial production
            if 'industrial' in series:
                try:
                    industrial_data = self.data_integration.get_fred_data(series['industrial'])
                    if not industrial_data.empty:
                        industrial_growth = industrial_data.pct_change(periods=12).iloc[-1] * 100
                        factors['sector'] = industrial_growth * 0.3  # Industrial contribution
                        weights['sector'] = 0.2
                except:
                    pass

        # 4. Monetary policy impact (10% weight)
        if 'fed_funds' in series or country_code in ['USA', 'GBR', 'EUR']:
            # Interest rate impact on growth
            factors['monetary'] = -0.5  # Tightening impact
            weights['monetary'] = 0.1

        # 5. External factors (10% weight)
        factors['external'] = 0.0  # Global growth spillover
        weights['external'] = 0.1

        # Calculate weighted prediction
        if factors:
            total_weight = sum(weights.values())
            weighted_sum = sum(factors.get(k, 0) * weights.get(k, 0) for k in factors)
            prediction = weighted_sum / total_weight if total_weight > 0 else 2.0

            # Adjust for volatility
            prediction *= (1 - profile.volatility * 0.2)

            confidence = min(0.8, total_weight)
        else:
            # Fallback for developed economies
            prediction = 2.0
            confidence = 0.3

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'developed_economy_model',
            'factors': factors,
            'weights': weights
        }

    async def _predict_emerging_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Prediction model for emerging economies"""

        factors = {}
        weights = {}

        series = self.CORRECTED_FRED_SERIES.get(country_code, {})

        # 1. Growth momentum (35% weight)
        if 'gdp' in series:
            try:
                gdp_data = self.data_integration.get_fred_data(series['gdp'])
                if not gdp_data.empty:
                    # Higher weight on recent growth for emerging markets
                    recent_growth = gdp_data.pct_change(periods=4).iloc[-3:].mean() * 100
                    factors['momentum'] = recent_growth
                    weights['momentum'] = 0.35
            except:
                pass

        # 2. Industrial/Manufacturing (25% weight)
        if 'industrial' in series:
            try:
                industrial_data = self.data_integration.get_fred_data(series['industrial'])
                if not industrial_data.empty:
                    industrial_growth = industrial_data.pct_change(periods=12).iloc[-1] * 100
                    factors['industrial'] = industrial_growth * 0.5
                    weights['industrial'] = 0.25
            except:
                pass

        # 3. Export performance (20% weight)
        if 'exports' in series:
            try:
                export_data = self.data_integration.get_fred_data(series['exports'])
                if not export_data.empty:
                    export_growth = export_data.pct_change(periods=12).iloc[-1] * 100
                    factors['exports'] = export_growth * 0.3
                    weights['exports'] = 0.2
            except:
                pass

        # 4. Investment/FDI trends (10% weight)
        factors['investment'] = profile.growth_potential * 5  # Growth potential proxy
        weights['investment'] = 0.1

        # 5. Inflation impact (10% weight)
        if 'cpi' in series:
            try:
                cpi_data = self.data_integration.get_fred_data(series['cpi'])
                if not cpi_data.empty:
                    inflation = cpi_data.pct_change(periods=12).iloc[-1] * 100
                    # High inflation hurts growth
                    factors['inflation_drag'] = max(-2, min(0, 5 - inflation))
                    weights['inflation_drag'] = 0.1
            except:
                pass

        # Calculate prediction
        if factors:
            total_weight = sum(weights.values())
            weighted_sum = sum(factors.get(k, 0) * weights.get(k, 0) for k in factors)
            prediction = weighted_sum / total_weight if total_weight > 0 else 4.5

            # Emerging markets have higher base growth
            prediction += profile.growth_potential * 2

            # But also higher volatility
            prediction *= (1 - profile.volatility * 0.15)

            confidence = min(0.7, total_weight * 0.9)
        else:
            # Fallback for emerging economies
            prediction = 4.5
            confidence = 0.3

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'emerging_economy_model',
            'factors': factors,
            'weights': weights
        }

    async def _predict_oil_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Prediction model for oil-dependent economies"""

        factors = {}
        weights = {}

        series = self.CORRECTED_FRED_SERIES.get(country_code, {})

        # 1. Oil price impact (50% weight)
        try:
            oil_data = self.data_integration.get_fred_data('DCOILWTICO')
            if not oil_data.empty:
                # Oil price change impact
                oil_change = oil_data.pct_change(periods=252).iloc[-1] * 100
                # Oil economies benefit from higher prices
                factors['oil_impact'] = oil_change * 0.1
                weights['oil_impact'] = 0.5
        except:
            factors['oil_impact'] = 0
            weights['oil_impact'] = 0.5

        # 2. Production volumes (20% weight)
        if 'oil_production' in series:
            try:
                production_data = self.data_integration.get_fred_data(series['oil_production'])
                if not production_data.empty:
                    production_change = production_data.pct_change(periods=12).iloc[-1] * 100
                    factors['production'] = production_change
                    weights['production'] = 0.2
            except:
                pass

        # 3. Diversification efforts (15% weight)
        if 'non_oil_gdp' in series:
            factors['diversification'] = 3.0  # Non-oil sector growth
            weights['diversification'] = 0.15
        else:
            factors['diversification'] = 1.0
            weights['diversification'] = 0.15

        # 4. Global demand (15% weight)
        factors['global_demand'] = 2.5  # Base global energy demand
        weights['global_demand'] = 0.15

        # Calculate prediction
        if factors:
            total_weight = sum(weights.values())
            weighted_sum = sum(factors.get(k, 0) * weights.get(k, 0) for k in factors)
            prediction = weighted_sum / total_weight if total_weight > 0 else 2.5

            # High volatility adjustment
            prediction *= (1 - profile.volatility * 0.1)

            confidence = min(0.65, total_weight * 0.8)
        else:
            prediction = 2.5
            confidence = 0.25

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'oil_economy_model',
            'factors': factors,
            'weights': weights
        }

    async def _predict_export_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Prediction model for export-driven economies"""

        factors = {}
        weights = {}

        series = self.CORRECTED_FRED_SERIES.get(country_code, {})

        # 1. Export performance (40% weight)
        if 'exports' in series:
            try:
                export_data = self.data_integration.get_fred_data(series['exports'])
                if not export_data.empty:
                    export_growth = export_data.pct_change(periods=12).iloc[-1] * 100
                    factors['exports'] = export_growth * 0.4
                    weights['exports'] = 0.4
            except:
                factors['exports'] = 2.0
                weights['exports'] = 0.4

        # 2. Global trade growth (25% weight)
        factors['global_trade'] = 3.0  # Base global trade growth
        weights['global_trade'] = 0.25

        # 3. Manufacturing PMI (20% weight)
        if 'industrial' in series:
            try:
                industrial_data = self.data_integration.get_fred_data(series['industrial'])
                if not industrial_data.empty:
                    industrial_growth = industrial_data.pct_change(periods=12).iloc[-1] * 100
                    factors['manufacturing'] = industrial_growth * 0.3
                    weights['manufacturing'] = 0.2
            except:
                pass

        # 4. Currency competitiveness (15% weight)
        factors['currency'] = 0.5  # Competitive currency benefit
        weights['currency'] = 0.15

        # Calculate prediction
        if factors:
            total_weight = sum(weights.values())
            weighted_sum = sum(factors.get(k, 0) * weights.get(k, 0) for k in factors)
            prediction = weighted_sum / total_weight if total_weight > 0 else 2.5

            # High external dependency adjustment
            prediction *= (1 + profile.external_dependency * 0.1)

            confidence = min(0.7, total_weight * 0.85)
        else:
            prediction = 2.5
            confidence = 0.3

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'export_economy_model',
            'factors': factors,
            'weights': weights
        }

    async def _predict_frontier_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Prediction model for frontier economies"""

        factors = {}
        weights = {}

        # Frontier economies often have limited data
        # Use more qualitative factors

        # 1. Demographics dividend (30% weight)
        factors['demographics'] = profile.growth_potential * 6
        weights['demographics'] = 0.3

        # 2. FDI and investment (25% weight)
        factors['investment'] = 4.0  # Base FDI growth
        weights['investment'] = 0.25

        # 3. Commodity prices (20% weight)
        factors['commodities'] = 1.0
        weights['commodities'] = 0.2

        # 4. Political stability (15% weight)
        factors['stability'] = -profile.volatility * 3
        weights['stability'] = 0.15

        # 5. Infrastructure development (10% weight)
        factors['infrastructure'] = 2.0
        weights['infrastructure'] = 0.1

        # Calculate prediction
        total_weight = sum(weights.values())
        weighted_sum = sum(factors.get(k, 0) * weights.get(k, 0) for k in factors)
        prediction = weighted_sum / total_weight if total_weight > 0 else 5.0

        # High growth potential but high volatility
        prediction += profile.growth_potential * 3
        prediction *= (1 - profile.volatility * 0.2)

        confidence = 0.4  # Lower confidence for frontier markets

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'frontier_economy_model',
            'factors': factors,
            'weights': weights
        }

    async def _predict_generic_economy(self, country_code: str, profile: EconomyProfile) -> Dict:
        """Generic prediction model for unclassified economies"""

        # Use simple trend-based prediction
        series = self.CORRECTED_FRED_SERIES.get(country_code, {})

        if 'gdp' in series:
            try:
                gdp_data = self.data_integration.get_fred_data(series['gdp'])
                if not gdp_data.empty:
                    recent_growth = gdp_data.pct_change(periods=4).iloc[-4:].mean() * 100
                    prediction = recent_growth
                    confidence = 0.5
                else:
                    prediction = 3.0
                    confidence = 0.2
            except:
                prediction = 3.0
                confidence = 0.2
        else:
            prediction = 3.0
            confidence = 0.2

        return {
            'prediction': round(prediction, 2),
            'confidence': confidence,
            'methodology': 'generic_model',
            'factors': {'trend': prediction},
            'weights': {'trend': 1.0}
        }

    async def predict_all_countries(self) -> Dict:
        """Run predictions for all countries"""

        results = {
            'timestamp': datetime.now().isoformat(),
            'predictions': {},
            'by_economy_type': {},
            'summary': {}
        }

        all_countries = list(self.ECONOMY_PROFILES.keys())

        for country_code in all_countries:
            logger.info(f"Predicting GDP for {country_code}")
            prediction = await self.predict_gdp(country_code)
            results['predictions'][country_code] = prediction

            # Group by economy type
            economy_type = prediction['economy_type']
            if economy_type not in results['by_economy_type']:
                results['by_economy_type'][economy_type] = []
            results['by_economy_type'][economy_type].append({
                'country': country_code,
                'prediction': prediction['prediction'],
                'confidence': prediction['confidence']
            })

        # Calculate summary statistics
        all_predictions = [p['prediction'] for p in results['predictions'].values() if p['prediction']]
        all_confidences = [p['confidence'] for p in results['predictions'].values() if p['confidence']]

        results['summary'] = {
            'total_countries': len(all_countries),
            'average_growth': round(np.mean(all_predictions), 2) if all_predictions else 0,
            'median_growth': round(np.median(all_predictions), 2) if all_predictions else 0,
            'average_confidence': round(np.mean(all_confidences), 2) if all_confidences else 0,
            'highest_growth': {
                'country': max(results['predictions'].items(),
                             key=lambda x: x[1]['prediction'] or 0)[0],
                'value': max(all_predictions) if all_predictions else 0
            },
            'lowest_growth': {
                'country': min(results['predictions'].items(),
                             key=lambda x: x[1]['prediction'] or 0)[0],
                'value': min(all_predictions) if all_predictions else 0
            }
        }

        return results


async def test_economy_aware_predictor():
    """Test the economy-aware GDP predictor"""

    predictor = EconomyAwareGDPPredictor()

    print("=" * 80)
    print("ECONOMY-AWARE GDP PREDICTOR TEST")
    print("=" * 80)

    # Test different economy types
    test_countries = [
        ('USA', 'Developed/Service'),
        ('CHN', 'Emerging/Manufacturing'),
        ('SAU', 'Oil-Dependent'),
        ('DEU', 'Export-Driven'),
        ('IND', 'Emerging/Service'),
        ('NGA', 'Frontier/Oil'),
        ('SGP', 'Small Open'),
        ('BRA', 'Emerging/Commodity')
    ]

    for country_code, description in test_countries:
        print(f"\n{country_code} ({description}):")
        print("-" * 40)

        result = await predictor.predict_gdp(country_code)

        print(f"  Economy Type: {result['economy_type']}")
        print(f"  GDP Prediction: {result['prediction']}%")
        print(f"  Confidence: {result['confidence']*100:.0f}%")
        print(f"  Methodology: {result['methodology']}")

        if result['factors']:
            print(f"  Key Factors:")
            for factor, value in sorted(result['factors'].items(),
                                       key=lambda x: result['weights'].get(x[0], 0),
                                       reverse=True)[:3]:
                weight = result['weights'].get(factor, 0)
                print(f"    - {factor}: {value:.2f} (weight: {weight*100:.0f}%)")

    print("\n" + "=" * 80)
    print("RUNNING FULL COUNTRY ANALYSIS...")
    print("=" * 80)

    # Run full analysis
    full_results = await predictor.predict_all_countries()

    print(f"\nSummary Statistics:")
    print(f"  Total Countries: {full_results['summary']['total_countries']}")
    print(f"  Average Growth: {full_results['summary']['average_growth']}%")
    print(f"  Median Growth: {full_results['summary']['median_growth']}%")
    print(f"  Average Confidence: {full_results['summary']['average_confidence']*100:.0f}%")
    print(f"  Highest Growth: {full_results['summary']['highest_growth']['country']} "
          f"({full_results['summary']['highest_growth']['value']}%)")
    print(f"  Lowest Growth: {full_results['summary']['lowest_growth']['country']} "
          f"({full_results['summary']['lowest_growth']['value']}%)")

    print(f"\nBy Economy Type:")
    for economy_type, countries in full_results['by_economy_type'].items():
        avg_growth = np.mean([c['prediction'] for c in countries])
        print(f"  {economy_type}: {len(countries)} countries, avg {avg_growth:.2f}%")

    # Save results
    import json
    output_file = f"economy_aware_gdp_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(full_results, f, indent=2, default=str)

    print(f"\n📊 Full results saved to {output_file}")

    return full_results


if __name__ == "__main__":
    asyncio.run(test_economy_aware_predictor())