#!/usr/bin/env python3
"""
Real-Time Market-Style Processing System
========================================

Production-grade real-time processing for BSG sentiment analysis with
market-style tick processing, order book metaphors, and streaming analytics.

 Author: BSG Team
 Created: 2025-01-15
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncIterator, Callable, Tuple
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
import logging
import json
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TickType(Enum):
    """Types of market ticks."""
    SENTIMENT = "sentiment"
    ARTICLE = "article"
    SOCIAL = "social"
    ECONOMIC = "economic"
    MARKET = "market"
    ALERT = "alert"


class Priority(Enum):
    """Message priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class MarketTick:
    """Individual market tick/event."""
    timestamp: datetime
    tick_type: TickType
    symbol: str  # Country/region/topic
    data: Dict[str, Any]
    priority: Priority = Priority.MEDIUM
    sequence: int = 0
    source: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.tick_type.value,
            "symbol": self.symbol,
            "data": self.data,
            "priority": self.priority.value,
            "sequence": self.sequence,
            "source": self.source
        }


@dataclass
class OrderBookLevel:
    """Sentiment order book level."""
    price: float  # Sentiment score
    volume: int   # Number of articles/posts
    timestamp: datetime
    sources: List[str] = field(default_factory=list)


class SentimentOrderBook:
    """Market-style order book for sentiment."""
    
    def __init__(self, symbol: str, depth: int = 10):
        self.symbol = symbol
        self.depth = depth
        self.bids: List[OrderBookLevel] = []  # Positive sentiment
        self.asks: List[OrderBookLevel] = []  # Negative sentiment
        self.last_update = datetime.now()
        self.mid_price = 0.0
        self.spread = 0.0
        self.imbalance = 0.0
        
    def add_sentiment(self, score: float, volume: int = 1, source: str = "unknown"):
        """Add sentiment score to order book."""
        level = OrderBookLevel(
            price=score,
            volume=volume,
            timestamp=datetime.now(),
            sources=[source]
        )
        
        if score > 0:
            self.bids.append(level)
            self.bids.sort(key=lambda x: x.price, reverse=True)
            self.bids = self.bids[:self.depth]
        else:
            self.asks.append(level)
            self.asks.sort(key=lambda x: x.price)
            self.asks = self.asks[:self.depth]
            
        self._update_metrics()
        
    def _update_metrics(self):
        """Update order book metrics."""
        if self.bids and self.asks:
            best_bid = self.bids[0].price
            best_ask = abs(self.asks[0].price)
            self.mid_price = (best_bid + best_ask) / 2
            self.spread = best_ask - best_bid
            
            bid_volume = sum(l.volume for l in self.bids)
            ask_volume = sum(l.volume for l in self.asks)
            total_volume = bid_volume + ask_volume
            
            if total_volume > 0:
                self.imbalance = (bid_volume - ask_volume) / total_volume
        
        self.last_update = datetime.now()
        
    def get_snapshot(self) -> Dict[str, Any]:
        """Get order book snapshot."""
        return {
            "symbol": self.symbol,
            "timestamp": self.last_update.isoformat(),
            "mid_price": self.mid_price,
            "spread": self.spread,
            "imbalance": self.imbalance,
            "bids": [(l.price, l.volume) for l in self.bids[:5]],
            "asks": [(l.price, l.volume) for l in self.asks[:5]],
            "bid_depth": len(self.bids),
            "ask_depth": len(self.asks)
        }


class StreamProcessor(ABC):
    """Abstract base for stream processors."""
    
    @abstractmethod
    async def process(self, tick: MarketTick) -> Optional[MarketTick]:
        """Process a tick, optionally returning transformed tick."""
        pass


