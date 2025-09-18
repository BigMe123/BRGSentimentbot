"""
Market-Style Real-Time Analysis Module
Provides professional trading desk style analysis with economic predictions
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn
import asyncio

from .economic_predictor import EconomicPredictor


@dataclass
class MarketSignal:
    """Trading signal with confidence"""
    asset_class: str  # equity, fx, commodity, rates
    instrument: str  # specific instrument
    direction: str  # long, short, neutral
    magnitude: float  # expected move %
    timeframe: str  # 1d, 1w, 1m
    confidence: float  # 0-1
    rationale: str
    risk_factors: List[str]


@dataclass
class MarketDashboard:
    """Complete market analysis dashboard"""
    timestamp: datetime

    # Macro indicators
    gdp_nowcast: float
    gdp_forecast: Dict[str, float]
    inflation_outlook: Dict[str, float]
    employment_forecast: Dict[str, float]

    # Market predictions
    equity_signals: List[MarketSignal]
    fx_signals: List[MarketSignal]
    commodity_signals: List[MarketSignal]
    rates_outlook: Dict[str, float]

    # Risk metrics
    vix_forecast: float
    geopolitical_risk: float
    correlation_matrix: Dict[str, Dict[str, float]]

    # Trading recommendations
    top_trades: List[MarketSignal]
    hedges: List[MarketSignal]

    # Sentiment metrics
    sentiment_scores: Dict[str, float]
    momentum_indicators: Dict[str, float]

    # News flow
    key_headlines: List[str]
    market_themes: List[str]


class MarketAnalyzer:
    """Professional market analysis system"""

    def __init__(self):
        self.console = Console()
        self.predictor = EconomicPredictor()

        # Market sensitivities
        self.asset_sensitivities = {
            'SPX': {'gdp': 1.5, 'inflation': -0.8, 'rates': -1.2, 'sentiment': 1.8},
            'DXY': {'gdp': 0.5, 'inflation': 0.7, 'rates': 1.5, 'risk': 0.9},
            'Gold': {'inflation': 1.2, 'rates': -0.9, 'risk': 1.5, 'dollar': -1.3},
            'Oil': {'gdp': 0.8, 'supply': -1.5, 'demand': 1.2, 'geopolitics': 0.9},
            'US10Y': {'inflation': 1.3, 'gdp': 0.6, 'fed': 1.8, 'risk': -0.5},
        }

        # Sector rotations
        self.sector_regimes = {
            'growth': ['technology', 'consumer_discretionary', 'communication'],
            'value': ['financials', 'energy', 'materials'],
            'defensive': ['utilities', 'consumer_staples', 'healthcare'],
            'cyclical': ['industrials', 'materials', 'financials']
        }

    async def analyze_markets(self,
                            articles: List[Dict],
                            sentiment_data: Dict[str, float],
                            economic_data: Optional[Dict] = None) -> MarketDashboard:
        """Generate complete market analysis"""

        # Extract themes and headlines
        themes = self._extract_market_themes(articles)
        headlines = self._get_key_headlines(articles)

        # Economic predictions
        gdp_pred = self.predictor.predict_gdp(sentiment_data, economic_data)
        inflation_pred = self.predictor.predict_inflation(sentiment_data)
        employment_pred = self.predictor.predict_employment(sentiment_data)

        # Generate market signals
        equity_signals = self._generate_equity_signals(gdp_pred, sentiment_data)
        fx_signals = self._generate_fx_signals(sentiment_data)
        commodity_signals = self._generate_commodity_signals(sentiment_data)
        rates_outlook = self._predict_rates(inflation_pred, gdp_pred)

        # Risk assessment
        vix_forecast = self._forecast_volatility(sentiment_data)
        geo_risk = self._calculate_geopolitical_risk(articles)
        correlations = self._calculate_correlations(sentiment_data)

        # Trading recommendations
        top_trades = self._identify_top_trades(equity_signals + fx_signals + commodity_signals)
        hedges = self._recommend_hedges(geo_risk, vix_forecast)

        # Momentum indicators
        momentum = self._calculate_momentum(sentiment_data, articles)

        return MarketDashboard(
            timestamp=datetime.now(),
            gdp_nowcast=gdp_pred['nowcast'],
            gdp_forecast={'1Q': gdp_pred['1Q'], '2Q': gdp_pred['2Q']},
            inflation_outlook=inflation_pred,
            employment_forecast=employment_pred,
            equity_signals=equity_signals,
            fx_signals=fx_signals,
            commodity_signals=commodity_signals,
            rates_outlook=rates_outlook,
            vix_forecast=vix_forecast,
            geopolitical_risk=geo_risk,
            correlation_matrix=correlations,
            top_trades=top_trades,
            hedges=hedges,
            sentiment_scores=sentiment_data,
            momentum_indicators=momentum,
            key_headlines=headlines,
            market_themes=themes
        )

    def display_dashboard(self, dashboard: MarketDashboard):
        """Display market dashboard in trading desk style"""

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        # Header
        header_text = f"🏦 MARKET ANALYSIS DASHBOARD | {dashboard.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        layout["header"].update(Panel(header_text, style="bold cyan"))

        # Main area split
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        # Left side - Macro indicators
        macro_table = Table(title="📊 MACRO INDICATORS", show_header=False)
        macro_table.add_column("Metric", style="cyan")
        macro_table.add_column("Value", style="yellow")
        macro_table.add_column("Δ", style="green")

        gdp_color = "green" if dashboard.gdp_nowcast > 2.5 else "red" if dashboard.gdp_nowcast < 1.5 else "yellow"
        macro_table.add_row("GDP Nowcast", f"[{gdp_color}]{dashboard.gdp_nowcast:+.1f}%[/]", "")
        macro_table.add_row("GDP 1Q Fwd", f"{dashboard.gdp_forecast['1Q']:+.1f}%", "")

        inf_1m = dashboard.inflation_outlook.get('1M', 0)
        inf_color = "red" if inf_1m > 3.0 else "green" if inf_1m < 2.0 else "yellow"
        macro_table.add_row("CPI 1M", f"[{inf_color}]{inf_1m:.1f}%[/]", "")

        emp_chg = dashboard.employment_forecast.get('payrolls', 0)
        emp_color = "green" if emp_chg > 150 else "red" if emp_chg < 50 else "yellow"
        macro_table.add_row("Payrolls", f"[{emp_color}]{emp_chg:.0f}K[/]", "")

        macro_table.add_row("", "", "")
        macro_table.add_row("VIX Fcst", f"{dashboard.vix_forecast:.1f}", "")
        macro_table.add_row("Geo Risk", f"{dashboard.geopolitical_risk:.0f}/100", "")

        layout["left"].update(macro_table)

        # Right side - Top trades
        trades_table = Table(title="💹 TOP TRADES", show_header=True)
        trades_table.add_column("Asset", style="cyan")
        trades_table.add_column("Signal", style="bold")
        trades_table.add_column("Target", style="yellow")
        trades_table.add_column("Conf", style="magenta")

        for trade in dashboard.top_trades[:5]:
            signal_style = "green" if trade.direction == "long" else "red" if trade.direction == "short" else "yellow"
            trades_table.add_row(
                trade.instrument,
                f"[{signal_style}]{trade.direction.upper()}[/]",
                f"{trade.magnitude:+.1f}%",
                f"{trade.confidence*100:.0f}%"
            )

        layout["right"].update(trades_table)

        # Footer - Market themes
        themes_text = " | ".join(dashboard.market_themes[:5])
        layout["footer"].update(Panel(f"📰 Themes: {themes_text}", style="dim"))

        self.console.print(layout)

    def display_live_analysis(self, articles_stream):
        """Display live updating analysis"""

        async def update_display():
            with Live(console=self.console, refresh_per_second=1) as live:
                while True:
                    # Get latest articles
                    latest_articles = await articles_stream.get_latest()

                    # Quick sentiment
                    sentiment = self._quick_sentiment(latest_articles)

                    # Update display
                    table = Table(title="🔴 LIVE MARKET SENTIMENT")
                    table.add_column("Metric", style="cyan")
                    table.add_column("Score", style="yellow")
                    table.add_column("Signal", style="bold")

                    for key, value in sentiment.items():
                        signal = "📈" if value > 0.2 else "📉" if value < -0.2 else "➡️"
                        color = "green" if value > 0.2 else "red" if value < -0.2 else "yellow"
                        table.add_row(key.title(), f"[{color}]{value:+.3f}[/]", signal)

                    live.update(table)
                    await asyncio.sleep(5)

        asyncio.run(update_display())

    def _generate_equity_signals(self, gdp: Dict, sentiment: Dict) -> List[MarketSignal]:
        """Generate equity market signals"""
        signals = []

        # S&P 500 signal
        spx_score = (
            gdp['nowcast'] * 0.3 +
            sentiment.get('overall', 0) * 0.4 +
            sentiment.get('corporate', 0) * 0.3
        )

        if spx_score > 1.0:
            direction = "long"
            magnitude = min(5.0, spx_score * 2)
        elif spx_score < -1.0:
            direction = "short"
            magnitude = min(5.0, abs(spx_score) * 2)
        else:
            direction = "neutral"
            magnitude = 0

        signals.append(MarketSignal(
            asset_class="equity",
            instrument="SPX",
            direction=direction,
            magnitude=magnitude,
            timeframe="1m",
            confidence=0.7,
            rationale=f"GDP {gdp['nowcast']:.1f}%, Sentiment {sentiment.get('overall', 0):.2f}",
            risk_factors=["Fed policy", "Geopolitics"]
        ))

        # Sector signals
        for sector, sensitivity in self.asset_sensitivities.items():
            if sector.startswith('Sector_'):
                sector_score = sum(
                    sentiment.get(factor, 0) * weight
                    for factor, weight in sensitivity.items()
                )

                if abs(sector_score) > 0.5:
                    signals.append(MarketSignal(
                        asset_class="equity",
                        instrument=sector,
                        direction="long" if sector_score > 0 else "short",
                        magnitude=abs(sector_score) * 3,
                        timeframe="1w",
                        confidence=0.6,
                        rationale=f"Sector rotation signal",
                        risk_factors=[]
                    ))

        return signals

    def _generate_fx_signals(self, sentiment: Dict) -> List[MarketSignal]:
        """Generate FX signals"""
        signals = []

        # Dollar index
        dxy_score = (
            sentiment.get('us_economy', 0) * 0.4 +
            sentiment.get('fed_hawkish', 0) * 0.3 +
            sentiment.get('risk_off', 0) * 0.3
        )

        if dxy_score > 0.3:
            signals.append(MarketSignal(
                asset_class="fx",
                instrument="DXY",
                direction="long",
                magnitude=abs(dxy_score) * 2,
                timeframe="1w",
                confidence=0.65,
                rationale="USD strength on Fed/Risk",
                risk_factors=["ECB policy", "China"]
            ))

        # EUR/USD
        eur_score = sentiment.get('europe', 0) - sentiment.get('us_economy', 0)
        if abs(eur_score) > 0.3:
            signals.append(MarketSignal(
                asset_class="fx",
                instrument="EURUSD",
                direction="long" if eur_score > 0 else "short",
                magnitude=abs(eur_score) * 1.5,
                timeframe="1w",
                confidence=0.6,
                rationale="Diverging growth",
                risk_factors=["ECB", "Fed"]
            ))

        return signals

    def _generate_commodity_signals(self, sentiment: Dict) -> List[MarketSignal]:
        """Generate commodity signals"""
        signals = []

        # Oil
        oil_score = (
            sentiment.get('energy_demand', 0) * 0.4 +
            sentiment.get('opec', 0) * 0.3 +
            sentiment.get('geopolitics', 0) * 0.3
        )

        if abs(oil_score) > 0.3:
            signals.append(MarketSignal(
                asset_class="commodity",
                instrument="WTI",
                direction="long" if oil_score > 0 else "short",
                magnitude=abs(oil_score) * 5,
                timeframe="1m",
                confidence=0.55,
                rationale="Supply/Demand dynamics",
                risk_factors=["OPEC", "Recession"]
            ))

        # Gold
        gold_score = (
            sentiment.get('risk_off', 0) * 0.4 +
            sentiment.get('inflation', 0) * 0.3 -
            sentiment.get('real_rates', 0) * 0.3
        )

        if abs(gold_score) > 0.3:
            signals.append(MarketSignal(
                asset_class="commodity",
                instrument="Gold",
                direction="long" if gold_score > 0 else "short",
                magnitude=abs(gold_score) * 3,
                timeframe="1m",
                confidence=0.6,
                rationale="Haven/Inflation hedge",
                risk_factors=["USD", "Rates"]
            ))

        return signals

    def _predict_rates(self, inflation: Dict, gdp: Dict) -> Dict[str, float]:
        """Predict interest rates"""
        rates = {}

        # 10Y Treasury
        base_rate = 4.0  # Current 10Y
        inflation_impact = (inflation.get('1M', 2.0) - 2.0) * 0.3
        growth_impact = (gdp['nowcast'] - 2.5) * 0.2

        rates['US10Y'] = base_rate + inflation_impact + growth_impact
        rates['US2Y'] = rates['US10Y'] + 0.5  # Assume some inversion

        # Fed funds
        rates['FedFunds'] = 5.25 + inflation_impact * 0.5

        return rates

    def _forecast_volatility(self, sentiment: Dict) -> float:
        """Forecast VIX"""
        base_vix = 15.0

        # Risk factors
        uncertainty = -sentiment.get('overall', 0) * 5
        geopolitics = sentiment.get('geopolitics', 0) * 3
        policy = sentiment.get('policy_uncertainty', 0) * 4

        vix = base_vix + uncertainty + geopolitics + policy
        return max(10, min(50, vix))  # Cap between 10-50

    def _calculate_geopolitical_risk(self, articles: List[Dict]) -> float:
        """Calculate geopolitical risk score"""
        risk_keywords = ['war', 'conflict', 'sanction', 'military', 'tension', 'crisis']

        risk_score = 0
        for article in articles[:100]:  # Last 100 articles
            text = article.get('text', '').lower()
            for keyword in risk_keywords:
                risk_score += text.count(keyword) * 2

        # Normalize to 0-100
        return min(100, risk_score / 10)

    def _calculate_correlations(self, sentiment: Dict) -> Dict[str, Dict[str, float]]:
        """Calculate asset correlations"""
        # Simplified correlation matrix
        return {
            'SPX': {'DXY': -0.3, 'Gold': -0.2, 'Oil': 0.4, 'VIX': -0.8},
            'DXY': {'SPX': -0.3, 'Gold': -0.5, 'Oil': -0.2, 'VIX': 0.3},
            'Gold': {'SPX': -0.2, 'DXY': -0.5, 'Oil': 0.1, 'VIX': 0.4},
            'Oil': {'SPX': 0.4, 'DXY': -0.2, 'Gold': 0.1, 'VIX': -0.1},
        }

    def _identify_top_trades(self, all_signals: List[MarketSignal]) -> List[MarketSignal]:
        """Identify best risk/reward trades"""
        # Sort by confidence * magnitude
        scored_signals = [
            (signal, signal.confidence * abs(signal.magnitude))
            for signal in all_signals
        ]
        scored_signals.sort(key=lambda x: x[1], reverse=True)

        return [signal for signal, _ in scored_signals[:5]]

    def _recommend_hedges(self, geo_risk: float, vix: float) -> List[MarketSignal]:
        """Recommend portfolio hedges"""
        hedges = []

        if vix > 25:
            hedges.append(MarketSignal(
                asset_class="volatility",
                instrument="VIX_Puts",
                direction="long",
                magnitude=20,
                timeframe="1m",
                confidence=0.7,
                rationale="Tail risk hedge",
                risk_factors=[]
            ))

        if geo_risk > 50:
            hedges.append(MarketSignal(
                asset_class="commodity",
                instrument="Gold",
                direction="long",
                magnitude=5,
                timeframe="3m",
                confidence=0.65,
                rationale="Geopolitical hedge",
                risk_factors=[]
            ))

        return hedges

    def _calculate_momentum(self, sentiment: Dict, articles: List[Dict]) -> Dict[str, float]:
        """Calculate momentum indicators"""
        # Simple momentum based on sentiment change
        momentum = {}

        # Would need historical sentiment to calculate properly
        # For now, use sentiment strength as proxy
        for key, value in sentiment.items():
            momentum[f"{key}_momentum"] = value * 0.5

        return momentum

    def _extract_market_themes(self, articles: List[Dict]) -> List[str]:
        """Extract key market themes"""
        themes = []
        theme_keywords = {
            'Fed Policy': ['fed', 'fomc', 'powell', 'rates'],
            'Inflation': ['inflation', 'cpi', 'prices'],
            'Recession': ['recession', 'slowdown', 'contraction'],
            'Earnings': ['earnings', 'profit', 'revenue'],
            'China': ['china', 'beijing', 'yuan'],
            'Energy': ['oil', 'gas', 'energy', 'opec'],
            'Tech': ['tech', 'ai', 'semiconductor'],
        }

        theme_counts = {theme: 0 for theme in theme_keywords}

        for article in articles[:50]:
            text = article.get('text', '').lower()
            for theme, keywords in theme_keywords.items():
                for keyword in keywords:
                    if keyword in text:
                        theme_counts[theme] += 1
                        break

        # Get top themes
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
        return [theme for theme, count in sorted_themes if count > 0][:5]

    def _get_key_headlines(self, articles: List[Dict]) -> List[str]:
        """Get most important headlines"""
        # Simple: return titles of most recent high-impact articles
        headlines = []
        for article in articles[:10]:
            title = article.get('title', '')
            if title and len(title) > 20:
                headlines.append(title[:100])

        return headlines[:5]

    def _quick_sentiment(self, articles: List[Dict]) -> Dict[str, float]:
        """Quick sentiment calculation for live updates"""
        sentiment = {
            'overall': 0,
            'risk': 0,
            'growth': 0,
            'inflation': 0,
            'policy': 0
        }

        # Simple keyword-based sentiment
        positive_words = ['growth', 'rise', 'gain', 'improve', 'strong']
        negative_words = ['fall', 'decline', 'weak', 'concern', 'risk']

        for article in articles:
            text = article.get('text', '').lower()
            pos_count = sum(1 for word in positive_words if word in text)
            neg_count = sum(1 for word in negative_words if word in text)

            article_sentiment = (pos_count - neg_count) / max(1, pos_count + neg_count)
            sentiment['overall'] += article_sentiment

        # Normalize
        n = len(articles) if articles else 1
        for key in sentiment:
            sentiment[key] /= n

        return sentiment


# Export classes
__all__ = ['MarketAnalyzer', 'MarketDashboard', 'MarketSignal']