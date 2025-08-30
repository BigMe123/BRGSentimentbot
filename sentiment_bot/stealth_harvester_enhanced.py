#!/usr/bin/env python3
"""
🛡️ Enhanced Military-Grade Stealth Harvester
Advanced anti-detection source discovery with persistent browser contexts, 
concurrent processing, SQLite storage, and dynamic bypass strategies.
"""

import sys
import os
import re
import json
import time
import hashlib
import argparse
import random
import asyncio
import sqlite3
import yaml
from typing import List, Dict, Set, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# TLS fingerprint evasion - mimics real browser TLS handshakes
from curl_cffi import requests as curl_requests

# Browser automation with anti-detection patches
try:
    from playwright_stealth import stealth_async
except ImportError:
    # Handle different library versions
    try:
        from playwright_stealth import stealth

        stealth_async = stealth  # Use sync version as fallback
    except ImportError:
        stealth_async = None  # Will use manual patches


def eprint(*args):
    """Write to stderr in a compatible way."""
    try:
        msg = " ".join(map(str, args))
    except Exception:
        msg = " ".join(["<unprintable>" for _ in args])
    sys.stderr.write(msg + os.linesep)


@dataclass
class ProxyConfig:
    """Manages proxy rotation to avoid IP-based blocking."""

    proxies: List[str] = field(default_factory=list)
    current_index: int = 0
    failed_proxies: Set[str] = field(default_factory=set)


@dataclass
class BrowserProfile:
    """Realistic browser fingerprint for rotation."""

    user_agent: str
    viewport: Tuple[int, int]
    headers: Dict[str, str]
    timezone: str
    language: str
    platform: str
    locale: str
    tls_impersonate: str  # TLS fingerprint profile name
    geolocation: Optional[Dict[str, float]] = None  # Lat/long for spoofing
    hardware_concurrency: int = 8  # CPU cores
    device_memory: int = 8  # RAM in GB
    screen_resolution: Tuple[int, int] = (1920, 1080)


@dataclass
class SourceRecord:
    """Metadata for a discovered news source."""

    domain: str
    name: str = ""
    topics: List[str] = field(default_factory=list)
    priority: float = 0.5
    policy: str = "allow"
    region: str = "unknown"
    rss_feeds: List[str] = field(default_factory=list)
    language: str = "en"
    discovered_at: Optional[float] = None
    protection_level: str = "none"
    bypass_method: str = ""
    success_rate: float = 0.0
    last_accessed: Optional[float] = None
    fetch_strategy: str = "requests"  # requests, browser, or hybrid