class SentimentAggregator(StreamProcessor):
    """Aggregates sentiment ticks."""
    
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.buffer: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.aggregates: Dict[str, Dict[str, float]] = {}
        
    async def process(self, tick: MarketTick) -> Optional[MarketTick]:
        """Aggregate sentiment ticks."""
        if tick.tick_type != TickType.SENTIMENT:
            return tick
            
        # Add to buffer
        self.buffer[tick.symbol].append(tick)
        
        # Remove old ticks
        cutoff = datetime.now() - timedelta(seconds=self.window_seconds)
        while self.buffer[tick.symbol] and self.buffer[tick.symbol][0].timestamp < cutoff:
            self.buffer[tick.symbol].popleft()
            
        # Calculate aggregates
        if self.buffer[tick.symbol]:
            scores = [t.data.get('sentiment', 0) for t in self.buffer[tick.symbol]]
            self.aggregates[tick.symbol] = {
                "mean": np.mean(scores),
                "std": np.std(scores),
                "min": np.min(scores),
                "max": np.max(scores),
                "count": len(scores),
                "momentum": scores[-1] - scores[0] if len(scores) > 1 else 0
            }
            
            # Return aggregated tick
            return MarketTick(
                timestamp=datetime.now(),
                tick_type=TickType.SENTIMENT,
                symbol=tick.symbol,
                data={
                    "aggregated": True,
                    **self.aggregates[tick.symbol]
                },
                priority=tick.priority,
                source="aggregator"
            )
            
        return tick


class AlertGenerator(StreamProcessor):
    """Generates alerts from market ticks."""
    
    def __init__(self, thresholds: Dict[str, float]):
        self.thresholds = thresholds
        self.last_alerts: Dict[str, datetime] = {}
        self.cooldown_seconds = 300  # 5 minutes
        
    async def process(self, tick: MarketTick) -> Optional[MarketTick]:
        """Check for alert conditions."""
        alerts = []
        
        # Check sentiment thresholds
        if tick.tick_type == TickType.SENTIMENT:
            sentiment = tick.data.get('sentiment', 0)
            
            if abs(sentiment) > self.thresholds.get('extreme_sentiment', 0.8):
                alerts.append({
                    "type": "extreme_sentiment",
                    "level": "high",
                    "message": f"Extreme sentiment detected: {sentiment:.2f}"
                })
                
            if 'momentum' in tick.data:
                momentum = tick.data['momentum']
                if abs(momentum) > self.thresholds.get('momentum', 0.3):
                    alerts.append({
                        "type": "momentum_shift",
                        "level": "medium",
                        "message": f"Sentiment momentum shift: {momentum:.2f}"
                    })
                    
        # Generate alert tick if needed
        if alerts and self._should_alert(tick.symbol):
            self.last_alerts[tick.symbol] = datetime.now()
            return MarketTick(
                timestamp=datetime.now(),
                tick_type=TickType.ALERT,
                symbol=tick.symbol,
                data={"alerts": alerts},
                priority=Priority.HIGH,
                source="alert_generator"
            )
            
        return None
        
    def _should_alert(self, symbol: str) -> bool:
        """Check if we should generate alert (cooldown)."""
        if symbol not in self.last_alerts:
            return True
        elapsed = (datetime.now() - self.last_alerts[symbol]).seconds
        return elapsed > self.cooldown_seconds


