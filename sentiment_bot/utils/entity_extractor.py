"""
Entity extraction and signal detection for articles.
"""

import re
from typing import List, Dict, Tuple
from collections import Counter
import hashlib


class EntityExtractor:
    """Extract entities and signals from text."""

    # Common market/financial entities
    KNOWN_ORGS = {
        "ECB",
        "Fed",
        "Federal Reserve",
        "BoE",
        "Bank of England",
        "BoJ",
        "Bank of Japan",
        "IMF",
        "World Bank",
        "BIS",
        "OECD",
        "G7",
        "G20",
        "EU",
        "UN",
        "NATO",
        "Apple",
        "Microsoft",
        "Google",
        "Amazon",
        "Meta",
        "Tesla",
        "Nvidia",
        "JPMorgan",
        "Goldman Sachs",
        "Morgan Stanley",
        "BlackRock",
        "Vanguard",
    }

    # Comprehensive countries and regions by continent
    COUNTRIES_BY_REGION = {
        "Europe": {
            # Western Europe
            "Germany",
            "France",
            "Italy",
            "Spain",
            "Netherlands",
            "Belgium",
            "Austria",
            "Switzerland",
            "Luxembourg",
            "Portugal",
            "Ireland",
            "UK",
            "United Kingdom",
            "Britain",
            # Northern Europe
            "Sweden",
            "Norway",
            "Denmark",
            "Finland",
            "Iceland",
            # Eastern Europe
            "Russia",
            "Poland",
            "Czech Republic",
            "Hungary",
            "Slovakia",
            "Romania",
            "Bulgaria",
            "Ukraine",
            "Belarus",
            "Lithuania",
            "Latvia",
            "Estonia",
            "Slovenia",
            "Croatia",
            "Serbia",
            "Bosnia",
            "Montenegro",
            "North Macedonia",
            "Albania",
            "Moldova",
            # Southern Europe
            "Greece",
            "Cyprus",
            "Malta",
            "Turkey",
        },
        "Americas": {
            # North America
            "United States",
            "USA",
            "US",
            "America",
            "Canada",
            "Mexico",
            # Central America
            "Guatemala",
            "Belize",
            "El Salvador",
            "Honduras",
            "Nicaragua",
            "Costa Rica",
            "Panama",
            # Caribbean
            "Cuba",
            "Jamaica",
            "Haiti",
            "Dominican Republic",
            "Puerto Rico",
            "Trinidad",
            "Barbados",
            # South America
            "Brazil",
            "Argentina",
            "Chile",
            "Peru",
            "Colombia",
            "Venezuela",
            "Ecuador",
            "Bolivia",
            "Paraguay",
            "Uruguay",
            "Guyana",
            "Suriname",
        },
        "Asia": {
            # East Asia
            "China",
            "Japan",
            "South Korea",
            "North Korea",
            "Mongolia",
            "Taiwan",
            # Southeast Asia
            "Indonesia",
            "Philippines",
            "Thailand",
            "Vietnam",
            "Malaysia",
            "Singapore",
            "Myanmar",
            "Cambodia",
            "Laos",
            "Brunei",
            "East Timor",
            # South Asia
            "India",
            "Pakistan",
            "Bangladesh",
            "Sri Lanka",
            "Nepal",
            "Bhutan",
            "Maldives",
            "Afghanistan",
            # Central Asia
            "Kazakhstan",
            "Uzbekistan",
            "Turkmenistan",
            "Kyrgyzstan",
            "Tajikistan",
            # Western Asia / Middle East
            "Saudi Arabia",
            "Iran",
            "Iraq",
            "Israel",
            "Jordan",
            "Lebanon",
            "Syria",
            "Yemen",
            "Oman",
            "UAE",
            "Qatar",
            "Kuwait",
            "Bahrain",
            "Georgia",
            "Armenia",
            "Azerbaijan",
        },
        "Africa": {
            # North Africa
            "Egypt",
            "Libya",
            "Tunisia",
            "Algeria",
            "Morocco",
            "Sudan",
            "South Sudan",
            # West Africa
            "Nigeria",
            "Ghana",
            "Senegal",
            "Mali",
            "Burkina Faso",
            "Niger",
            "Guinea",
            "Sierra Leone",
            "Liberia",
            "Ivory Coast",
            "Togo",
            "Benin",
            "Mauritania",
            "Gambia",
            "Guinea-Bissau",
            "Cape Verde",
            # East Africa
            "Ethiopia",
            "Kenya",
            "Tanzania",
            "Uganda",
            "Rwanda",
            "Burundi",
            "Somalia",
            "Eritrea",
            "Djibouti",
            "Comoros",
            "Seychelles",
            "Mauritius",
            "Madagascar",
            # Central Africa
            "Democratic Republic of Congo",
            "Central African Republic",
            "Chad",
            "Cameroon",
            "Equatorial Guinea",
            "Gabon",
            "Republic of Congo",
            "Sao Tome and Principe",
            # Southern Africa
            "South Africa",
            "Zimbabwe",
            "Zambia",
            "Botswana",
            "Namibia",
            "Lesotho",
            "Swaziland",
            "Malawi",
            "Mozambique",
            "Angola",
        },
        "Oceania": {
            "Australia",
            "New Zealand",
            "Papua New Guinea",
            "Fiji",
            "Solomon Islands",
            "Vanuatu",
            "Samoa",
            "Tonga",
            "Kiribati",
            "Palau",
            "Marshall Islands",
            "Micronesia",
            "Nauru",
            "Tuvalu",
        },
    }

    # Flatten for easy lookup
    KNOWN_GPES = set()
    COUNTRY_TO_REGION = {}
    for region, countries in COUNTRIES_BY_REGION.items():
        for country in countries:
            KNOWN_GPES.add(country)
            COUNTRY_TO_REGION[country] = region

    # Add common alternative names — maps variants to canonical name
    COUNTRY_ALIASES = {
        "US": "United States",
        "USA": "United States",
        "America": "United States",
        "U.S.": "United States",
        "U.S.A.": "United States",
        "UK": "United Kingdom",
        "Britain": "United Kingdom",
        "Great Britain": "United Kingdom",
        "England": "United Kingdom",
        "DRC": "Democratic Republic of Congo",
        "Congo": "Democratic Republic of Congo",
        "UAE": "United Arab Emirates",
        "Emirates": "United Arab Emirates",
        "South Korea": "South Korea",
        "Republic of Korea": "South Korea",
        "North Korea": "North Korea",
        "DPRK": "North Korea",
        "Ivory Coast": "Ivory Coast",
        "Cote d'Ivoire": "Ivory Coast",
        "Swaziland": "Swaziland",
        "Eswatini": "Swaziland",
        "Czech Republic": "Czech Republic",
        "Czechia": "Czech Republic",
        "East Timor": "East Timor",
        "Timor-Leste": "East Timor",
        "Palestine": "Palestine",
        "Palestinian": "Palestine",
        "Gaza": "Palestine",
        "West Bank": "Palestine",
        "Taiwan": "Taiwan",
        "Republic of China": "Taiwan",
        "Hong Kong": "Hong Kong",
        "Macau": "Macau",
        "Kosovo": "Kosovo",
    }

    # Market tickers patterns
    TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b(?:\.[A-Z]{1,2})?")

    # Currency pairs
    CURRENCY_PATTERN = re.compile(r"\b[A-Z]{3}/[A-Z]{3}\b|\b[A-Z]{6}\b")
    CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "CNY", "INR"}

    # Volatility triggers
    VOLATILITY_KEYWORDS = {
        "crisis",
        "crash",
        "surge",
        "plunge",
        "spike",
        "collapse",
        "rally",
        "tumble",
        "soar",
        "panic",
        "shock",
        "turmoil",
        "volatility",
        "uncertainty",
    }

    # Risk signals
    RISK_SIGNALS = {
        "high": ["crisis", "crash", "collapse", "panic", "emergency", "critical"],
        "elevated": ["concern", "worry", "risk", "threat", "warning", "caution"],
        "normal": ["stable", "steady", "moderate", "balanced", "neutral"],
        "low": ["calm", "quiet", "positive", "optimistic", "bullish"],
    }

    # spaCy NER availability (class-level, checked once)
    _spacy_extractor = None
    _spacy_checked = False

    @classmethod
    def _get_spacy_extractor(cls):
        """Skip spaCy NER — dict/regex path is fast and sufficient.

        spaCy + NLI model loading is extremely slow on MPS and causes hangs.
        The dictionary path catches all known orgs, countries, tickers, and
        currency pairs reliably. Re-enable only if a GPU backend is confirmed.
        """
        cls._spacy_checked = True
        cls._spacy_extractor = None
        return None

    def _canonicalize_entity(self, text: str, label: str) -> Dict[str, str]:
        """Canonicalize a spaCy entity using our dictionaries."""
        # Map spaCy labels to our types
        type_map = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "GPE", "LOC": "GPE", "NORP": "GPE"}
        etype = type_map.get(label, label)

        # Canonicalize country names via alias dict
        if etype == "GPE":
            canonical = self.COUNTRY_ALIASES.get(text, text)
            return {"text": canonical, "type": "GPE"}

        # Check if it matches a known org
        if text in self.KNOWN_ORGS:
            return {"text": text, "type": "ORG"}

        return {"text": text, "type": etype}

    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """
        Extract named entities from text.

        Uses spaCy NER when available (pip install spacy + model), with
        dictionary-based canonicalization. Falls back to pure regex/dict
        matching when spaCy is not installed.

        Tickers and currency pairs always use regex (where it's better).

        Returns:
            List of entity dictionaries with text and type
        """
        entities = []
        seen = set()

        # --- Try spaCy NER first ---
        spacy_ext = self._get_spacy_extractor()
        if spacy_ext is not None:
            try:
                aspects = spacy_ext.extract_aspects(text)
                for aspect in aspects:
                    if aspect.get("label") in ("PERSON", "ORG", "GPE", "LOC", "NORP"):
                        entity = self._canonicalize_entity(aspect["text"], aspect["label"])
                        key = (entity["text"], entity["type"])
                        if key not in seen:
                            seen.add(key)
                            entities.append(entity)
            except Exception:
                pass  # fall through to dict path

        # --- Dictionary fallback for ORG/GPE (always runs to catch what spaCy misses) ---
        for org in self.KNOWN_ORGS:
            if org in text:
                key = (org, "ORG")
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": org, "type": "ORG"})

        seen_countries = set()
        for gpe in self.KNOWN_GPES:
            if gpe in text:
                canonical = self.COUNTRY_ALIASES.get(gpe, gpe)
                key = (canonical, "GPE")
                if canonical not in seen_countries and key not in seen:
                    seen_countries.add(canonical)
                    seen.add(key)
                    entities.append({"text": canonical, "type": "GPE"})
        for alias, canonical in self.COUNTRY_ALIASES.items():
            if alias in text:
                key = (canonical, "GPE")
                if canonical not in seen_countries and key not in seen:
                    seen_countries.add(canonical)
                    seen.add(key)
                    entities.append({"text": canonical, "type": "GPE"})

        # --- Tickers (regex is better than NER for these) ---
        potential_tickers = self.TICKER_PATTERN.findall(text)
        for ticker in potential_tickers:
            if len(ticker) >= 2 and ticker not in {"THE", "AND", "FOR", "ARE", "BUT"}:
                key = (ticker, "TICKER")
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": ticker, "type": "TICKER"})

        # --- Currency pairs (regex) ---
        currency_matches = self.CURRENCY_PATTERN.findall(text)
        for match in currency_matches:
            if "/" in match:
                parts = match.split("/")
                if all(p in self.CURRENCIES for p in parts):
                    key = (match, "CURRENCY")
                    if key not in seen:
                        seen.add(key)
                        entities.append({"text": match, "type": "CURRENCY"})
            elif len(match) == 6:
                if match[:3] in self.CURRENCIES and match[3:] in self.CURRENCIES:
                    key = (match, "CURRENCY")
                    if key not in seen:
                        seen.add(key)
                        entities.append({"text": match, "type": "CURRENCY"})

        return entities

    def extract_tickers(self, text: str) -> List[str]:
        """Extract stock tickers from text."""
        tickers = []

        # Look for explicit ticker mentions (e.g., "AAPL", "MSFT")
        potential_tickers = self.TICKER_PATTERN.findall(text)

        for ticker in potential_tickers:
            # Filter out common words
            if (
                len(ticker) >= 2
                and len(ticker) <= 5
                and ticker
                not in {"THE", "AND", "FOR", "ARE", "BUT", "CEO", "IPO", "ETF"}
            ):
                tickers.append(ticker)

        # Look for index mentions
        index_patterns = [
            r"S&P\s*500",
            r"Dow\s*Jones",
            r"NASDAQ",
            r"FTSE",
            r"DAX",
            r"CAC",
            r"Nikkei",
            r"Hang\s*Seng",
            r"STOXX",
            r"Russell",
        ]

        for pattern in index_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # Convert to standard ticker format
                if "S&P" in pattern:
                    tickers.append("^GSPC")
                elif "Dow" in pattern:
                    tickers.append("^DJI")
                elif "NASDAQ" in pattern:
                    tickers.append("^IXIC")
                elif "FTSE" in pattern:
                    tickers.append("^FTSE")
                elif "DAX" in pattern:
                    tickers.append("^GDAXI")
                elif "Nikkei" in pattern:
                    tickers.append("^N225")
                elif "STOXX" in pattern:
                    tickers.append("^STOXX50E")

        return list(set(tickers))

    def detect_volatility(self, text: str) -> float:
        """
        Detect volatility signals in text.

        Args:
            text: Input text

        Returns:
            Volatility score between 0 and 1
        """
        text_lower = text.lower()

        # Count volatility keywords
        volatility_count = sum(
            1 for keyword in self.VOLATILITY_KEYWORDS if keyword in text_lower
        )

        # Normalize by text length (per 100 words)
        word_count = len(text.split())
        if word_count > 0:
            volatility_score = min(1.0, volatility_count / (word_count / 100))
        else:
            volatility_score = 0.0

        # Boost score for multiple exclamation marks or all caps
        if text.count("!") > 2:
            volatility_score = min(1.0, volatility_score * 1.2)

        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        if caps_ratio > 0.3:
            volatility_score = min(1.0, volatility_score * 1.1)

        return volatility_score

    def detect_risk_level(self, text: str, sentiment_score: float) -> str:
        """
        Detect risk level from text and sentiment.

        Args:
            text: Input text
            sentiment_score: Sentiment score (-1 to 1)

        Returns:
            Risk level string
        """
        text_lower = text.lower()

        # Count risk signal keywords
        risk_scores = {}
        for level, keywords in self.RISK_SIGNALS.items():
            risk_scores[level] = sum(1 for kw in keywords if kw in text_lower)

        # Get highest scoring level
        max_level = max(risk_scores, key=risk_scores.get)

        # Adjust based on sentiment
        if sentiment_score < -0.5 and max_level in ["normal", "low"]:
            return "elevated"
        elif sentiment_score < -0.7:
            return "high"
        elif sentiment_score > 0.5 and max_level in ["elevated", "high"]:
            return "normal"

        return max_level

    # NLI topic analyzer (class-level, checked once)
    _nli_analyzer = None
    _nli_checked = False

    # Map our theme labels to NLI-friendly natural language
    THEME_NLI_LABELS = {
        "inflation": "inflation and rising prices",
        "monetary_policy": "central bank monetary policy and interest rates",
        "economic_growth": "economic growth, GDP, or recession",
        "equity_markets": "stock markets and equities",
        "fixed_income": "bonds, yields, and fixed income",
        "fx_markets": "foreign exchange and currency markets",
        "geopolitical_risk": "war, military conflict, or sanctions",
        "political_risk": "elections, voting, or political campaigns",
        "energy_prices": "oil, gas, and energy prices",
        "green_transition": "renewable energy and climate policy",
        "ai_disruption": "artificial intelligence and machine learning",
        "crypto_markets": "cryptocurrency and blockchain",
    }

    @classmethod
    def _get_nli_analyzer(cls):
        """Skip local NLI — themes are pre-computed via HF Inference API.

        Local BART-large-MNLI hangs on MPS with large batches.
        The keyword fallback path is sufficient when HF API themes
        are not already attached to articles.
        """
        cls._nli_checked = True
        cls._nli_analyzer = None
        return None

    def extract_themes(self, text: str, topic: str = None) -> List[str]:
        """
        Extract key themes from text.

        Uses zero-shot NLI classification when ML extras are installed.
        Falls back to keyword matching otherwise.

        Returns:
            List of theme strings (max 5), ordered by confidence.
        """
        # --- Try NLI-based classification first ---
        nli = self._get_nli_analyzer()
        if nli is not None:
            try:
                nli_pipeline = nli._get_nli_pipeline()
                # Score all themes in one call using candidate_labels
                labels = list(self.THEME_NLI_LABELS.values())
                keys = list(self.THEME_NLI_LABELS.keys())

                result = nli_pipeline(
                    text[:1500],
                    candidate_labels=labels,
                    multi_label=True,
                )

                scored = []
                for label, score in zip(result["labels"], result["scores"]):
                    idx = labels.index(label)
                    if score > 0.3:
                        scored.append((keys[idx], score))

                scored.sort(key=lambda x: x[1], reverse=True)
                if scored:
                    return [theme for theme, _ in scored[:5]]
            except Exception:
                pass  # fall through to keyword path

        # --- Keyword fallback ---
        themes = []
        text_lower = text.lower()

        if any(word in text_lower for word in ["inflation", "cpi", "prices", "cost"]):
            themes.append("inflation")
        if any(word in text_lower for word in ["rate", "interest", "hike", "cut", "fed", "ecb"]):
            themes.append("monetary_policy")
        if any(word in text_lower for word in ["recession", "growth", "gdp", "economy"]):
            themes.append("economic_growth")
        if any(word in text_lower for word in ["stock", "equity", "share", "market"]):
            themes.append("equity_markets")
        if any(word in text_lower for word in ["bond", "yield", "treasury", "gilt"]):
            themes.append("fixed_income")
        if any(word in text_lower for word in ["dollar", "euro", "yen", "currency", "fx"]):
            themes.append("fx_markets")
        if any(word in text_lower for word in ["war", "conflict", "military", "sanctions"]):
            themes.append("geopolitical_risk")
        if any(word in text_lower for word in ["election", "vote", "poll", "candidate"]):
            themes.append("political_risk")
        if any(word in text_lower for word in ["oil", "gas", "energy", "opec", "crude"]):
            themes.append("energy_prices")
        if any(word in text_lower for word in ["renewable", "solar", "wind", "green"]):
            themes.append("green_transition")
        if any(word in text_lower for word in ["ai", "artificial intelligence", "ml", "gpt"]):
            themes.append("ai_disruption")
        if any(word in text_lower for word in ["crypto", "bitcoin", "blockchain", "defi"]):
            themes.append("crypto_markets")

        return themes[:5]

    def extract_country_mentions(self, text: str) -> List[Dict[str, str]]:
        """
        Extract country mentions from text with context.

        Args:
            text: Input text

        Returns:
            List of country mention dictionaries with country, region, and context
        """
        mentions = []
        text_lower = text.lower()

        # Look for country mentions
        for country in self.KNOWN_GPES:
            # Use word boundaries to avoid partial matches
            pattern = r"\b" + re.escape(country.lower()) + r"\b"
            matches = list(re.finditer(pattern, text_lower))

            if matches:
                # Get surrounding context for each match
                for match in matches:
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].strip()

                    # Normalize country name using aliases
                    normalized_country = self.COUNTRY_ALIASES.get(country, country)
                    region = self.COUNTRY_TO_REGION.get(normalized_country, "Unknown")

                    mentions.append(
                        {
                            "country": normalized_country,
                            "region": region,
                            "context": context,
                            "position": match.start(),
                        }
                    )

        return mentions

    def analyze_country_sentiment(
        self, country_mentions: List[Dict], sentiment_score: float, text: str
    ) -> List[Dict]:
        """
        Analyze sentiment for mentioned countries.

        Args:
            country_mentions: List of country mention dictionaries
            sentiment_score: Overall article sentiment score
            text: Full article text

        Returns:
            List of country sentiment dictionaries
        """
        country_sentiments = []
        text_lower = text.lower()

        # Define positive and negative context keywords
        positive_keywords = {
            "growth",
            "success",
            "prosperity",
            "stable",
            "strong",
            "positive",
            "improvement",
            "progress",
            "development",
            "opportunity",
            "investment",
            "boom",
            "recovery",
            "breakthrough",
            "achievement",
            "victory",
            "alliance",
            "cooperation",
            "peace",
        }

        negative_keywords = {
            "crisis",
            "conflict",
            "war",
            "instability",
            "corruption",
            "recession",
            "decline",
            "collapse",
            "threat",
            "sanctions",
            "violence",
            "protests",
            "unrest",
            "chaos",
            "failure",
            "scandal",
            "attack",
            "terrorism",
            "poverty",
            "unemployment",
            "inflation",
        }

        risk_keywords = {
            "high_risk": [
                "war",
                "terrorism",
                "collapse",
                "crisis",
                "sanctions",
                "conflict",
            ],
            "medium_risk": [
                "protests",
                "instability",
                "corruption",
                "recession",
                "unrest",
            ],
            "low_risk": [
                "stable",
                "growth",
                "investment",
                "development",
                "cooperation",
            ],
        }

        for mention in country_mentions:
            context = mention["context"].lower()
            country = mention["country"]

            # Analyze context sentiment
            positive_score = sum(1 for word in positive_keywords if word in context)
            negative_score = sum(1 for word in negative_keywords if word in context)

            # Calculate country-specific sentiment
            if positive_score > negative_score:
                country_sentiment = "positive"
                sentiment_strength = min(1.0, positive_score / 3)
            elif negative_score > positive_score:
                country_sentiment = "negative"
                sentiment_strength = min(1.0, negative_score / 3)
            else:
                country_sentiment = "neutral"
                sentiment_strength = 0.5

            # Analyze risk level
            risk_level = "low"
            for level, keywords in risk_keywords.items():
                if any(word in context for word in keywords):
                    if level == "high_risk":
                        risk_level = "high"
                        break
                    elif level == "medium_risk":
                        risk_level = "medium"

            country_sentiments.append(
                {
                    "country": country,
                    "region": mention["region"],
                    "sentiment": country_sentiment,
                    "sentiment_strength": sentiment_strength,
                    "risk_level": risk_level,
                    "context": (
                        mention["context"][:100] + "..."
                        if len(mention["context"]) > 100
                        else mention["context"]
                    ),
                    "positive_signals": positive_score,
                    "negative_signals": negative_score,
                }
            )

        return country_sentiments

    def generate_country_insights(
        self, country_sentiments_list: List[List[Dict]]
    ) -> Dict:
        """
        Generate insights about countries mentioned across all articles.

        Args:
            country_sentiments_list: List of country sentiment lists from all articles

        Returns:
            Dictionary with country insights
        """
        from collections import Counter, defaultdict

        # Aggregate data across all articles
        country_mentions = Counter()
        country_sentiment_scores = defaultdict(list)
        country_risk_levels = defaultdict(list)
        country_regions = {}
        country_contexts = defaultdict(list)

        for sentiments in country_sentiments_list:
            for sentiment in sentiments:
                country = sentiment["country"]
                country_mentions[country] += 1
                country_sentiment_scores[country].append(
                    {
                        "sentiment": sentiment["sentiment"],
                        "strength": sentiment["sentiment_strength"],
                        "positive_signals": sentiment["positive_signals"],
                        "negative_signals": sentiment["negative_signals"],
                    }
                )
                country_risk_levels[country].append(sentiment["risk_level"])
                country_regions[country] = sentiment["region"]
                country_contexts[country].append(sentiment["context"])

        # Calculate aggregate scores
        insights = {
            "most_mentioned": [],
            "highest_risk": [],
            "most_positive": [],
            "most_negative": [],
            "regional_summary": defaultdict(
                lambda: {"positive": 0, "negative": 0, "neutral": 0, "high_risk": 0}
            ),
        }

        for country, count in country_mentions.items():
            if count < 2:  # Skip countries mentioned only once
                continue

            sentiments = country_sentiment_scores[country]
            risks = country_risk_levels[country]
            region = country_regions[country]

            # Calculate average sentiment
            positive_count = sum(1 for s in sentiments if s["sentiment"] == "positive")
            negative_count = sum(1 for s in sentiments if s["sentiment"] == "negative")
            neutral_count = len(sentiments) - positive_count - negative_count

            avg_positive_signals = sum(s["positive_signals"] for s in sentiments) / len(
                sentiments
            )
            avg_negative_signals = sum(s["negative_signals"] for s in sentiments) / len(
                sentiments
            )

            # Risk analysis
            high_risk_count = sum(1 for r in risks if r == "high")
            risk_ratio = high_risk_count / len(risks) if risks else 0

            country_data = {
                "country": country,
                "region": region,
                "mentions": count,
                "positive_mentions": positive_count,
                "negative_mentions": negative_count,
                "neutral_mentions": neutral_count,
                "avg_positive_signals": avg_positive_signals,
                "avg_negative_signals": avg_negative_signals,
                "risk_ratio": risk_ratio,
                "sample_context": (
                    country_contexts[country][0] if country_contexts[country] else ""
                ),
            }

            # Add to appropriate categories
            insights["most_mentioned"].append(country_data)

            if risk_ratio > 0.3:  # High risk threshold
                insights["highest_risk"].append(country_data)

            if positive_count > negative_count and avg_positive_signals > 1:
                insights["most_positive"].append(country_data)

            if negative_count > positive_count and avg_negative_signals > 1:
                insights["most_negative"].append(country_data)

            # Update regional summary
            insights["regional_summary"][region]["positive"] += positive_count
            insights["regional_summary"][region]["negative"] += negative_count
            insights["regional_summary"][region]["neutral"] += neutral_count
            if risk_ratio > 0.5:
                insights["regional_summary"][region]["high_risk"] += 1

        # Sort categories
        insights["most_mentioned"] = sorted(
            insights["most_mentioned"], key=lambda x: x["mentions"], reverse=True
        )[:10]
        insights["highest_risk"] = sorted(
            insights["highest_risk"], key=lambda x: x["risk_ratio"], reverse=True
        )[:5]
        insights["most_positive"] = sorted(
            insights["most_positive"],
            key=lambda x: x["avg_positive_signals"],
            reverse=True,
        )[:5]
        insights["most_negative"] = sorted(
            insights["most_negative"],
            key=lambda x: x["avg_negative_signals"],
            reverse=True,
        )[:5]

        return insights

    def generate_article_id(self, source: str, title: str, published_at: str) -> str:
        """Generate unique article ID."""

        # Clean source domain
        source_clean = source.replace("www.", "").replace(".com", "").replace(".", "_")

        # Create hash from title
        title_hash = hashlib.md5(title.encode()).hexdigest()[:8]

        # Extract date if possible
        date_part = published_at[:10].replace("-", "") if published_at else "00000000"

        return f"{source_clean}_{date_part}_{title_hash}"

    def calculate_text_hash(self, text: str) -> str:
        """Calculate SHA256 hash of text."""
        return f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
