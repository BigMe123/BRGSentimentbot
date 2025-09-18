"""
Region to Country Mapping System
Provides automatic expansion from regions to countries with proper tagging
"""

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass


@dataclass
class CountryInfo:
    """Country information with metadata"""
    name: str
    iso_code: str
    region: str
    subregion: str
    languages: List[str]
    timezone: str
    gdp_rank: Optional[int] = None
    population_rank: Optional[int] = None
    market_type: str = "emerging"  # developed, emerging, frontier


class RegionCountryMapper:
    """Maps regions to countries and provides selection logic"""

    def __init__(self):
        self.regions = self._initialize_regions()
        self.countries = self._initialize_countries()
        self.economic_blocs = self._initialize_economic_blocs()

    def _initialize_regions(self) -> Dict[str, List[str]]:
        """Initialize region to country mappings"""
        return {
            'americas': {
                'north_america': ['United States', 'Canada', 'Mexico'],
                'central_america': ['Guatemala', 'Honduras', 'El Salvador', 'Nicaragua',
                                   'Costa Rica', 'Panama', 'Belize'],
                'caribbean': ['Cuba', 'Dominican Republic', 'Haiti', 'Jamaica', 'Trinidad and Tobago',
                            'Barbados', 'Bahamas', 'Puerto Rico'],
                'south_america': ['Brazil', 'Argentina', 'Colombia', 'Peru', 'Venezuela', 'Chile',
                                'Ecuador', 'Bolivia', 'Paraguay', 'Uruguay', 'Guyana', 'Suriname']
            },
            'europe': {
                'western_europe': ['United Kingdom', 'France', 'Germany', 'Netherlands', 'Belgium',
                                 'Luxembourg', 'Ireland', 'Austria', 'Switzerland', 'Liechtenstein'],
                'southern_europe': ['Spain', 'Portugal', 'Italy', 'Greece', 'Malta', 'Cyprus',
                                   'San Marino', 'Vatican City', 'Andorra', 'Monaco'],
                'northern_europe': ['Sweden', 'Norway', 'Denmark', 'Finland', 'Iceland',
                                  'Estonia', 'Latvia', 'Lithuania'],
                'eastern_europe': ['Poland', 'Czech Republic', 'Slovakia', 'Hungary', 'Romania',
                                 'Bulgaria', 'Croatia', 'Slovenia', 'Serbia', 'Bosnia and Herzegovina',
                                 'Montenegro', 'North Macedonia', 'Albania', 'Kosovo', 'Moldova'],
                'eurasia': ['Russia', 'Belarus', 'Ukraine', 'Georgia', 'Armenia', 'Azerbaijan']
            },
            'asia': {
                'east_asia': ['China', 'Japan', 'South Korea', 'North Korea', 'Taiwan',
                            'Mongolia', 'Hong Kong', 'Macau'],
                'southeast_asia': ['Indonesia', 'Thailand', 'Philippines', 'Vietnam', 'Malaysia',
                                 'Singapore', 'Myanmar', 'Cambodia', 'Laos', 'Brunei',
                                 'East Timor'],
                'south_asia': ['India', 'Pakistan', 'Bangladesh', 'Sri Lanka', 'Nepal',
                             'Bhutan', 'Afghanistan', 'Maldives'],
                'central_asia': ['Kazakhstan', 'Uzbekistan', 'Turkmenistan', 'Kyrgyzstan',
                               'Tajikistan']
            },
            'middle_east': {
                'gulf_states': ['Saudi Arabia', 'UAE', 'Qatar', 'Kuwait', 'Bahrain', 'Oman'],
                'levant': ['Israel', 'Palestine', 'Lebanon', 'Syria', 'Jordan'],
                'other_middle_east': ['Iran', 'Iraq', 'Turkey', 'Yemen', 'Egypt']
            },
            'africa': {
                'north_africa': ['Egypt', 'Libya', 'Tunisia', 'Algeria', 'Morocco', 'Sudan',
                               'Western Sahara'],
                'west_africa': ['Nigeria', 'Ghana', 'Senegal', 'Mali', 'Burkina Faso',
                              'Niger', 'Ivory Coast', 'Guinea', 'Benin', 'Togo',
                              'Sierra Leone', 'Liberia', 'Mauritania', 'Gambia',
                              'Guinea-Bissau', 'Cape Verde'],
                'east_africa': ['Ethiopia', 'Kenya', 'Tanzania', 'Uganda', 'Rwanda',
                              'Burundi', 'Somalia', 'Eritrea', 'Djibouti', 'South Sudan',
                              'Seychelles', 'Comoros', 'Mauritius', 'Madagascar'],
                'central_africa': ['Democratic Republic of Congo', 'Cameroon', 'Angola',
                                 'Chad', 'Central African Republic', 'Republic of Congo',
                                 'Gabon', 'Equatorial Guinea', 'Sao Tome and Principe'],
                'southern_africa': ['South Africa', 'Zimbabwe', 'Botswana', 'Namibia',
                                  'Mozambique', 'Zambia', 'Malawi', 'Lesotho', 'Eswatini']
            },
            'oceania': {
                'australia_nz': ['Australia', 'New Zealand'],
                'pacific_islands': ['Fiji', 'Papua New Guinea', 'Solomon Islands', 'Vanuatu',
                                  'Samoa', 'Tonga', 'Kiribati', 'Palau', 'Marshall Islands',
                                  'Micronesia', 'Nauru', 'Tuvalu']
            }
        }

    def _initialize_countries(self) -> Dict[str, CountryInfo]:
        """Initialize detailed country information"""
        countries = {}

        # Major economies (G20 + important markets)
        major_countries = {
            'United States': CountryInfo('United States', 'US', 'americas', 'north_america',
                                       ['en'], 'America/New_York', 1, 3, 'developed'),
            'China': CountryInfo('China', 'CN', 'asia', 'east_asia',
                               ['zh'], 'Asia/Shanghai', 2, 1, 'emerging'),
            'Japan': CountryInfo('Japan', 'JP', 'asia', 'east_asia',
                               ['ja'], 'Asia/Tokyo', 3, 11, 'developed'),
            'Germany': CountryInfo('Germany', 'DE', 'europe', 'western_europe',
                                 ['de'], 'Europe/Berlin', 4, 17, 'developed'),
            'India': CountryInfo('India', 'IN', 'asia', 'south_asia',
                               ['hi', 'en'], 'Asia/Kolkata', 5, 2, 'emerging'),
            'United Kingdom': CountryInfo('United Kingdom', 'GB', 'europe', 'western_europe',
                                        ['en'], 'Europe/London', 6, 21, 'developed'),
            'France': CountryInfo('France', 'FR', 'europe', 'western_europe',
                                ['fr'], 'Europe/Paris', 7, 22, 'developed'),
            'Brazil': CountryInfo('Brazil', 'BR', 'americas', 'south_america',
                                ['pt'], 'America/Sao_Paulo', 8, 6, 'emerging'),
            'Italy': CountryInfo('Italy', 'IT', 'europe', 'southern_europe',
                               ['it'], 'Europe/Rome', 9, 23, 'developed'),
            'Canada': CountryInfo('Canada', 'CA', 'americas', 'north_america',
                                ['en', 'fr'], 'America/Toronto', 10, 38, 'developed'),
            'South Korea': CountryInfo('South Korea', 'KR', 'asia', 'east_asia',
                                     ['ko'], 'Asia/Seoul', 11, 28, 'developed'),
            'Russia': CountryInfo('Russia', 'RU', 'europe', 'eurasia',
                                ['ru'], 'Europe/Moscow', 12, 9, 'emerging'),
            'Spain': CountryInfo('Spain', 'ES', 'europe', 'southern_europe',
                               ['es'], 'Europe/Madrid', 13, 30, 'developed'),
            'Australia': CountryInfo('Australia', 'AU', 'oceania', 'australia_nz',
                                   ['en'], 'Australia/Sydney', 14, 54, 'developed'),
            'Mexico': CountryInfo('Mexico', 'MX', 'americas', 'north_america',
                                ['es'], 'America/Mexico_City', 15, 10, 'emerging'),
            'Indonesia': CountryInfo('Indonesia', 'ID', 'asia', 'southeast_asia',
                                   ['id'], 'Asia/Jakarta', 16, 4, 'emerging'),
            'Saudi Arabia': CountryInfo('Saudi Arabia', 'SA', 'middle_east', 'gulf_states',
                                      ['ar'], 'Asia/Riyadh', 17, 41, 'emerging'),
            'Turkey': CountryInfo('Turkey', 'TR', 'middle_east', 'other_middle_east',
                                ['tr'], 'Europe/Istanbul', 18, 18, 'emerging'),
            'Netherlands': CountryInfo('Netherlands', 'NL', 'europe', 'western_europe',
                                     ['nl'], 'Europe/Amsterdam', 19, 67, 'developed'),
            'Switzerland': CountryInfo('Switzerland', 'CH', 'europe', 'western_europe',
                                     ['de', 'fr', 'it'], 'Europe/Zurich', 20, 100, 'developed'),
        }

        countries.update(major_countries)

        # Add more countries as needed...
        # This is a subset - in production would have all countries

        return countries

    def _initialize_economic_blocs(self) -> Dict[str, List[str]]:
        """Initialize economic bloc memberships"""
        return {
            'G7': ['United States', 'Japan', 'Germany', 'United Kingdom',
                  'France', 'Italy', 'Canada'],
            'G20': ['United States', 'China', 'Japan', 'Germany', 'India',
                   'United Kingdom', 'France', 'Brazil', 'Italy', 'Canada',
                   'South Korea', 'Russia', 'Spain', 'Australia', 'Mexico',
                   'Indonesia', 'Saudi Arabia', 'Turkey', 'Argentina', 'South Africa'],
            'BRICS': ['Brazil', 'Russia', 'India', 'China', 'South Africa',
                     'Saudi Arabia', 'Iran', 'Ethiopia', 'Egypt', 'Argentina', 'UAE'],
            'EU': ['Germany', 'France', 'Italy', 'Spain', 'Netherlands', 'Belgium',
                  'Austria', 'Ireland', 'Finland', 'Portugal', 'Greece', 'Czech Republic',
                  'Sweden', 'Denmark', 'Poland', 'Romania', 'Hungary', 'Slovakia',
                  'Bulgaria', 'Croatia', 'Slovenia', 'Lithuania', 'Latvia', 'Estonia',
                  'Luxembourg', 'Malta', 'Cyprus'],
            'ASEAN': ['Indonesia', 'Thailand', 'Philippines', 'Vietnam', 'Malaysia',
                     'Singapore', 'Myanmar', 'Cambodia', 'Laos', 'Brunei'],
            'NAFTA': ['United States', 'Canada', 'Mexico'],
            'MERCOSUR': ['Brazil', 'Argentina', 'Uruguay', 'Paraguay'],
            'GCC': ['Saudi Arabia', 'UAE', 'Qatar', 'Kuwait', 'Bahrain', 'Oman'],
            'AU': ['South Africa', 'Nigeria', 'Egypt', 'Kenya', 'Ethiopia', 'Ghana',
                  'Morocco', 'Algeria', 'Tunisia', 'Angola', 'Tanzania', 'Uganda'],
            'OPEC': ['Saudi Arabia', 'Iran', 'Iraq', 'UAE', 'Kuwait', 'Venezuela',
                   'Nigeria', 'Algeria', 'Angola', 'Libya', 'Equatorial Guinea',
                   'Gabon', 'Congo', 'Azerbaijan'],
            'OECD': ['United States', 'Japan', 'Germany', 'United Kingdom', 'France',
                   'Italy', 'Canada', 'South Korea', 'Spain', 'Australia', 'Mexico',
                   'Netherlands', 'Switzerland', 'Belgium', 'Sweden', 'Poland',
                   'Austria', 'Norway', 'Denmark', 'Ireland', 'Israel', 'Czech Republic',
                   'Finland', 'Portugal', 'Greece', 'New Zealand', 'Hungary', 'Chile',
                   'Turkey', 'Slovenia', 'Estonia', 'Luxembourg', 'Iceland', 'Latvia',
                   'Lithuania', 'Slovakia', 'Colombia', 'Costa Rica']
        }

    def get_countries_by_region(self, region: str) -> List[str]:
        """Get all countries in a region"""
        countries = []

        if region in self.regions:
            for subregion, country_list in self.regions[region].items():
                countries.extend(country_list)
        elif region == 'global' or region == 'all':
            for region_data in self.regions.values():
                for subregion, country_list in region_data.items():
                    countries.extend(country_list)

        return list(set(countries))  # Remove duplicates

    def get_countries_by_bloc(self, bloc: str) -> List[str]:
        """Get countries by economic bloc"""
        return self.economic_blocs.get(bloc.upper(), [])

    def get_major_countries_by_region(self, region: str, limit: int = 5) -> List[str]:
        """Get major countries by GDP ranking in a region"""
        region_countries = self.get_countries_by_region(region)

        # Filter by countries we have GDP data for
        ranked_countries = []
        for country_name in region_countries:
            if country_name in self.countries:
                country_info = self.countries[country_name]
                if country_info.gdp_rank:
                    ranked_countries.append((country_name, country_info.gdp_rank))

        # Sort by GDP rank
        ranked_countries.sort(key=lambda x: x[1])

        return [country for country, _ in ranked_countries[:limit]]

    def expand_selection(self, regions: List[str] = None,
                        countries: List[str] = None,
                        blocs: List[str] = None,
                        include_neighbors: bool = False) -> Set[str]:
        """
        Expand selection based on various criteria
        Returns a set of country names
        """
        selected = set()

        # Add explicitly selected countries
        if countries:
            selected.update(countries)

        # Expand regions
        if regions:
            for region in regions:
                selected.update(self.get_countries_by_region(region))

        # Expand economic blocs
        if blocs:
            for bloc in blocs:
                selected.update(self.get_countries_by_bloc(bloc))

        # Add neighbors if requested
        if include_neighbors and countries:
            neighbors = self._get_neighbors(countries)
            selected.update(neighbors)

        return selected

    def _get_neighbors(self, countries: List[str]) -> Set[str]:
        """Get neighboring countries (simplified)"""
        neighbors = set()

        neighbor_map = {
            'United States': ['Canada', 'Mexico'],
            'China': ['India', 'Japan', 'Russia', 'South Korea', 'Vietnam', 'Mongolia'],
            'Germany': ['France', 'Poland', 'Czech Republic', 'Austria', 'Switzerland',
                       'Denmark', 'Netherlands', 'Belgium', 'Luxembourg'],
            'India': ['Pakistan', 'China', 'Bangladesh', 'Nepal', 'Sri Lanka', 'Myanmar'],
            'Brazil': ['Argentina', 'Uruguay', 'Paraguay', 'Colombia', 'Peru', 'Venezuela'],
            'Russia': ['China', 'Ukraine', 'Belarus', 'Kazakhstan', 'Finland', 'Norway'],
            # Add more as needed
        }

        for country in countries:
            if country in neighbor_map:
                neighbors.update(neighbor_map[country])

        return neighbors

    def get_sources_for_countries(self, countries: Set[str],
                                 source_catalog: Any) -> List[Any]:
        """
        Get news sources for selected countries
        This would interface with the source catalog
        """
        sources = []

        for country in countries:
            # Get country code
            country_info = self.countries.get(country)
            if country_info:
                # Query source catalog for this country
                # This is a placeholder - would integrate with actual catalog
                country_sources = source_catalog.get_sources_by_country(
                    country_info.iso_code
                )
                sources.extend(country_sources)

        return sources

    def get_regional_languages(self, region: str) -> Set[str]:
        """Get all languages spoken in a region"""
        languages = set()
        countries = self.get_countries_by_region(region)

        for country in countries:
            if country in self.countries:
                languages.update(self.countries[country].languages)

        return languages

    def classify_markets(self, countries: Set[str]) -> Dict[str, List[str]]:
        """Classify countries by market type"""
        classification = {
            'developed': [],
            'emerging': [],
            'frontier': []
        }

        for country in countries:
            if country in self.countries:
                market_type = self.countries[country].market_type
                classification[market_type].append(country)

        return classification


# Singleton instance
_mapper_instance = None


def get_region_mapper() -> RegionCountryMapper:
    """Get singleton instance of region mapper"""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = RegionCountryMapper()
    return _mapper_instance


# Export
__all__ = ['RegionCountryMapper', 'get_region_mapper', 'CountryInfo']