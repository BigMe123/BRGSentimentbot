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

    # Countries and regions
    KNOWN_GPES = {
        "United States",
        "USA",
        "US",
        "America",
        "China",
        "Japan",
        "Germany",
        "UK",
        "United Kingdom",
        "Britain",
        "France",
        "Italy",
        "Spain",
        "India",
        "Brazil",
        "Russia",
        "Canada",
        "Australia",
        "South Korea",
        "Mexico",
        "Indonesia",
        "Europe",
        "Asia",
        "Africa",
        "Middle East",
        "Latin America",
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

    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """
        Extract named entities from text.

        Args:
            text: Input text

        Returns:
            List of entity dictionaries with text and type
        """
        entities = []

        # Extract organizations
        for org in self.KNOWN_ORGS:
            if org in text:
                entities.append({"text": org, "type": "ORG"})

        # Extract geopolitical entities
        for gpe in self.KNOWN_GPES:
            if gpe in text:
                entities.append({"text": gpe, "type": "GPE"})

        # Extract potential tickers
        potential_tickers = self.TICKER_PATTERN.findall(text)
        for ticker in potential_tickers:
            # Filter out common words that match pattern
            if len(ticker) >= 2 and ticker not in {"THE", "AND", "FOR", "ARE", "BUT"}:
                entities.append({"text": ticker, "type": "TICKER"})

        # Extract currency pairs
        currency_matches = self.CURRENCY_PATTERN.findall(text)
        for match in currency_matches:
            if "/" in match:
                parts = match.split("/")
                if all(p in self.CURRENCIES for p in parts):
                    entities.append({"text": match, "type": "CURRENCY"})
            elif len(match) == 6:
                # Check if it's a currency pair like EURUSD
                if match[:3] in self.CURRENCIES and match[3:] in self.CURRENCIES:
                    entities.append({"text": match, "type": "CURRENCY"})

        # Deduplicate while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            key = (entity["text"], entity["type"])
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        return unique_entities

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

    def extract_themes(self, text: str, topic: str = None) -> List[str]:
        """
        Extract key themes from text.

        Args:
            text: Input text
            topic: Article topic for context

        Returns:
            List of theme strings
        """
        themes = []
        text_lower = text.lower()

        # Economic themes
        if any(word in text_lower for word in ["inflation", "cpi", "prices", "cost"]):
            themes.append("inflation")

        if any(
            word in text_lower
            for word in ["rate", "interest", "hike", "cut", "fed", "ecb"]
        ):
            themes.append("monetary_policy")

        if any(
            word in text_lower for word in ["recession", "growth", "gdp", "economy"]
        ):
            themes.append("economic_growth")

        # Market themes
        if any(word in text_lower for word in ["stock", "equity", "share", "market"]):
            themes.append("equity_markets")

        if any(word in text_lower for word in ["bond", "yield", "treasury", "gilt"]):
            themes.append("fixed_income")

        if any(
            word in text_lower for word in ["dollar", "euro", "yen", "currency", "fx"]
        ):
            themes.append("fx_markets")

        # Geopolitical themes
        if any(
            word in text_lower for word in ["war", "conflict", "military", "sanctions"]
        ):
            themes.append("geopolitical_risk")

        if any(
            word in text_lower for word in ["election", "vote", "poll", "candidate"]
        ):
            themes.append("political_risk")

        # Energy themes
        if any(
            word in text_lower for word in ["oil", "gas", "energy", "opec", "crude"]
        ):
            themes.append("energy_prices")

        if any(word in text_lower for word in ["renewable", "solar", "wind", "green"]):
            themes.append("green_transition")

        # Tech themes
        if any(
            word in text_lower
            for word in ["ai", "artificial intelligence", "ml", "gpt"]
        ):
            themes.append("ai_disruption")

        if any(
            word in text_lower for word in ["crypto", "bitcoin", "blockchain", "defi"]
        ):
            themes.append("crypto_markets")

        return themes[:5]  # Return top 5 themes

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