class StealthDatabase:
    """SQLite database for efficient storage and querying."""

    def __init__(self, db_path: str = ".stealth_harvest.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Create database tables if they don't exist."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                domain TEXT PRIMARY KEY,
                name TEXT,
                topics TEXT,
                priority REAL,
                policy TEXT,
                region TEXT,
                rss_feeds TEXT,
                language TEXT,
                discovered_at REAL,
                protection_level TEXT,
                bypass_method TEXT,
                success_rate REAL,
                last_accessed REAL,
                fetch_strategy TEXT
            );
            
            CREATE TABLE IF NOT EXISTS request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                timestamp REAL,
                status_code INTEGER,
                success BOOLEAN,
                protection_detected TEXT,
                bypass_used TEXT
            );
            
            CREATE TABLE IF NOT EXISTS cookies (
                domain TEXT PRIMARY KEY,
                cookies TEXT,
                updated_at REAL
            );
            
            CREATE INDEX IF NOT EXISTS idx_sources_protection ON sources(protection_level);
            CREATE INDEX IF NOT EXISTS idx_sources_priority ON sources(priority);
            CREATE INDEX IF NOT EXISTS idx_history_timestamp ON request_history(timestamp);
        """
        )
        self.conn.commit()

    def save_source(self, record: SourceRecord):
        """Save or update a source record."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                record.domain,
                record.name,
                json.dumps(record.topics),
                record.priority,
                record.policy,
                record.region,
                json.dumps(record.rss_feeds),
                record.language,
                record.discovered_at,
                record.protection_level,
                record.bypass_method,
                record.success_rate,
                record.last_accessed,
                record.fetch_strategy,
            ),
        )
        self.conn.commit()

    def get_source(self, domain: str) -> Optional[SourceRecord]:
        """Retrieve a source record by domain."""
        cursor = self.conn.execute("SELECT * FROM sources WHERE domain = ?", (domain,))
        row = cursor.fetchone()
        if row:
            return SourceRecord(
                domain=row["domain"],
                name=row["name"],
                topics=json.loads(row["topics"]),
                priority=row["priority"],
                policy=row["policy"],
                region=row["region"],
                rss_feeds=json.loads(row["rss_feeds"]),
                language=row["language"],
                discovered_at=row["discovered_at"],
                protection_level=row["protection_level"],
                bypass_method=row["bypass_method"],
                success_rate=row["success_rate"],
                last_accessed=row["last_accessed"],
                fetch_strategy=row["fetch_strategy"],
            )
        return None

    def get_all_sources(self) -> List[SourceRecord]:
        """Get all discovered sources."""
        cursor = self.conn.execute("SELECT * FROM sources ORDER BY priority DESC")
        sources = []
        for row in cursor:
            sources.append(
                SourceRecord(
                    domain=row["domain"],
                    name=row["name"],
                    topics=json.loads(row["topics"]),
                    priority=row["priority"],
                    policy=row["policy"],
                    region=row["region"],
                    rss_feeds=json.loads(row["rss_feeds"]),
                    language=row["language"],
                    discovered_at=row["discovered_at"],
                    protection_level=row["protection_level"],
                    bypass_method=row["bypass_method"],
                    success_rate=row["success_rate"],
                    last_accessed=row["last_accessed"],
                    fetch_strategy=row["fetch_strategy"],
                )
            )
        return sources

    def log_request(
        self,
        url: str,
        status_code: int,
        success: bool,
        protection: str = "",
        bypass: str = "",
    ):
        """Log request history for analysis."""
        self.conn.execute(
            """
            INSERT INTO request_history (url, timestamp, status_code, success, protection_detected, bypass_used)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (url, time.time(), status_code, success, protection, bypass),
        )
        self.conn.commit()

    def save_cookies(self, domain: str, cookies: List[Dict]):
        """Save cookies for a domain."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO cookies VALUES (?, ?, ?)
        """,
            (domain, json.dumps(cookies), time.time()),
        )
        self.conn.commit()

    def get_cookies(self, domain: str) -> Optional[List[Dict]]:
        """Get cookies for a domain."""
        cursor = self.conn.execute(
            "SELECT cookies FROM cookies WHERE domain = ?", (domain,)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row["cookies"])
        return None

    def close(self):
        """Close database connection."""
        self.conn.close()


class EnhancedStealthHarvester:
    """🛡️ Enhanced military-grade stealth harvester with advanced features."""

    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        self.config = self._load_config(config_path)

        # Database
        self.db = StealthDatabase(
            self.config.get("database", {}).get("path", ".stealth_harvest.db")
        )

        # Browser management
        self.browser = None  # Persistent browser instance
        self.contexts: Dict[str, Any] = {}  # Browser contexts per domain
        self.playwright = None

        # Profiles and fingerprints
        self.browser_profiles = self._generate_browser_profiles()
        self.current_profile = random.choice(self.browser_profiles)

        # Proxy management
        self.proxy_config = ProxyConfig(proxies=self.config.get("proxies", []))

        # Request tracking
        self.request_count = 0
        self.last_request_time = 0
        self.request_history: List[Tuple[str, float]] = []

        # Bypass strategies
        self.bypass_strategies = {
            "cf_bypass": self._handle_cloudflare,
            "captcha_solver": self._handle_captcha,
            "browser_js": self._escalate_to_browser,
            "rotate_ip": self._rotate_and_retry,
            "rotate_profile": self._rotate_profile_and_retry,
            "stealth_headers": self._enhance_stealth_headers,
            "advanced_solver": self._handle_advanced_protection,
            "px_bypass": self._handle_perimeterx,
            "akamai_bypass": self._handle_akamai,
        }

        # CAPTCHA solver configuration
        self.captcha_config = self.config.get("captcha", {})
        self.captcha_solver = self._init_captcha_solver()

        # Worker pool settings
        self.max_workers = self.config.get("performance", {}).get("max_workers", 5)
        self.worker_queue: Optional[asyncio.Queue] = None

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file or use defaults."""
        default_config = {
            "database": {"path": ".stealth_harvest.db"},
            "performance": {"max_workers": 5, "base_delay": 3.0, "jitter": 1.5},
            "browser": {
                "headless": True,
                "persistent_contexts": True,
                "enable_webrtc_leak_prevention": True,
            },
            "captcha": {
                "service": "twocaptcha",
                "api_key": os.environ.get("CAPTCHA_API_KEY", ""),
            },
            "proxies": [],
            "geolocation": {
                "enabled": True,
                "locations": [
                    {"latitude": 40.7128, "longitude": -74.0060},  # NYC
                    {"latitude": 51.5074, "longitude": -0.1278},  # London
                    {"latitude": 35.6762, "longitude": 139.6503},  # Tokyo
                ],
            },
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded_config = yaml.safe_load(f)
                    # Merge with defaults
                    for key, value in loaded_config.items():
                        if isinstance(value, dict) and key in default_config:
                            default_config[key].update(value)
                        else:
                            default_config[key] = value
            except Exception as e:
                eprint(f"Warning: Could not load config from {config_path}: {e}")

        return default_config

    def _generate_browser_profiles(self) -> List[BrowserProfile]:
        """Create diverse browser fingerprints with TLS mapping."""
        profiles = []

        # Geolocation options
        geolocations = self.config.get("geolocation", {}).get("locations", [])

        # Chrome profiles with matching TLS fingerprints
        chrome_configs = [
            ("131.0.6778.205", "chrome120"),
            ("130.0.6723.118", "chrome116"),
            ("129.0.6668.89", "chrome110"),
        ]

        for version, tls_profile in chrome_configs:
            geo = random.choice(geolocations) if geolocations else None
            profiles.append(
                BrowserProfile(
                    user_agent=f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36",
                    viewport=(1920, 1080),
                    headers={
                        "sec-ch-ua": f'"Google Chrome";v="{version.split(".")[0]}", "Chromium";v="{version.split(".")[0]}", "Not_A Brand";v="99"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                    },
                    timezone="America/New_York",
                    language="en-US",
                    platform="Win32",
                    locale="en-US",
                    tls_impersonate=tls_profile,
                    geolocation=geo,
                    hardware_concurrency=random.choice([4, 8, 16]),
                    device_memory=random.choice([4, 8, 16]),
                    screen_resolution=(1920, 1080),
                )
            )

        # Firefox profiles
        firefox_configs = [
            ("133.0", "firefox"),
            ("132.0.2", "firefox"),
        ]

        for version, tls_profile in firefox_configs:
            geo = random.choice(geolocations) if geolocations else None
            profiles.append(
                BrowserProfile(
                    user_agent=f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}) Gecko/20100101 Firefox/{version}",
                    viewport=(1366, 768),
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Upgrade-Insecure-Requests": "1",
                    },
                    timezone="Europe/London",
                    language="en-GB",
                    platform="Win32",
                    locale="en-GB",
                    tls_impersonate=tls_profile,
                    geolocation=geo,
                    hardware_concurrency=random.choice([4, 8]),
                    device_memory=random.choice([4, 8, 16]),
                    screen_resolution=(1366, 768),
                )
            )

        # Safari profiles
        safari_configs = [
            ("18.2", "safari17_0"),
            ("18.1", "safari17_0"),
        ]

        for version, tls_profile in safari_configs:
            geo = random.choice(geolocations) if geolocations else None
            profiles.append(
                BrowserProfile(
                    user_agent=f"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{version} Safari/605.1.15",
                    viewport=(1440, 900),
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                    },
                    timezone="America/Los_Angeles",
                    language="en-US",
                    platform="MacIntel",
                    locale="en-US",
                    tls_impersonate=tls_profile,
                    geolocation=geo,
                    hardware_concurrency=random.choice([8, 16]),
                    device_memory=random.choice([8, 16, 32]),
                    screen_resolution=(2560, 1440),
                )
            )

        return profiles

    def _init_captcha_solver(self):
        """Initialize CAPTCHA solving service."""
        if self.captcha_config.get("api_key"):
            service = self.captcha_config.get("service", "twocaptcha")
            if service == "twocaptcha":
                try:
                    from twocaptcha import TwoCaptcha

                    return TwoCaptcha(self.captcha_config["api_key"])
                except ImportError:
                    eprint(
                        "⚠️ TwoCaptcha library not installed. Install with: pip install 2captcha-python"
                    )
        return None

    async def _init_playwright(self):
        """Initialize Playwright with persistent browser."""
        try:
            from playwright.async_api import async_playwright

            if not self.playwright:
                self.playwright = await async_playwright().start()

                # Launch persistent browser instance
                if not self.browser and self.config.get("browser", {}).get(
                    "persistent_contexts", True
                ):
                    launch_args = [
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-extensions",
                        "--disable-plugins",
                    ]

                    # Add WebRTC leak prevention
                    if self.config.get("browser", {}).get(
                        "enable_webrtc_leak_prevention", True
                    ):
                        launch_args.append(
                            "--disable-features=WebRtcHideLocalIpsWithMdns"
                        )

                    self.browser = await self.playwright.chromium.launch(
                        headless=self.config.get("browser", {}).get("headless", True),
                        args=launch_args,
                    )
                    eprint("🚀 Persistent browser launched")
        except ImportError:
            eprint("⚠️ Playwright not available - falling back to requests only")
            self.playwright = None

    async def _get_or_create_context(self, domain: str):
        """Get existing browser context for domain or create new one."""
        if domain not in self.contexts:
            proxy = self._rotate_proxy()
            proxy_dict = {"server": proxy} if proxy else None

            # Get geolocation for current profile
            geo = self.current_profile.geolocation

            context_options = {
                "viewport": {
                    "width": self.current_profile.viewport[0],
                    "height": self.current_profile.viewport[1],
                },
                "user_agent": self.current_profile.user_agent,
                "extra_http_headers": self._build_headers(),
                "proxy": proxy_dict,
                "locale": self.current_profile.locale,
                "timezone_id": self.current_profile.timezone,
            }

            # Add geolocation if available
            if geo and self.config.get("geolocation", {}).get("enabled", True):
                context_options["geolocation"] = geo
                context_options["permissions"] = ["geolocation"]

            context = await self.browser.new_context(**context_options)

            # Load saved cookies
            saved_cookies = self.db.get_cookies(domain)
            if saved_cookies:
                await context.add_cookies(saved_cookies)
                eprint(f"🍪 Loaded {len(saved_cookies)} cookies for {domain}")

            self.contexts[domain] = context
            eprint(f"📂 Created new context for {domain}")

        return self.contexts[domain]

    def _rotate_proxy(self) -> Optional[str]:
        """Cycle through proxy servers."""
        if not self.proxy_config.proxies:
            return None

        available_proxies = [
            p
            for p in self.proxy_config.proxies
            if p not in self.proxy_config.failed_proxies
        ]

        if not available_proxies:
            self.proxy_config.failed_proxies.clear()
            available_proxies = self.proxy_config.proxies

        proxy = available_proxies[
            self.proxy_config.current_index % len(available_proxies)
        ]
        self.proxy_config.current_index += 1

        return proxy

    def _rotate_profile(self):
        """Switch browser fingerprint."""
        self.current_profile = random.choice(self.browser_profiles)
        eprint(
            f"🔄 Rotated to profile with TLS: {self.current_profile.tls_impersonate}"
        )

    async def _smart_delay(
        self, base_delay: Optional[float] = None, jitter: Optional[float] = None
    ):
        """Human-like timing with circadian patterns."""
        if base_delay is None:
            base_delay = self.config.get("performance", {}).get("base_delay", 3.0)
        if jitter is None:
            jitter = self.config.get("performance", {}).get("jitter", 1.5)

        self.request_count += 1

        # Circadian rhythm adjustment
        hour = datetime.now().hour
        if 0 <= hour < 6:  # Night
            base_delay *= 2.5
        elif 6 <= hour < 9:  # Morning
            base_delay *= 1.2
        elif 9 <= hour < 17:  # Work hours
            base_delay *= 0.8
        elif 17 <= hour < 22:  # Evening
            base_delay *= 1.0
        else:  # Late evening
            base_delay *= 1.5

        # Progressive backoff
        if self.request_count > 15:
            backoff_multiplier = min(5.0, self.request_count / 8)
            base_delay *= backoff_multiplier

        # Gaussian distribution
        delay = base_delay + random.gauss(0, jitter)
        delay = max(1.0, delay)

        time_since_last = time.time() - self.last_request_time
        if time_since_last < delay:
            await asyncio.sleep(delay - time_since_last)

        self.last_request_time = time.time()

        # Random breaks
        break_chance = random.random()
        if break_chance < 0.05:  # 5% long break
            eprint("☕ Taking extended break...")
            await asyncio.sleep(random.uniform(30, 90))
        elif break_chance < 0.15:  # 10% medium break
            eprint("⏸️  Taking short break...")
            await asyncio.sleep(random.uniform(10, 25))

    async def _tiered_fetch(self, url: str, retries: int = 3) -> Optional[str]:
        """Tiered fetch strategy: try lightweight first, escalate if needed."""
        domain = urlparse(url).hostname

        # Check if we have a preferred strategy for this domain
        existing_record = self.db.get_source(domain)
        if existing_record and existing_record.fetch_strategy == "browser":
            # Skip straight to browser if we know it's needed
            return await self._browser_get(url)

        # Try lightweight requests first
        for attempt in range(retries):
            try:
                content = await self._requests_get(url)
                if content:
                    # Detect if we need browser for future requests
                    protection_level, bypass_method = self._detect_protection_level(
                        url, content, 200
                    )
                    if protection_level in ["advanced", "fortress"]:
                        # Remember to use browser next time
                        if existing_record:
                            existing_record.fetch_strategy = "browser"
                            self.db.save_source(existing_record)
                    return content
            except Exception as e:
                eprint(f"Requests failed for {url}: {e}")

            # Escalate to browser if requests failed
            if attempt == 0:
                eprint(f"🚀 Escalating to browser for {url}")
                content = await self._browser_get(url)
                if content:
                    # Remember to use browser next time
                    if existing_record:
                        existing_record.fetch_strategy = "browser"
                        self.db.save_source(existing_record)
                    return content

            if attempt < retries - 1:
                await asyncio.sleep(random.uniform(5, 15))
                self._rotate_profile()

        return None

    async def _browser_get(self, url: str) -> Optional[str]:
        """Fetch using persistent browser context with enhanced stealth."""
        await self._init_playwright()
        if not self.browser:
            return None

        domain = urlparse(url).hostname

        try:
            context = await self._get_or_create_context(domain)
            page = await context.new_page()

            # Apply stealth patches
            if stealth_async:
                await stealth_async(page)
            else:
                await self._apply_enhanced_stealth_patches(page)

            # Navigate
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Simulate human behavior
            await self._simulate_human_behavior(page)

            # Check for protection and handle if needed
            content = await page.content()
            protection_level, bypass_method = self._detect_protection_level(
                url, content, 200
            )

            if bypass_method and bypass_method in self.bypass_strategies:
                eprint(f"🔓 Applying bypass strategy: {bypass_method}")
                success = await self.bypass_strategies[bypass_method](page, url)
                if success:
                    content = await page.content()

            # Save cookies
            cookies = await context.cookies()
            self.db.save_cookies(domain, cookies)

            # Close page but keep context
            await page.close()

            return content

        except Exception as e:
            eprint(f"Browser request failed for {url}: {e}")
            return None

    async def _apply_enhanced_stealth_patches(self, page):
        """Apply comprehensive stealth patches."""
        await page.add_init_script(
            f"""
            // Override webdriver
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined
            }});
            
            // Chrome object
            window.chrome = {{
                runtime: {{}},
                loadTimes: function() {{}},
                csi: function() {{}}
            }};
            
            // Hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {self.current_profile.hardware_concurrency}
            }});
            
            // Device memory
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {self.current_profile.device_memory}
            }});
            
            // Screen resolution
            Object.defineProperty(screen, 'width', {{ get: () => {self.current_profile.screen_resolution[0]} }});
            Object.defineProperty(screen, 'height', {{ get: () => {self.current_profile.screen_resolution[1]} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {self.current_profile.screen_resolution[0]} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {self.current_profile.screen_resolution[1] - 40} }});
            
            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({{ state: Notification.permission }}) :
                    originalQuery(parameters)
            );
            
            // Plugins
            Object.defineProperty(navigator, 'plugins', {{
                get: () => [1, 2, 3, 4, 5]
            }});
            
            // Languages
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{self.current_profile.language}', 'en']
            }});
            
            // Canvas fingerprint noise
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {{
                const context = this.getContext('2d');
                if (context) {{
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {{
                        imageData.data[i] = imageData.data[i] ^ 1;
                    }}
                    context.putImageData(imageData, 0, 0);
                }}
                return originalToDataURL.apply(this, arguments);
            }};
            
            // WebGL fingerprint
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) {{
                    return 'Intel Inc.';
                }}
                if (parameter === 37446) {{
                    return 'Intel Iris OpenGL Engine';
                }}
                return getParameter(parameter);
            }};
            
            // Battery API
            if (navigator.getBattery) {{
                navigator.getBattery = () => Promise.resolve({{
                    charging: true,
                    chargingTime: 0,
                    dischargingTime: Infinity,
                    level: 1
                }});
            }}
        """
        )

    async def _requests_get(self, url: str) -> Optional[str]:
        """HTTP request with TLS fingerprint matching."""
        headers = self._build_headers()
        proxy = self._rotate_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None

        try:
            # Use TLS fingerprint from current profile
            impersonate_browser = self.current_profile.tls_impersonate
            response = curl_requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=20,
                impersonate=impersonate_browser,
            )

            if response.status_code == 200:
                self.db.log_request(url, 200, True)
                return response.text
            else:
                self.db.log_request(url, response.status_code, False)
                eprint(f"HTTP {response.status_code} for {url}")
                return None

        except Exception as e:
            if proxy:
                self.proxy_config.failed_proxies.add(proxy)
            self.db.log_request(url, 0, False)
            eprint(f"Request failed for {url}: {e}")
            return None

    def _build_headers(self) -> Dict[str, str]:
        """Build realistic HTTP headers."""
        base_headers = {
            "User-Agent": self.current_profile.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": f"{self.current_profile.language},en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        base_headers.update(self.current_profile.headers)

        if random.random() < 0.3:
            referers = [
                "https://www.google.com/",
                "https://www.bing.com/",
                "https://search.yahoo.com/",
            ]
            base_headers["Referer"] = random.choice(referers)

        return base_headers

    async def _simulate_human_behavior(self, page):
        """Simulate realistic human browsing."""
        try:
            viewport_width = self.current_profile.viewport[0]
            viewport_height = self.current_profile.viewport[1]

            # Random scroll pattern
            for _ in range(random.randint(1, 3)):
                scroll_distance = random.randint(100, 500)
                await page.evaluate(
                    f"""
                    window.scrollBy({{
                        top: {scroll_distance},
                        behavior: 'smooth'
                    }});
                """
                )
                await asyncio.sleep(random.uniform(0.5, 2.0))

            # Random mouse movements
            for _ in range(random.randint(2, 4)):
                x = random.randint(50, viewport_width - 50)
                y = random.randint(50, min(viewport_height - 50, 800))
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.2, 0.8))

        except Exception as e:
            eprint(f"Behavior simulation failed: {e}")

    def _detect_protection_level(
        self, url: str, content: Optional[str], response_code: int
    ) -> Tuple[str, str]:
        """Identify anti-bot systems and suggest bypass strategy."""
        if not content:
            if response_code == 403:
                return "fortress", "browser_with_solver"
            elif response_code == 404:
                return "advanced", "browser_stealth"
            else:
                return "basic", "rotate_profile"

        content_lower = content.lower()

        protection_indicators = [
            ("cloudflare", "advanced", "cf_bypass"),
            ("recaptcha", "advanced", "captcha_solver"),
            ("hcaptcha", "advanced", "captcha_solver"),
            ("please enable javascript", "advanced", "browser_js"),
            ("access denied", "basic", "rotate_ip"),
            ("blocked", "basic", "rotate_profile"),
            ("datadome", "fortress", "advanced_solver"),
            ("perimeterx", "fortress", "px_bypass"),
            ("akamai", "advanced", "akamai_bypass"),
        ]

        for indicator, level, method in protection_indicators:
            if indicator in content_lower:
                return level, method

        return "none", ""

    # Bypass strategy methods
    async def _handle_cloudflare(self, page, url: str) -> bool:
        """Handle Cloudflare challenges."""
        eprint("🧠 Handling Cloudflare challenge...")
        try:
            # Wait for challenge to resolve
            await asyncio.sleep(10)
            # Check if redirected
            if page.url != url:
                return True
        except:
            pass
        return False

    async def _handle_captcha(self, page, url: str) -> bool:
        """Solve CAPTCHA challenges."""
        if not self.captcha_solver:
            eprint("⚠️ No CAPTCHA solver configured")
            return False

        try:
            # Find reCAPTCHA site key
            site_key = await page.evaluate(
                """
                () => {
                    const recap = document.querySelector('[data-sitekey]');
                    return recap ? recap.getAttribute('data-sitekey') : null;
                }
            """
            )

            if site_key:
                eprint(f"📝 Solving CAPTCHA...")
                result = self.captcha_solver.recaptcha(sitekey=site_key, url=page.url)
                if result and "code" in result:
                    await page.evaluate(
                        f"""
                        document.getElementById('g-recaptcha-response').innerHTML = '{result['code']}';
                    """
                    )
                    # Submit form
                    await page.evaluate("document.querySelector('form').submit();")
                    await asyncio.sleep(3)
                    return True
        except Exception as e:
            eprint(f"CAPTCHA solving failed: {e}")

        return False

    async def _escalate_to_browser(self, page, url: str) -> bool:
        """Already in browser, just return success."""
        return True

    async def _rotate_and_retry(self, page, url: str) -> bool:
        """Rotate IP and retry."""
        self._rotate_proxy()
        return True

    async def _rotate_profile_and_retry(self, page, url: str) -> bool:
        """Rotate browser profile."""
        self._rotate_profile()
        return True

    async def _enhance_stealth_headers(self, page, url: str) -> bool:
        """Enhance stealth headers."""
        return True

    async def _handle_advanced_protection(self, page, url: str) -> bool:
        """Handle advanced protection systems."""
        eprint("🔐 Advanced protection detected - applying countermeasures")
        await asyncio.sleep(random.uniform(5, 10))
        return True

    async def _handle_perimeterx(self, page, url: str) -> bool:
        """Handle PerimeterX protection."""
        eprint("🛡️ PerimeterX detected")
        # Implementation would go here
        return False

    async def _handle_akamai(self, page, url: str) -> bool:
        """Handle Akamai protection."""
        eprint("🛡️ Akamai detected")
        # Implementation would go here
        return False

    # Worker pool for concurrent processing
    async def _worker(self, name: str, queue: asyncio.Queue):
        """Worker coroutine for processing URLs."""
        while True:
            try:
                url = await queue.get()
                eprint(f"👷 Worker {name} processing {url}")

                await self._smart_delay()

                # Process URL
                domain = self._normalize_domain(url)
                await self.discover_from_domain(domain)

                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                eprint(f"Worker {name} error: {e}")
                queue.task_done()

    async def run_concurrent_harvest(self, domains: List[str]):
        """Run harvesting with concurrent workers."""
        queue = asyncio.Queue()

        # Add all domains to queue
        for domain in domains:
            await queue.put(domain)

        # Create workers
        workers = []
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}", queue))
            workers.append(worker)

        # Wait for all tasks to complete
        await queue.join()

        # Cancel workers
        for worker in workers:
            worker.cancel()

        await asyncio.gather(*workers, return_exceptions=True)

    async def discover_from_domain(self, domain: str) -> Optional[SourceRecord]:
        """Discover source with tiered fetch strategy."""
        domain = self._normalize_domain(domain)

        # Check if already known
        existing = self.db.get_source(domain)
        if existing:
            eprint(f"Already known: {domain}")
            return existing

        eprint(f"🕵️ Discovering: {domain}")

        url = f"https://{domain}"
        content = await self._tiered_fetch(url)

        if not content:
            eprint(f"💀 Failed to fetch {domain}")
            self.db.log_request(url, 0, False)
            return None

        protection_level, bypass_method = self._detect_protection_level(
            url, content, 200
        )
        eprint(f"🛡️ Protection: {protection_level}, Bypass: {bypass_method}")

        # Extract metadata
        name = self._extract_title(content) or domain
        rss_feeds = await self._find_rss_feeds(content, domain)
        region = self._infer_region(domain)
        topics = self._infer_topics(name + " " + self._extract_description(content))

        record = SourceRecord(
            domain=domain,
            name=name,
            topics=topics,
            priority=self._calculate_priority(domain, topics, protection_level),
            region=region,
            rss_feeds=rss_feeds,
            protection_level=protection_level,
            bypass_method=bypass_method,
            discovered_at=time.time(),
            last_accessed=time.time(),
            fetch_strategy=(
                "browser"
                if protection_level in ["advanced", "fortress"]
                else "requests"
            ),
        )

        self.db.save_source(record)
        self.db.log_request(url, 200, True, protection_level, bypass_method)

        eprint(f"✅ Discovered: {domain} -> {len(rss_feeds)} feeds")
        return record

    async def _find_rss_feeds(self, html: str, domain: str) -> List[str]:
        """Find RSS feed URLs."""
        feeds = []

        # Look for RSS link tags
        rss_pattern = r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*href=["\']([^"\']*)["\']'
        for match in re.finditer(rss_pattern, html, re.IGNORECASE):
            href = match.group(1)
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = f"https://{domain}{href}"
            feeds.append(href)

        # Try common RSS paths
        common_paths = ["/rss", "/feed", "/rss.xml", "/feed.xml", "/atom.xml"]
        for path in common_paths:
            url = f"https://{domain}{path}"
            if await self._is_valid_rss(url):
                feeds.append(url)

        return list(set(feeds))

    async def _is_valid_rss(self, url: str) -> bool:
        """Validate RSS feed."""
        try:
            content = await self._tiered_fetch(url)
            if not content or len(content) < 100:
                return False

            rss_indicators = ["<rss", "<feed", "</rss>", "</feed>", "<channel", "<item"]
            content_lower = content.lower()

            return any(indicator in content_lower for indicator in rss_indicators)

        except:
            return False

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain format."""
        domain = domain.lower().strip()
        domain = re.sub(r"^https?://", "", domain)
        domain = re.sub(r"^www\.", "", domain)
        domain = domain.rstrip("/")
        return domain

    def _extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            return title[:100]
        return ""

    def _extract_description(self, html: str) -> str:
        """Extract description from HTML."""
        match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:200]
        return ""

    def _infer_region(self, domain: str) -> str:
        """Infer region from domain."""
        if domain.endswith(".uk") or domain.endswith(".fr") or domain.endswith(".de"):
            return "europe"
        elif domain.endswith(".au"):
            return "asia"
        else:
            return "americas"

    def _infer_topics(self, text: str) -> List[str]:
        """Infer topics from text."""
        text = text.lower()
        topics = []

        topic_keywords = {
            "economy": ["economic", "finance", "business", "market", "trade"],
            "politics": ["politic", "government", "policy", "election"],
            "security": ["security", "defense", "military", "conflict"],
            "tech": ["technology", "tech", "digital", "ai", "software"],
            "diplomacy": ["foreign", "international", "diplomatic"],
        }

        for topic, keywords in topic_keywords.items():
            if any(keyword in text for keyword in keywords):
                topics.append(topic)

        if not topics:
            topics.append("general")

        return topics

    def _calculate_priority(
        self, domain: str, topics: List[str], protection_level: str
    ) -> float:
        """Calculate source priority."""
        base = 0.5

        # Trusted sources
        if any(x in domain for x in ["gov", "edu", "reuters", "bbc", "economist"]):
            base += 0.3

        # Important topics
        if "economy" in topics or "politics" in topics:
            base += 0.1

        # Protection level bonus
        protection_bonus = {
            "none": 0.0,
            "basic": 0.05,
            "advanced": 0.10,
            "fortress": 0.15,
        }
        base += protection_bonus.get(protection_level, 0.0)

        return min(0.95, base)

    def export_to_yaml(self) -> str:
        """Export discoveries as YAML."""
        sources = self.db.get_all_sources()
        data = []

        for source in sources:
            data.append(
                {
                    "domain": source.domain,
                    "name": source.name,
                    "topics": source.topics,
                    "priority": round(source.priority, 2),
                    "policy": source.policy,
                    "region": source.region,
                    "protection_level": source.protection_level,
                    "bypass_method": source.bypass_method,
                    "rss_endpoints": source.rss_feeds,
                    "fetch_strategy": source.fetch_strategy,
                }
            )

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    async def close(self):
        """Cleanup resources."""
        # Close browser contexts
        for domain, context in self.contexts.items():
            await context.close()

        # Close browser
        if self.browser:
            await self.browser.close()

        # Stop playwright
        if self.playwright:
            await self.playwright.stop()

        # Close database
        self.db.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="🛡️ Enhanced Stealth Harvester")
    parser.add_argument("--seed", help="Single domain to discover")
    parser.add_argument("--seeds", help="File with seed domains")
    parser.add_argument("--config", help="Configuration YAML file")
    parser.add_argument("--out", help="Output YAML file")
    parser.add_argument(
        "--concurrent", action="store_true", help="Use concurrent workers"
    )

    args = parser.parse_args()

    if not args.seeds and not args.seed:
        eprint("No seeds provided. Use --seed or --seeds file.")
        return 2

    harvester = EnhancedStealthHarvester(config_path=args.config)

    try:
        # Collect domains
        domains = []
        if args.seed:
            domains.append(args.seed)
        if args.seeds:
            with open(args.seeds, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        domains.append(line)

        eprint(f"🕵️ Starting harvest of {len(domains)} domains...")

        # Run harvesting
        if args.concurrent:
            eprint(f"⚡ Using {harvester.max_workers} concurrent workers")
            await harvester.run_concurrent_harvest(domains)
        else:
            for i, domain in enumerate(domains):
                eprint(f"[{i+1}/{len(domains)}] Processing {domain}...")
                await harvester.discover_from_domain(domain)

        # Export results
        yaml_output = harvester.export_to_yaml()

        if args.out:
            with open(args.out, "w") as f:
                f.write(yaml_output)
            eprint(f"📝 Wrote results to {args.out}")
        else:
            print(yaml_output)

        return 0

    finally:
        await harvester.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        eprint("🛑 Harvest interrupted")
        sys.exit(130)
