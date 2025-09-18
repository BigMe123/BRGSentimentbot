#!/usr/bin/env python3
"""
Multi-Country Economic Predictor
=================================
Supports economic predictions for all major economic powers using
country-specific FRED series and international data sources.
"""

import os
import sys
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import required modules
from sentiment_bot.comprehensive_economic_predictors import AlphaVantageClient
from sentiment_bot.ml_foundation import ModelConfig, DataIntegration


class MultiCountryEconomicPredictor:
    """Economic predictor supporting all major economic powers"""

    # FRED Series IDs for different countries
    COUNTRY_SERIES = {
        'USA': {
            'gdp': 'GDPC1',  # Real GDP
            'cpi': 'CPIAUCSL',  # CPI All Urban Consumers
            'unemployment': 'UNRATE',  # Unemployment Rate
            'employment': 'PAYEMS',  # All Employees Nonfarm
            'industrial': 'INDPRO',  # Industrial Production Index
            'retail': 'RSXFS',  # Retail Sales
            'consumer_conf': 'UMCSENT',  # U of Michigan Consumer Sentiment
        },
        'CHN': {  # China
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita (World Bank via FRED)
            'cpi': 'CHNCPIALLMINMEI',  # CPI China
            'unemployment': 'CHNURHARMMDSMEI',  # Unemployment Rate China
            'industrial': 'CHNPROINDMISMEI',  # Industrial Production China
            'exports': 'XTEXVA01CNM659S',  # Exports China
            'imports': 'XTIMVA01CNM659S',  # Imports China
        },
        'JPN': {  # Japan
            'gdp': 'JPNRGDPEXP',  # Real GDP Japan
            'cpi': 'JPNCPIALLMINMEI',  # CPI Japan
            'unemployment': 'JPNURHARMMDSMEI',  # Unemployment Rate Japan
            'industrial': 'JPNPROINDMISMEI',  # Industrial Production Japan
            'exports': 'JPNXTEXVA01CXMLM',  # Exports Japan
        },
        'DEU': {  # Germany
            'gdp': 'CLVMNACSAB1GQDE',  # Real GDP Germany
            'cpi': 'DEUCPIALLMINMEI',  # CPI Germany
            'unemployment': 'DEUURHARMMDSMEI',  # Unemployment Rate Germany
            'industrial': 'DEUPROINDMISMEI',  # Industrial Production Germany
            'exports': 'DEUXTEXVA01CXMLM',  # Exports Germany
        },
        'GBR': {  # United Kingdom
            'gdp': 'GBRRGDPQDSNAQ',  # Real GDP UK
            'cpi': 'GBRCPIALLMINMEI',  # CPI UK
            'unemployment': 'GBRURHARMMDSMEI',  # Unemployment Rate UK
            'industrial': 'GBRPROINDMISMEI',  # Industrial Production UK
            'retail': 'GBRSLRTTO01IXOBM',  # Retail Sales UK
        },
        'FRA': {  # France
            'gdp': 'CLVMNACSCAB1GQFR',  # Real GDP France
            'cpi': 'FRACPIALLMINMEI',  # CPI France
            'unemployment': 'FRAURHARMMDSMEI',  # Unemployment Rate France
            'industrial': 'FRAPROINDMISMEI',  # Industrial Production France
        },
        'IND': {  # India
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita (World Bank)
            'cpi': 'INDCPIALLMINMEI',  # CPI India
            'industrial': 'INDPROINDQISMEI',  # Industrial Production India
            'exports': 'INDXTEXVA01CXMLM',  # Exports India
        },
        'ITA': {  # Italy
            'gdp': 'CLVMNACSAB1GQIT',  # Real GDP Italy
            'cpi': 'ITACPIALLMINMEI',  # CPI Italy
            'unemployment': 'ITAURHARMMDSMEI',  # Unemployment Rate Italy
        },
        'CAN': {  # Canada
            'gdp': 'NGDPRSAXDCCAQ',  # Real GDP Canada
            'cpi': 'CANCPIALLMINMEI',  # CPI Canada
            'unemployment': 'CANURHARMMDSMEI',  # Unemployment Rate Canada
            'employment': 'LFEMTTTTCAM647S',  # Employment Canada
        },
        'KOR': {  # South Korea
            'gdp': 'NGDPRSAXDCKRQ',  # Real GDP South Korea
            'cpi': 'KORCPIALLMINMEI',  # CPI Korea
            'unemployment': 'KORURHARMMDSMEI',  # Unemployment Rate Korea
            'exports': 'KORXTEXVA01CXMLM',  # Exports Korea
        },
        'ESP': {  # Spain
            'gdp': 'CLVMNACSCAB1GQES',  # Real GDP Spain
            'cpi': 'ESPCPIALLMINMEI',  # CPI Spain
            'unemployment': 'ESPURHARMMDSMEI',  # Unemployment Rate Spain
        },
        'MEX': {  # Mexico
            'gdp': 'MEXRGDPQDSNAQ',  # Real GDP Mexico
            'cpi': 'MEXCPIALLMINMEI',  # CPI Mexico
            'unemployment': 'MEXURHARMMDSMEI',  # Unemployment Rate Mexico
        },
        'IDN': {  # Indonesia
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'cpi': 'IDNCPIALLMINMEI',  # CPI Indonesia
        },
        'NLD': {  # Netherlands
            'gdp': 'CLVMNACSCAB1GQNL',  # Real GDP Netherlands
            'cpi': 'NLDCPIALLMINMEI',  # CPI Netherlands
            'unemployment': 'NLDURHARMMDSMEI',  # Unemployment Rate Netherlands
        },
        'SAU': {  # Saudi Arabia
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'oil_production': 'SAUOILPRODM',  # Oil Production Saudi Arabia
        },
        'TUR': {  # Turkey
            'gdp': 'CLVMNACNSAB1GQTR',  # Real GDP Turkey
            'cpi': 'TURCPIALLMINMEI',  # CPI Turkey
            'unemployment': 'TURURHARMMDSMEI',  # Unemployment Rate Turkey
        },
        'CHE': {  # Switzerland
            'gdp': 'CLVMNACSCAB1GQCH',  # Real GDP Switzerland
            'cpi': 'CHECPIALLMINMEI',  # CPI Switzerland
            'unemployment': 'CHEURHARMMDSMEI',  # Unemployment Rate Switzerland
        },
        'POL': {  # Poland
            'gdp': 'CLVMNACSCAB1GQPL',  # Real GDP Poland
            'cpi': 'POLCPIALLMINMEI',  # CPI Poland
            'unemployment': 'POLURHARMMDSMEI',  # Unemployment Rate Poland
        },
        'BEL': {  # Belgium
            'gdp': 'CLVMNACSCAB1GQBE',  # Real GDP Belgium
            'cpi': 'BELCPIALLMINMEI',  # CPI Belgium
            'unemployment': 'BELURHARMMDSMEI',  # Unemployment Rate Belgium
        },
        'ARG': {  # Argentina
            'gdp': 'ARGRGDPQDSNAQ',  # Real GDP Argentina
            'cpi': 'ARGCPIALLMINMEI',  # CPI Argentina
            'unemployment': 'ARGURHARMQDSMEI',  # Unemployment Rate Argentina
        },
        'SWE': {  # Sweden
            'gdp': 'CLVMNACSCAB1GQSE',  # Real GDP Sweden
            'cpi': 'SWECPIALLMINMEI',  # CPI Sweden
            'unemployment': 'SWEURHARMMDSMEI',  # Unemployment Rate Sweden
        },
        'IRL': {  # Ireland
            'gdp': 'CLVMNACSCAB1GQIE',  # Real GDP Ireland
            'cpi': 'IRLCPIALLMINMEI',  # CPI Ireland
            'unemployment': 'IRLURHARMMDSMEI',  # Unemployment Rate Ireland
        },
        'ISR': {  # Israel
            'gdp': 'CLVMNACSCAB1GQIS',  # Real GDP Israel
            'cpi': 'ISRCPIALLMINMEI',  # CPI Israel
            'unemployment': 'ISRURHARMMDSMEI',  # Unemployment Rate Israel
        },
        'NOR': {  # Norway
            'gdp': 'CLVMNACSCAB1GQNO',  # Real GDP Norway
            'cpi': 'NORCPIALLMINMEI',  # CPI Norway
            'unemployment': 'NORURHARMMDSMEI',  # Unemployment Rate Norway
            'oil_revenue': 'NOROILREVENUE',  # Oil Revenue Norway
        },
        'ARE': {  # UAE
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'oil_production': 'AREOILPRODM',  # Oil Production UAE
        },
        'EGY': {  # Egypt
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'cpi': 'EGYCPIALLMINMEI',  # CPI Egypt
        },
        'DNK': {  # Denmark
            'gdp': 'CLVMNACSCAB1GQDK',  # Real GDP Denmark
            'cpi': 'DNKCPIALLMINMEI',  # CPI Denmark
            'unemployment': 'DNKURHARMMDSMEI',  # Unemployment Rate Denmark
        },
        'SGP': {  # Singapore
            'gdp': 'SGPRGDPQDSNAQ',  # Real GDP Singapore
            'cpi': 'SGPCPIALLMINMEI',  # CPI Singapore
            'unemployment': 'SGPURHARMMDSMEI',  # Unemployment Rate Singapore
        },
        'MYS': {  # Malaysia
            'gdp': 'MYSRGDPQDSNAQ',  # Real GDP Malaysia
            'cpi': 'MYSCPIALLMINMEI',  # CPI Malaysia
            'unemployment': 'MYSURHARMMDSMEI',  # Unemployment Rate Malaysia
        },
        'PHL': {  # Philippines
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'cpi': 'PHLCPIALLMINMEI',  # CPI Philippines
        },
        'ZAF': {  # South Africa
            'gdp': 'ZAFRGDPQDSNAQ',  # Real GDP South Africa
            'cpi': 'ZAFCPIALLMINMEI',  # CPI South Africa
            'unemployment': 'ZAFURHARMQDSMEI',  # Unemployment Rate South Africa
        },
        'COL': {  # Colombia
            'gdp': 'COLRGDPQDSNAQ',  # Real GDP Colombia
            'cpi': 'COLCPIALLMINMEI',  # CPI Colombia
            'unemployment': 'COLURHARMMDSMEI',  # Unemployment Rate Colombia
        },
        'PAK': {  # Pakistan
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'cpi': 'PAKCPIALLMINMEI',  # CPI Pakistan
        },
        'CHL': {  # Chile
            'gdp': 'CHLRGDPQDSNAQ',  # Real GDP Chile
            'cpi': 'CHLCPIALLMINMEI',  # CPI Chile
            'unemployment': 'CHLURHARMMDSMEI',  # Unemployment Rate Chile
        },
        'FIN': {  # Finland
            'gdp': 'CLVMNACSCAB1GQFI',  # Real GDP Finland
            'cpi': 'FINCPIALLMINMEI',  # CPI Finland
            'unemployment': 'FINURHARMMDSMEI',  # Unemployment Rate Finland
        },
        'ROU': {  # Romania
            'gdp': 'CLVMNACSCAB1GQRO',  # Real GDP Romania
            'cpi': 'ROUCPIALLMINMEI',  # CPI Romania
            'unemployment': 'ROUURHARMMDSMEI',  # Unemployment Rate Romania
        },
        'CZE': {  # Czech Republic
            'gdp': 'CLVMNACSCAB1GQCZ',  # Real GDP Czech Republic
            'cpi': 'CZECPIALLMINMEI',  # CPI Czech Republic
            'unemployment': 'CZEURHARMMDSMEI',  # Unemployment Rate Czech Republic
        },
        'NZL': {  # New Zealand
            'gdp': 'NZLRGDPQDSNAQ',  # Real GDP New Zealand
            'cpi': 'NZLCPIALLMINMEI',  # CPI New Zealand
            'unemployment': 'NZLURHARMQDSMEI',  # Unemployment Rate New Zealand
        },
        'PRT': {  # Portugal
            'gdp': 'CLVMNACSCAB1GQPT',  # Real GDP Portugal
            'cpi': 'PRTCPIALLMINMEI',  # CPI Portugal
            'unemployment': 'PRTURHARMMDSMEI',  # Unemployment Rate Portugal
        },
        'GRC': {  # Greece
            'gdp': 'CLVMNACSCAB1GQGR',  # Real GDP Greece
            'cpi': 'GRCCPIALLMINMEI',  # CPI Greece
            'unemployment': 'GRCURHARMMDSMEI',  # Unemployment Rate Greece
        },
        'HUN': {  # Hungary
            'gdp': 'CLVMNACSCAB1GQHU',  # Real GDP Hungary
            'cpi': 'HUNCPIALLMINMEI',  # CPI Hungary
            'unemployment': 'HUNURHARMMDSMEI',  # Unemployment Rate Hungary
        },
        'KWT': {  # Kuwait
            'gdp': 'NYGDPMKTPCDWLD',  # GDP per capita
            'oil_production': 'KWTOILPRODM',  # Oil Production Kuwait
        },
        'AUT': {  # Austria
            'gdp': 'CLVMNACSCAB1GQAT',  # Real GDP Austria
            'cpi': 'AUTCPIALLMINMEI',  # CPI Austria
            'unemployment': 'AUTURHARMMDSMEI',  # Unemployment Rate Austria
        },
        'RUS': {  # Russia
            'gdp': 'RURGDPQDSNAQ',  # Real GDP Russia (if available)
            'cpi': 'RUSCPIALLMINMEI',  # CPI Russia
            'unemployment': 'RUSURHARMMDSMEI',  # Unemployment Rate Russia
            'oil_production': 'RUSOILPRODM',  # Oil Production Russia
        },
        'BRA': {  # Brazil
            'gdp': 'BRACLVMNACSCAB1GQ',  # Real GDP Brazil
            'cpi': 'BRACPIALLMINMEI',  # CPI Brazil
            'unemployment': 'BRAURHARMMDSMEI',  # Unemployment Rate Brazil
        },
        'AUS': {  # Australia
            'gdp': 'AUSRGDPQDSNAQ',  # Real GDP Australia
            'cpi': 'AUSCPIALLMINMEI',  # CPI Australia
            'unemployment': 'AUSURHARMMDSMEI',  # Unemployment Rate Australia
            'employment': 'LFEMTTTTAUM647S',  # Employment Australia
        }
    }

    # Country name mappings
    COUNTRY_NAMES = {
        'USA': 'United States',
        'CHN': 'China',
        'JPN': 'Japan',
        'DEU': 'Germany',
        'GBR': 'United Kingdom',
        'FRA': 'France',
        'IND': 'India',
        'ITA': 'Italy',
        'CAN': 'Canada',
        'KOR': 'South Korea',
        'ESP': 'Spain',
        'MEX': 'Mexico',
        'IDN': 'Indonesia',
        'NLD': 'Netherlands',
        'SAU': 'Saudi Arabia',
        'TUR': 'Turkey',
        'CHE': 'Switzerland',
        'POL': 'Poland',
        'BEL': 'Belgium',
        'ARG': 'Argentina',
        'SWE': 'Sweden',
        'IRL': 'Ireland',
        'ISR': 'Israel',
        'NOR': 'Norway',
        'ARE': 'UAE',
        'EGY': 'Egypt',
        'DNK': 'Denmark',
        'SGP': 'Singapore',
        'MYS': 'Malaysia',
        'PHL': 'Philippines',
        'ZAF': 'South Africa',
        'COL': 'Colombia',
        'PAK': 'Pakistan',
        'CHL': 'Chile',
        'FIN': 'Finland',
        'ROU': 'Romania',
        'CZE': 'Czech Republic',
        'NZL': 'New Zealand',
        'PRT': 'Portugal',
        'GRC': 'Greece',
        'HUN': 'Hungary',
        'KWT': 'Kuwait',
        'AUT': 'Austria',
        'RUS': 'Russia',
        'BRA': 'Brazil',
        'AUS': 'Australia'
    }

    def __init__(self):
        """Initialize multi-country predictor"""

        # Set up API keys
        os.environ['FRED_API_KEY'] = '28eb3d64654c60195cfeed9bc4ec2a41'
        os.environ['ALPHA_VANTAGE_API_KEY'] = 'YILWUFW6VO1RA561'

        # Initialize config
        self.config = ModelConfig()
        self.config.fred_api_key = os.getenv('FRED_API_KEY')
        self.config.use_fred = True
        self.config.use_yfinance = True

        # Initialize Alpha Vantage client
        self.av_client = AlphaVantageClient()

        logger.info("Multi-country economic predictor initialized")

    def get_country_code(self, country_input: str) -> str:
        """Convert country name or code to 3-letter ISO code"""

        country_upper = country_input.upper()

        # Check if it's already a valid code
        if country_upper in self.COUNTRY_SERIES:
            return country_upper

        # Check country names
        for code, name in self.COUNTRY_NAMES.items():
            if country_input.lower() in name.lower():
                return code

        # Check common 2-letter to 3-letter conversions
        two_to_three = {
            'US': 'USA', 'CN': 'CHN', 'JP': 'JPN', 'DE': 'DEU',
            'GB': 'GBR', 'UK': 'GBR', 'FR': 'FRA', 'IN': 'IND',
            'IT': 'ITA', 'CA': 'CAN', 'KR': 'KOR', 'ES': 'ESP',
            'MX': 'MEX', 'ID': 'IDN', 'NL': 'NLD', 'SA': 'SAU',
            'TR': 'TUR', 'CH': 'CHE', 'PL': 'POL', 'BE': 'BEL',
            'AR': 'ARG', 'SE': 'SWE', 'IE': 'IRL', 'IL': 'ISR',
            'NO': 'NOR', 'AE': 'ARE', 'EG': 'EGY', 'DK': 'DNK',
            'SG': 'SGP', 'MY': 'MYS', 'PH': 'PHL', 'ZA': 'ZAF',
            'CO': 'COL', 'PK': 'PAK', 'CL': 'CHL', 'FI': 'FIN',
            'RO': 'ROU', 'CZ': 'CZE', 'NZ': 'NZL', 'PT': 'PRT',
            'GR': 'GRC', 'HU': 'HUN', 'KW': 'KWT', 'AT': 'AUT',
            'RU': 'RUS', 'BR': 'BRA', 'AU': 'AUS'
        }

        if country_upper in two_to_three:
            return two_to_three[country_upper]

        # Default to USA if not found
        logger.warning(f"Country '{country_input}' not found, defaulting to USA")
        return 'USA'

    async def predict_gdp(self, country: str) -> Dict:
        """Predict GDP growth for any supported country"""

        country_code = self.get_country_code(country)
        country_name = self.COUNTRY_NAMES.get(country_code, country)

        result = {
            'indicator': 'GDP Growth',
            'country': country_name,
            'country_code': country_code,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Get country-specific GDP series
            if country_code not in self.COUNTRY_SERIES:
                result['status'] = 'unsupported'
                result['error'] = f'Country {country_name} not in database'
                result['prediction'] = 'N/A'
                return result

            gdp_series_id = self.COUNTRY_SERIES[country_code].get('gdp')

            if not gdp_series_id:
                # Try World Bank data via Alpha Vantage
                async with self.av_client as client:
                    gdp_data = await client.get_economic_indicator('REAL_GDP', country=country_code)
                    if not gdp_data.empty:
                        gdp_growth = gdp_data['value'].pct_change(periods=4).iloc[-1] * 100
                        result['prediction'] = round(gdp_growth, 2)
                        result['confidence'] = 0.65
                        result['status'] = 'success'
                        result['source'] = 'Alpha Vantage'
                    else:
                        result['prediction'] = self._get_fallback_gdp(country_code)
                        result['confidence'] = 0.3
                        result['status'] = 'fallback'
            else:
                # Get data from FRED
                data_integration = DataIntegration(self.config)
                gdp_series = data_integration.get_fred_data(gdp_series_id)

                if not gdp_series.empty:
                    # Calculate growth rate based on series type
                    if 'Q' in gdp_series_id or 'GDPQ' in gdp_series_id:
                        # Quarterly data - annualized
                        gdp_growth = gdp_series.pct_change(periods=4).iloc[-1] * 100
                    else:
                        # Annual or monthly data
                        gdp_growth = gdp_series.pct_change(periods=1).iloc[-1] * 100

                    result['prediction'] = round(gdp_growth, 2)
                    result['confidence'] = 0.75
                    result['status'] = 'success'
                    result['source'] = 'FRED'
                    result['series_id'] = gdp_series_id
                else:
                    result['prediction'] = self._get_fallback_gdp(country_code)
                    result['confidence'] = 0.3
                    result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"GDP prediction failed for {country_name}: {e}")
            result['prediction'] = self._get_fallback_gdp(country_code)
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def predict_inflation(self, country: str) -> Dict:
        """Predict inflation for any supported country"""

        country_code = self.get_country_code(country)
        country_name = self.COUNTRY_NAMES.get(country_code, country)

        result = {
            'indicator': 'CPI/Inflation',
            'country': country_name,
            'country_code': country_code,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            if country_code not in self.COUNTRY_SERIES:
                result['status'] = 'unsupported'
                result['error'] = f'Country {country_name} not in database'
                result['prediction'] = 'N/A'
                return result

            cpi_series_id = self.COUNTRY_SERIES[country_code].get('cpi')

            if cpi_series_id:
                # Get CPI data from FRED
                data_integration = DataIntegration(self.config)
                cpi_series = data_integration.get_fred_data(cpi_series_id)

                if not cpi_series.empty:
                    # Calculate inflation rate
                    inflation = cpi_series.pct_change(periods=12).iloc[-1] * 100
                    result['prediction'] = round(inflation, 2)
                    result['confidence'] = 0.8
                    result['status'] = 'success'
                    result['source'] = 'FRED'
                    result['series_id'] = cpi_series_id
                else:
                    result['prediction'] = self._get_fallback_inflation(country_code)
                    result['confidence'] = 0.3
                    result['status'] = 'fallback'
            else:
                result['prediction'] = self._get_fallback_inflation(country_code)
                result['confidence'] = 0.3
                result['status'] = 'no_data'

        except Exception as e:
            logger.error(f"Inflation prediction failed for {country_name}: {e}")
            result['prediction'] = self._get_fallback_inflation(country_code)
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    def _get_fallback_gdp(self, country_code: str) -> float:
        """Get fallback GDP growth estimates"""

        # Regional averages as fallbacks
        fallback_gdp = {
            'USA': 2.5, 'CHN': 5.0, 'JPN': 1.0, 'DEU': 1.5, 'GBR': 1.8,
            'FRA': 1.6, 'IND': 6.5, 'ITA': 1.2, 'CAN': 2.3, 'KOR': 2.8,
            'ESP': 2.0, 'MEX': 2.2, 'IDN': 5.0, 'NLD': 1.7, 'SAU': 2.5,
            'TUR': 4.0, 'CHE': 1.5, 'POL': 3.5, 'BEL': 1.6, 'ARG': 2.0,
            'SWE': 2.0, 'IRL': 4.5, 'ISR': 3.0, 'NOR': 2.0, 'ARE': 3.5,
            'EGY': 4.0, 'DNK': 1.8, 'SGP': 3.0, 'MYS': 4.5, 'PHL': 5.5,
            'ZAF': 1.5, 'COL': 3.0, 'PAK': 4.0, 'CHL': 2.5, 'FIN': 1.5,
            'ROU': 3.5, 'CZE': 2.5, 'NZL': 2.5, 'PRT': 2.0, 'GRC': 2.0,
            'HUN': 3.0, 'KWT': 2.0, 'AUT': 1.6, 'RUS': 1.5, 'BRA': 2.5,
            'AUS': 2.3
        }

        return fallback_gdp.get(country_code, 2.5)

    def _get_fallback_inflation(self, country_code: str) -> float:
        """Get fallback inflation estimates"""

        fallback_inflation = {
            'USA': 3.2, 'CHN': 2.0, 'JPN': 2.5, 'DEU': 3.5, 'GBR': 4.0,
            'FRA': 3.0, 'IND': 5.5, 'ITA': 3.0, 'CAN': 3.5, 'KOR': 3.0,
            'ESP': 3.5, 'MEX': 4.5, 'IDN': 3.5, 'NLD': 3.5, 'SAU': 2.5,
            'TUR': 50.0, 'CHE': 1.5, 'POL': 5.0, 'BEL': 3.0, 'ARG': 100.0,
            'SWE': 3.0, 'IRL': 4.0, 'ISR': 3.5, 'NOR': 3.5, 'ARE': 2.0,
            'EGY': 15.0, 'DNK': 3.0, 'SGP': 3.5, 'MYS': 3.0, 'PHL': 4.0,
            'ZAF': 5.0, 'COL': 5.5, 'PAK': 15.0, 'CHL': 4.5, 'FIN': 3.0,
            'ROU': 6.0, 'CZE': 4.0, 'NZL': 4.0, 'PRT': 3.0, 'GRC': 3.0,
            'HUN': 5.5, 'KWT': 3.0, 'AUT': 3.5, 'RUS': 7.0, 'BRA': 4.5,
            'AUS': 4.0
        }

        return fallback_inflation.get(country_code, 3.5)

    async def get_supported_countries(self) -> List[Dict]:
        """Get list of all supported countries"""

        countries = []
        for code, name in self.COUNTRY_NAMES.items():
            series = self.COUNTRY_SERIES.get(code, {})
            countries.append({
                'code': code,
                'name': name,
                'data_coverage': {
                    'gdp': 'gdp' in series,
                    'cpi': 'cpi' in series,
                    'unemployment': 'unemployment' in series,
                    'employment': 'employment' in series or 'industrial' in series
                },
                'quality': 'high' if len(series) >= 3 else 'medium' if len(series) >= 2 else 'limited'
            })

        return sorted(countries, key=lambda x: x['name'])


async def test_multi_country_predictions():
    """Test predictions for multiple countries"""

    predictor = MultiCountryEconomicPredictor()

    # Test major economies
    test_countries = [
        'USA', 'China', 'Japan', 'Germany', 'UK',
        'India', 'France', 'Italy', 'Brazil', 'Canada',
        'South Korea', 'Australia', 'Russia', 'Spain', 'Mexico'
    ]

    print("🌍 Multi-Country Economic Predictions")
    print("=" * 60)

    for country in test_countries:
        print(f"\n📍 {country}:")

        # GDP prediction
        gdp = await predictor.predict_gdp(country)
        print(f"  GDP Growth: {gdp['prediction']}% (Confidence: {gdp['confidence']*100:.0f}%)")

        # Inflation prediction
        inflation = await predictor.predict_inflation(country)
        print(f"  Inflation: {inflation['prediction']}% (Confidence: {inflation['confidence']*100:.0f}%)")

        print(f"  Status: GDP={gdp['status']}, CPI={inflation['status']}")

        # Small delay between countries
        time.sleep(0.5)

    # Show all supported countries
    print("\n📊 All Supported Countries:")
    supported = await predictor.get_supported_countries()

    high_quality = [c for c in supported if c['quality'] == 'high']
    medium_quality = [c for c in supported if c['quality'] == 'medium']
    limited_quality = [c for c in supported if c['quality'] == 'limited']

    print(f"\n🟢 High Quality Data ({len(high_quality)} countries):")
    for c in high_quality[:10]:
        print(f"  {c['name']} ({c['code']})")

    print(f"\n🟡 Medium Quality Data ({len(medium_quality)} countries):")
    for c in medium_quality[:5]:
        print(f"  {c['name']} ({c['code']})")

    print(f"\n🔴 Limited Data ({len(limited_quality)} countries):")
    for c in limited_quality[:5]:
        print(f"  {c['name']} ({c['code']})")

    print(f"\n✅ Total countries supported: {len(supported)}")


if __name__ == "__main__":
    asyncio.run(test_multi_country_predictions())