class RealTimeMarketProcessor:
    """Main real-time market-style processor."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.order_books: Dict[str, SentimentOrderBook] = {}
        self.processors: List[StreamProcessor] = []
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.sequence_counter = 0
        self.stats = {
            "ticks_processed": 0,
            "ticks_dropped": 0,
            "alerts_generated": 0,
            "start_time": datetime.now()
        }
        self.running = False
        self.tasks: List[asyncio.Task] = []

        # Initialize processors
        self._setup_processors()

    def _setup_processors(self):
        """Setup stream processors."""
        # Sentiment aggregator
        self.processors.append(
            SentimentAggregator(
                window_seconds=self.config.get('aggregation_window', 60)
            )
        )

        # Alert generator
        self.processors.append(
            AlertGenerator(
                thresholds=self.config.get('alert_thresholds', {
                    'extreme_sentiment': 0.8,
                    'momentum': 0.3,
                    'volume_spike': 5.0
                })
            )
        )

    async def start(self):
        """Start the processor."""
        if self.running:
            logger.warning("Processor already running")
            return

        self.running = True
        logger.info("Starting real-time market processor")

        # Start processing tasks
        self.tasks = [
            asyncio.create_task(self._process_ticks()),
            asyncio.create_task(self._monitor_health()),
            asyncio.create_task(self._publish_snapshots())
        ]

    async def stop(self):
        """Stop the processor."""
        logger.info("Stopping real-time market processor")
        self.running = False

        # Cancel tasks
        for task in self.tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def submit_tick(self, tick: MarketTick) -> bool:
        """Submit tick for processing."""
        if not self.running:
            return False

        try:
            # Add sequence number
            tick.sequence = self.sequence_counter
            self.sequence_counter += 1

            # Try to add to queue
            self.tick_queue.put_nowait(tick)
            return True

        except asyncio.QueueFull:
            self.stats['ticks_dropped'] += 1
            logger.warning(f"Tick queue full, dropping tick: {tick.symbol}")
            return False

    async def _process_ticks(self):
        """Main tick processing loop."""
        logger.info("Tick processor started")

        while self.running:
            try:
                # Get tick from queue
                tick = await asyncio.wait_for(
                    self.tick_queue.get(),
                    timeout=1.0
                )

                # Update order book
                if tick.tick_type == TickType.SENTIMENT:
                    await self._update_order_book(tick)

                # Process through pipeline
                current_tick = tick
                for processor in self.processors:
                    result = await processor.process(current_tick)
                    if result:
                        current_tick = result

                        # Handle alerts
                        if result.tick_type == TickType.ALERT:
                            self.stats['alerts_generated'] += 1
                            await self._handle_alert(result)

                self.stats['ticks_processed'] += 1

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing tick: {e}")

    async def _update_order_book(self, tick: MarketTick):
        """Update sentiment order book."""
        symbol = tick.symbol

        # Create order book if needed
        if symbol not in self.order_books:
            self.order_books[symbol] = SentimentOrderBook(symbol)

        # Add sentiment
        sentiment = tick.data.get('sentiment', 0)
        volume = tick.data.get('volume', 1)
        source = tick.source

        self.order_books[symbol].add_sentiment(sentiment, volume, source)

    async def _handle_alert(self, alert_tick: MarketTick):
        """Handle alert tick."""
        logger.warning(f"ALERT [{alert_tick.symbol}]: {alert_tick.data}")

        # Could send to external systems, notifications, etc.

    async def _monitor_health(self):
        """Monitor system health."""
        logger.info("Health monitor started")

        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Calculate metrics
                uptime = (datetime.now() - self.stats['start_time']).seconds
                tps = self.stats['ticks_processed'] / max(uptime, 1)
                drop_rate = self.stats['ticks_dropped'] / max(
                    self.stats['ticks_processed'] + self.stats['ticks_dropped'], 1
                )

                logger.info(
                    f"Health: TPS={tps:.1f}, Processed={self.stats['ticks_processed']}, "
                    f"Dropped={self.stats['ticks_dropped']} ({drop_rate:.1%}), "
                    f"Alerts={self.stats['alerts_generated']}"
                )

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def _publish_snapshots(self):
        """Publish order book snapshots."""
        logger.info("Snapshot publisher started")

        while self.running:
            try:
                await asyncio.sleep(5)  # Publish every 5 seconds

                snapshots = {}
                for symbol, book in self.order_books.items():
                    snapshots[symbol] = book.get_snapshot()

                # Would normally publish to message queue, WebSocket, etc.
                if snapshots:
                    logger.debug(f"Publishing {len(snapshots)} order book snapshots")

            except Exception as e:
                logger.error(f"Snapshot publisher error: {e}")

    def get_order_book(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get order book snapshot for symbol."""
        if symbol in self.order_books:
            return self.order_books[symbol].get_snapshot()
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics."""
        uptime = (datetime.now() - self.stats['start_time']).seconds
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "tps": self.stats['ticks_processed'] / max(uptime, 1),
            "queue_size": self.tick_queue.qsize(),
            "order_books": len(self.order_books),
            "running": self.running
        }


class MarketDataFeed:
    """Simulated market data feed."""

    def __init__(self, processor: RealTimeMarketProcessor):
        self.processor = processor
        self.running = False
        self.feeds: List[asyncio.Task] = []

    async def start(self):
        """Start data feeds."""
        if self.running:
            return

        self.running = True

        # Start various feeds
        self.feeds = [
            asyncio.create_task(self._sentiment_feed()),
            asyncio.create_task(self._article_feed()),
            asyncio.create_task(self._market_feed())
        ]

    async def stop(self):
        """Stop data feeds."""
        self.running = False

        for feed in self.feeds:
            feed.cancel()

        await asyncio.gather(*self.feeds, return_exceptions=True)

    async def _sentiment_feed(self):
        """Simulate sentiment data feed."""
        symbols = ['USA', 'EUR', 'GBP', 'JPY', 'CNY']

        while self.running:
            try:
                # Generate random sentiment
                symbol = np.random.choice(symbols)
                sentiment = np.random.normal(0, 0.3)
                sentiment = np.clip(sentiment, -1, 1)

                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.SENTIMENT,
                    symbol=symbol,
                    data={
                        'sentiment': sentiment,
                        'confidence': np.random.uniform(0.5, 1.0),
                        'volume': np.random.randint(1, 10)
                    },
                    priority=Priority.MEDIUM,
                    source='sentiment_analyzer'
                )

                await self.processor.submit_tick(tick)

                # Random delay
                await asyncio.sleep(np.random.exponential(0.5))

            except Exception as e:
                logger.error(f"Sentiment feed error: {e}")

    async def _article_feed(self):
        """Simulate article feed."""
        topics = ['economy', 'inflation', 'employment', 'trade', 'market']

        while self.running:
            try:
                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.ARTICLE,
                    symbol=np.random.choice(['USA', 'EUR']),
                    data={
                        'topic': np.random.choice(topics),
                        'source': 'Reuters',
                        'relevance': np.random.uniform(0.3, 1.0)
                    },
                    priority=Priority.LOW,
                    source='news_feed'
                )

                await self.processor.submit_tick(tick)
                await asyncio.sleep(np.random.exponential(2.0))

            except Exception as e:
                logger.error(f"Article feed error: {e}")

    async def _market_feed(self):
        """Simulate market data feed."""
        while self.running:
            try:
                tick = MarketTick(
                    timestamp=datetime.now(),
                    tick_type=TickType.MARKET,
                    symbol='SPX',
                    data={
                        'price': 4500 + np.random.normal(0, 10),
                        'volume': np.random.randint(1000, 10000),
                        'change': np.random.normal(0, 0.5)
                    },
                    priority=Priority.HIGH,
                    source='market_data'
                )

                await self.processor.submit_tick(tick)
                await asyncio.sleep(np.random.exponential(1.0))

            except Exception as e:
                logger.error(f"Market feed error: {e}")


# Factory functions
def create_market_processor(**kwargs) -> RealTimeMarketProcessor:
    """Create configured market processor."""
    config = {
        'aggregation_window': kwargs.get('aggregation_window', 60),
        'alert_thresholds': kwargs.get('alert_thresholds', {
            'extreme_sentiment': 0.8,
            'momentum': 0.3,
            'volume_spike': 5.0
        }),
        **kwargs
    }
    return RealTimeMarketProcessor(config)


def create_market_feed(processor: RealTimeMarketProcessor) -> MarketDataFeed:
    """Create market data feed."""
    return MarketDataFeed(processor)