#!/usr/bin/env python3
"""
🛡️ Military-Grade Stealth Harvester
Advanced anti-detection source discovery with full browser emulation, TLS evasion, and enhanced stealth.
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
from typing import List, Dict, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import urllib.error
import xml.etree.ElementTree as ET

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
    """Print to stderr for status messages (won't mix with stdout output)."""
    try:
        msg = " ".join(map(str, args))
    except Exception:
        msg = " ".join(["<unprintable>" for _ in args])  # Handle encoding issues
    sys.stderr.write(msg + os.linesep)


@dataclass
class ProxyConfig:
    """Manages proxy rotation to avoid IP-based blocking."""

    proxies: List[str] = field(default_factory=list)  # List of proxy servers
    current_index: int = 0  # Current position in rotation
    failed_proxies: Set[str] = field(default_factory=set)  # Track failed proxies


@dataclass
class BrowserProfile:
    """Realistic browser fingerprint for rotation."""

    user_agent: str  # Browser user agent string
    viewport: Tuple[int, int]  # Screen resolution
    headers: Dict[str, str]  # HTTP headers specific to browser
    timezone: str  # Browser timezone
    language: str  # Browser language
    platform: str  # Operating system platform
    locale: str  # Browser locale setting


@dataclass
class SourceRecord:
    """Metadata for a discovered news source."""

    domain: str  # Domain name
    name: str = ""  # Site title/name
    topics: List[str] = field(default_factory=list)  # Content categories
    priority: float = 0.5  # Importance score (0-1)
    policy: str = "allow"  # Access policy
    region: str = "unknown"  # Geographic region
    rss_feeds: List[str] = field(default_factory=list)  # RSS/Atom feed URLs
    language: str = "en"  # Content language
    discovered_at: Optional[float] = None  # Discovery timestamp
    protection_level: str = "none"  # Bot protection level detected
    bypass_method: str = ""  # Technique used to bypass protection
    success_rate: float = 0.0  # Historical success rate


class StealthHarvester:
    """🛡️ Military-grade stealth harvester with full anti-detection."""

    def __init__(self, db_path: str = ".stealth_harvest_db.json"):
        self.db_path = db_path  # Database file path
        self.known: Dict[str, SourceRecord] = {}  # Discovered sources cache
        self.session_cookies: Dict[str, List[Dict]] = {}  # Cookie storage per domain
        self.proxy_config = ProxyConfig()  # Proxy rotation manager
        self.browser_profiles = (
            self._generate_browser_profiles()
        )  # Browser fingerprints
        self.current_profile = random.choice(self.browser_profiles)  # Active profile
        self.request_count = 0  # Track number of requests
        self.last_request_time = 0  # Timestamp of last request
        self.playwright = None  # Browser automation instance
        self.tls_sessions: Dict[str, Any] = {}  # TLS session cache
        self.dns_cache: Dict[str, str] = {}  # DNS resolution cache
        self.request_history: List[Tuple[str, float]] = []  # Request pattern tracking
        # Initialize 2Captcha solver with API key
        try:
            from twocaptcha import TwoCaptcha

            self.captcha_solver = TwoCaptcha("ad21dba743166099eabb775dfa61a09e")
        except ImportError:
            eprint("⚠️ 2Captcha library not installed. Run: pip install 2captcha-python")
            self.captcha_solver = None
        self.success_stats: Dict[str, Dict[str, int]] = {}  # Success metrics
        self.load_db()  # Load existing discoveries

    def _generate_browser_profiles(self) -> List[BrowserProfile]:
        """Create diverse browser fingerprints to avoid detection."""
        profiles = []  # Collection of browser profiles

        # Desktop Chrome - Latest versions for authenticity
        chrome_versions = [
            "131.0.6778.205",
            "130.0.6723.118",
            "129.0.6668.89",
            "128.0.6613.120",
            "127.0.6533.88",
        ]
        for version in chrome_versions:
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
                )
            )

        # Firefox profiles (desktop) - Latest versions
        firefox_versions = ["133.0", "132.0.2", "131.0.3", "130.0", "129.0"]
        for version in firefox_versions:
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
                )
            )

        # Safari profiles (desktop) - Latest versions
        safari_versions = ["18.2", "18.1", "18.0", "17.6", "17.5"]
        for version in safari_versions:
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
                )
            )

        # Mobile profiles (Android Chrome) - Latest versions
        mobile_versions = [
            "131.0.6778.135",
            "130.0.6723.107",
            "129.0.6668.100",
            "128.0.6613.127",
        ]
        for version in mobile_versions:
            profiles.append(
                BrowserProfile(
                    user_agent=f"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Mobile Safari/537.36",
                    viewport=(360, 800),
                    headers={
                        "sec-ch-ua": f'"Android WebView";v="{version.split(".")[0]}", "Chromium";v="{version.split(".")[0]}", "Not_A Brand";v="99"',
                        "sec-ch-ua-mobile": "?1",
                        "sec-ch-ua-platform": '"Android"',
                    },
                    timezone="America/Chicago",
                    language="en-US",
                    platform="Linux armv8l",
                    locale="en-US",
                )
            )

        return profiles

    async def _init_playwright(self):
        """Start browser automation for JS-rendered sites."""
        try:
            from playwright.async_api import async_playwright

            if not self.playwright:
                self.playwright = (
                    await async_playwright().start()
                )  # Start browser engine
        except ImportError:
            eprint("⚠️  Playwright not available - falling back to requests only")
            self.playwright = None

    def _rotate_proxy(self) -> Optional[str]:
        """Cycle through proxy servers to avoid IP blocking."""
        if not self.proxy_config.proxies:
            return None

        # Filter out failed proxies
        available_proxies = [
            p
            for p in self.proxy_config.proxies
            if p not in self.proxy_config.failed_proxies
        ]

        # Reset if all proxies failed
        if not available_proxies:
            self.proxy_config.failed_proxies.clear()
            available_proxies = self.proxy_config.proxies

        # Round-robin selection
        proxy = available_proxies[
            self.proxy_config.current_index % len(available_proxies)
        ]
        self.proxy_config.current_index += 1

        return proxy

    def _rotate_profile(self):
        """Switch browser fingerprint to avoid pattern detection."""
        self.current_profile = random.choice(self.browser_profiles)  # Random selection
        eprint(f"🔄 Rotated to {self.current_profile.user_agent[:50]}...")

    async def _smart_delay(self, base_delay: float = 3.0, jitter: float = 1.5):
        """Human-like timing with circadian rhythm patterns."""
        self.request_count += 1

        # Adjust speed based on time of day (mimics human activity)
        import datetime

        hour = datetime.datetime.now().hour
        if 0 <= hour < 6:  # Night time
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

        # Add Gaussian distribution for more realistic timing
        delay = base_delay + random.gauss(0, jitter)
        delay = max(1.0, delay)

        time_since_last = time.time() - self.last_request_time
        if time_since_last < delay:
            await asyncio.sleep(delay - time_since_last)

        self.last_request_time = time.time()

        # Random extended breaks with varying probabilities
        break_chance = random.random()
        if break_chance < 0.05:  # 5% chance of long break
            eprint("☕ Taking extended human-like break...")
            await asyncio.sleep(random.uniform(30, 90))
        elif break_chance < 0.15:  # 10% chance of medium break
            eprint("⏸️  Taking short break...")
            await asyncio.sleep(random.uniform(10, 25))

    async def _stealth_get(
        self, url: str, use_browser: bool = False, retries: int = 3
    ) -> Optional[str]:
        """Main stealth request handler with retry logic."""

        # Monitor request patterns for suspicious behavior
        self._track_request_pattern(url)

        # Insert decoy requests if pattern looks bot-like
        if self._is_pattern_suspicious():
            eprint("⚠️ Suspicious pattern detected - inserting decoy requests")
            await self._insert_decoy_requests()

        for attempt in range(retries):
            await self._smart_delay()

            if self.request_count % 8 == 0:  # Rotate more frequently
                self._rotate_profile()

            try:
                if use_browser and self.playwright:
                    return await self._browser_get(url)
                else:
                    return await self._requests_get(url)
            except Exception as e:
                eprint(
                    f"Stealth request failed for {url} (attempt {attempt+1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(random.uniform(5, 15))  # Backoff
                    self._rotate_profile()  # Switch profile on failure

        return None

    def _track_request_pattern(self, url: str):
        """Record request for pattern analysis."""
        self.request_history.append((url, time.time()))  # Store URL and timestamp
        # Maintain sliding window of 100 requests
        if len(self.request_history) > 100:
            self.request_history.pop(0)

    def _is_pattern_suspicious(self) -> bool:
        """Detect bot-like patterns in request history."""
        if len(self.request_history) < 10:
            return False  # Not enough data

        # Check for overly regular timing (bot signature)
        recent_times = [t for _, t in self.request_history[-10:]]
        time_diffs = [
            recent_times[i + 1] - recent_times[i] for i in range(len(recent_times) - 1)
        ]

        # If timing is too regular (low variance), it's suspicious
        if time_diffs:
            avg_diff = sum(time_diffs) / len(time_diffs)
            variance = sum((d - avg_diff) ** 2 for d in time_diffs) / len(time_diffs)
            if variance < 0.5:  # Too regular
                return True

        # Check for same domain too frequently
        recent_domains = [
            urlparse(url).hostname for url, _ in self.request_history[-20:]
        ]
        domain_counts = {}
        for domain in recent_domains:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # If any domain appears more than 50% of the time, it's suspicious
        max_count = max(domain_counts.values()) if domain_counts else 0
        if max_count > 10:
            return True

        return False

    async def _insert_decoy_requests(self):
        """Make fake requests to popular sites to appear human."""
        # Popular sites a human might visit
        decoy_sites = [
            "https://www.google.com",
            "https://www.wikipedia.org",
            "https://www.reddit.com",
            "https://www.twitter.com",
            "https://www.youtube.com",
            "https://www.amazon.com",
            "https://news.ycombinator.com",
            "https://www.github.com",
        ]

        # Make 1-3 decoy requests
        num_decoys = random.randint(1, 3)
        for _ in range(num_decoys):
            decoy_url = random.choice(decoy_sites)
            eprint(f"🎭 Making decoy request to {decoy_url}")
            try:
                await self._requests_get(decoy_url)
            except:
                pass  # Ignore decoy failures
            await asyncio.sleep(random.uniform(2, 5))

    async def _browser_get(self, url: str) -> Optional[str]:
        """Fetch content using automated browser with anti-detection."""
        await self._init_playwright()  # Initialize browser engine
        if not self.playwright:
            return None  # Fallback if browser not available

        proxy = self._rotate_proxy()
        proxy_dict = {"server": proxy} if proxy else None

        try:
            browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-images",  # Optional for speed
                    # Removed --disable-javascript for dynamic content
                ],
            )
            context = await browser.new_context(
                viewport={
                    "width": self.current_profile.viewport[0],
                    "height": self.current_profile.viewport[1],
                },
                user_agent=self.current_profile.user_agent,
                extra_http_headers=self._build_headers(),
                proxy=proxy_dict,
                locale=self.current_profile.locale,
                timezone_id=self.current_profile.timezone,
            )

            # Load cookies if available
            domain = urlparse(url).hostname
            if domain in self.session_cookies:
                await context.add_cookies(self.session_cookies[domain])

            page = await context.new_page()
            if stealth_async:
                await stealth_async(page)  # Apply stealth patches
            else:
                # Manual stealth patches if library not available
                await self._apply_manual_stealth_patches(page)

            # Navigate with realistic behavior
            await page.goto(
                url, wait_until="networkidle", timeout=20000
            )  # Upgraded wait for better loading

            # Check for CAPTCHA presence
            captcha_detected = await page.evaluate(
                """
                () => {
                    // Check for various CAPTCHA types
                    const recaptcha = document.querySelector('[data-sitekey], .g-recaptcha, #g-recaptcha');
                    const hcaptcha = document.querySelector('.h-captcha, [data-hcaptcha-sitekey]');
                    const cloudflare = document.querySelector('.cf-challenge, #cf-content');
                    
                    if (recaptcha) return 'recaptcha';
                    if (hcaptcha) return 'hcaptcha';
                    if (cloudflare) return 'cloudflare';
                    
                    // Check for CAPTCHA in text
                    const bodyText = document.body.innerText.toLowerCase();
                    if (bodyText.includes('captcha') || bodyText.includes('verify you are human')) {
                        return 'generic';
                    }
                    
                    return null;
                }
            """
            )

            if captcha_detected:
                eprint(f"🚨 CAPTCHA detected: {captcha_detected}")
                if captcha_detected in ["recaptcha", "hcaptcha"]:
                    # Attempt to solve CAPTCHA
                    solved = await self._handle_captcha(page, captcha_detected)
                    if solved:
                        # Wait for page to reload after CAPTCHA
                        await asyncio.sleep(3)
                        await page.wait_for_load_state("networkidle")
                    else:
                        eprint("⚠️ Could not solve CAPTCHA - continuing anyway")

            # Simulate human behavior
            await self._simulate_human_behavior(page)

            # Honeypot avoidance: Detect hidden links/fields
            await self._avoid_honeypots(page)

            content = await page.content()

            # Save cookies
            cookies = await context.cookies()
            self.session_cookies[domain] = cookies

            await context.close()
            await browser.close()

            return content

        except Exception as e:
            eprint(f"Browser request failed for {url}: {e}")
            if proxy:
                self.proxy_config.failed_proxies.add(proxy)
            return None

    async def _simulate_human_behavior(self, page):
        """Mimic human browsing with realistic mouse/scroll patterns."""
        try:
            viewport_width = self.current_profile.viewport[0]
            viewport_height = self.current_profile.viewport[1]

            # Choose reading pattern (how humans scan pages)
            reading_pattern = random.choice(["F", "Z", "random"])

            if reading_pattern == "F":
                # F-pattern: horizontal top, vertical left, horizontal middle
                await self._simulate_f_pattern_reading(
                    page, viewport_width, viewport_height
                )
            elif reading_pattern == "Z":
                # Z-pattern: diagonal reading
                await self._simulate_z_pattern_reading(
                    page, viewport_width, viewport_height
                )
            else:
                # Random scrolling and interaction
                await self._simulate_random_browsing(
                    page, viewport_width, viewport_height
                )

            # Simulate text selection occasionally
            if random.random() < 0.15:
                await self._simulate_text_selection(page)

            # Simulate tab switching behavior
            if random.random() < 0.1:
                await self._simulate_tab_behavior(page)

            # Random idle time (simulating reading)
            if random.random() < 0.3:
                reading_time = random.uniform(2, 8)
                await asyncio.sleep(reading_time)

        except Exception as e:
            eprint(f"Behavioral simulation failed: {e}")

    async def _simulate_f_pattern_reading(self, page, width, height):
        """F-pattern: how users scan headlines and left content."""
        try:
            # Scan top horizontally (headlines)
            for x in range(100, width - 100, 150):
                await page.mouse.move(x, 100)
                await asyncio.sleep(random.uniform(0.1, 0.3))

            # Vertical scan down left side
            for y in range(100, min(height, 800), 100):
                await page.mouse.move(150, y)
                await asyncio.sleep(random.uniform(0.2, 0.4))

            # Middle horizontal scan
            for x in range(150, width // 2, 100):
                await page.mouse.move(x, height // 2)
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except:
            pass

    async def _simulate_z_pattern_reading(self, page, width, height):
        """Z-pattern: diagonal scanning for visual layouts."""
        try:
            # Start top-left, move to top-right
            await page.mouse.move(100, 100)
            await asyncio.sleep(0.5)
            await page.mouse.move(width - 100, 100)
            await asyncio.sleep(0.5)

            # Diagonal to bottom left
            await page.mouse.move(100, min(height - 100, 700))
            await asyncio.sleep(0.5)

            # Bottom left to bottom right
            await page.mouse.move(width - 100, min(height - 100, 700))
            await asyncio.sleep(0.5)
        except:
            pass

    async def _simulate_random_browsing(self, page, width, height):
        """Simulate random browsing behavior."""
        try:
            # Multiple random scrolls with varying speeds
            for _ in range(random.randint(1, 4)):
                scroll_distance = random.randint(100, height // 2)
                direction = random.choice([1, -1])
                scroll_speed = random.choice(["smooth", "auto"])

                await page.evaluate(
                    f"""
                    window.scrollBy({{
                        top: {scroll_distance * direction},
                        behavior: '{scroll_speed}'
                    }});
                """
                )
                await asyncio.sleep(random.uniform(0.5, 2.0))

            # Random mouse movements with bezier curves
            for _ in range(random.randint(2, 5)):
                x = random.randint(50, width - 50)
                y = random.randint(50, min(height - 50, 800))

                # Move with random speed
                steps = random.randint(5, 15)
                await self._bezier_mouse_move(page, x, y, steps)
                await asyncio.sleep(random.uniform(0.2, 1.0))
        except:
            pass

    async def _bezier_mouse_move(self, page, target_x, target_y, steps=10):
        """Natural curved mouse movement (humans don't move in straight lines)."""
        try:
            # Starting position estimate
            current_x = random.randint(100, 300)
            current_y = random.randint(100, 300)

            # Bezier curve control points for natural arc
            cp1_x = current_x + random.randint(-100, 100)
            cp1_y = current_y + random.randint(-100, 100)
            cp2_x = target_x + random.randint(-100, 100)
            cp2_y = target_y + random.randint(-100, 100)

            for i in range(steps):
                t = i / steps
                # Cubic bezier formula
                x = (
                    (1 - t) ** 3 * current_x
                    + 3 * (1 - t) ** 2 * t * cp1_x
                    + 3 * (1 - t) * t**2 * cp2_x
                    + t**3 * target_x
                )
                y = (
                    (1 - t) ** 3 * current_y
                    + 3 * (1 - t) ** 2 * t * cp1_y
                    + 3 * (1 - t) * t**2 * cp2_y
                    + t**3 * target_y
                )

                await page.mouse.move(int(x), int(y))
                await asyncio.sleep(0.01)
        except:
            # Fallback to simple move
            await page.mouse.move(target_x, target_y)

    async def _simulate_text_selection(self, page):
        """Simulate text selection behavior."""
        try:
            # Triple-click to select paragraph
            x = random.randint(200, 400)
            y = random.randint(200, 400)
            await page.mouse.click(x, y, click_count=3)
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Clear selection
            await page.mouse.click(100, 100)
        except:
            pass

    async def _simulate_tab_behavior(self, page):
        """Simulate tab key navigation."""
        try:
            for _ in range(random.randint(1, 3)):
                await page.keyboard.press("Tab")
                await asyncio.sleep(random.uniform(0.3, 0.8))
        except:
            pass

    async def _apply_manual_stealth_patches(self, page):
        """Inject JavaScript to hide automation signatures."""
        try:
            # Override telltale browser automation properties
            await page.add_init_script(
                """
                // Override webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override chrome property
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {}
                };
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Override plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Canvas fingerprint protection with noise
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    const context = this.getContext('2d');
                    if (context) {
                        // Add imperceptible noise
                        const imageData = context.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {
                            imageData.data[i] = imageData.data[i] ^ 1;  // Tiny modification
                        }
                        context.putImageData(imageData, 0, 0);
                    }
                    return originalToDataURL.apply(this, arguments);
                };
                
                // WebGL fingerprint protection
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter(parameter);
                };
                
                // Battery API protection
                if (navigator.getBattery) {
                    navigator.getBattery = () => Promise.resolve({
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1
                    });
                }
            """
            )
        except Exception as e:
            eprint(f"Manual stealth patches failed: {e}")

    async def _avoid_honeypots(self, page):
        """Detect invisible traps meant to catch bots."""
        try:
            # Find hidden elements bots might interact with
            hidden_elements = await page.query_selector_all(
                '[style*="display:none"], [style*="visibility:hidden"], input[type="hidden"]'
            )
            if hidden_elements:
                eprint(
                    f"⚠️ Detected {len(hidden_elements)} potential honeypots - avoiding interaction"
                )
                # Don't interact with hidden elements (bot trap)
        except Exception as e:
            eprint(f"Honeypot detection failed: {e}")

    async def _requests_get(self, url: str) -> Optional[str]:
        """HTTP request with TLS fingerprint spoofing."""
        headers = self._build_headers()  # Generate browser-like headers
        proxy = self._rotate_proxy()  # Get next proxy if available
        proxies = {"http": proxy, "https": proxy} if proxy else None

        try:
            # Use curl_cffi for TLS fingerprint mimic (impersonate recent Chrome)
            # Available options: chrome110, chrome116, chrome120, edge101, safari17_0
            impersonate_browser = random.choice(
                ["chrome120", "chrome116", "chrome110", "edge101"]
            )
            response = curl_requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=20,
                impersonate=impersonate_browser,
            )
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                eprint(f"🚫 Access denied for {url} (bot detected)")
            elif response.status_code == 404:
                eprint(f"❌ Not found: {url} (possible fake 404)")
            else:
                eprint(f"HTTP {response.status_code} for {url}")

            return None

        except Exception as e:
            if proxy:
                self.proxy_config.failed_proxies.add(proxy)
                eprint(f"Proxy {proxy} failed, rotating...")
            eprint(f"Request failed for {url}: {e}")
            return None

    def _build_headers(self) -> Dict[str, str]:
        """Build realistic HTTP headers for current profile, enhanced with Sec-Fetch."""
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

        # Add random referer from search engines
        if random.random() < 0.3:
            referers = [
                "https://www.google.com/",
                "https://www.bing.com/",
                "https://search.yahoo.com/",
            ]
            base_headers["Referer"] = random.choice(referers)

        return base_headers

    def _detect_protection_level(
        self, url: str, content: Optional[str], response_code: int
    ) -> Tuple[str, str]:
        """Identify anti-bot systems and suggest bypass strategy."""
        bypass_method = ""

        # Infer protection from HTTP status codes
        if not content:
            if response_code == 403:
                return "fortress", "browser_with_solver"  # Highest protection
            elif response_code == 404:
                return "advanced", "browser_stealth"  # Fake 404 protection
            else:
                return "basic", "rotate_profile"  # Basic blocking

        content_lower = content.lower()

        # Extended protection indicators with bypass methods
        protection_indicators = [
            ("cloudflare", "advanced", "cf_bypass"),
            ("recaptcha", "advanced", "captcha_solver"),
            ("hcaptcha", "advanced", "captcha_solver"),
            ("geetest", "advanced", "captcha_solver"),
            ("funcaptcha", "advanced", "captcha_solver"),
            ("please enable javascript", "advanced", "browser_js"),
            ("access denied", "basic", "rotate_ip"),
            ("blocked", "basic", "rotate_profile"),
            ("bot", "basic", "stealth_headers"),
            ("datadome", "fortress", "advanced_solver"),
            ("perimeterx", "fortress", "px_bypass"),
            ("akamai", "advanced", "akamai_bypass"),
            ("incapsula", "advanced", "incap_bypass"),
            ("f5", "advanced", "f5_bypass"),
            ("imperva", "advanced", "imperva_bypass"),
            ("kasada", "fortress", "kasada_solver"),
            ("shape security", "fortress", "shape_bypass"),
            ("distil", "advanced", "distil_bypass"),
        ]

        for indicator, level, method in protection_indicators:
            if indicator in content_lower:
                return level, method

        # Check for CAPTCHA images
        if any(
            x in content_lower for x in ["captcha", "challenge", "verify you are human"]
        ):
            return "advanced", "captcha_solver"

        return "none", ""

    async def _handle_captcha(self, page, captcha_type: str = "recaptcha") -> bool:
        """Solve CAPTCHA challenges using 2Captcha service."""
        eprint(f"🔐 CAPTCHA detected: {captcha_type}")

        # Check for CAPTCHA solving service
        if not self.captcha_solver:
            eprint("⚠️ No CAPTCHA solver available - install 2captcha-python")
            return False

        try:
            page_url = page.url

            if captcha_type == "recaptcha":
                # Find reCAPTCHA site key
                site_key = await page.evaluate(
                    """
                    () => {
                        // Check for reCAPTCHA v2
                        const recap = document.querySelector('[data-sitekey]');
                        if (recap) return recap.getAttribute('data-sitekey');
                        
                        // Check for reCAPTCHA v3
                        const scripts = Array.from(document.scripts);
                        for (const script of scripts) {
                            const match = script.innerHTML.match(/grecaptcha.execute\\(['"]([^'"]+)['"]/);
                            if (match) return match[1];
                        }
                        return null;
                    }
                """
                )

                if site_key:
                    eprint(f"📝 Found reCAPTCHA site key: {site_key[:20]}...")
                    eprint("🔄 Solving CAPTCHA with 2Captcha service...")

                    # Solve with 2Captcha
                    result = self.captcha_solver.recaptcha(
                        sitekey=site_key, url=page_url
                    )

                    if result and "code" in result:
                        # Inject solution
                        await page.evaluate(
                            f"""
                            document.getElementById('g-recaptcha-response').innerHTML='{result['code']}';
                            if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {{
                                Object.entries(window.___grecaptcha_cfg.clients).forEach(([key, client]) => {{
                                    if (client.callback) {{
                                        client.callback('{result['code']}');
                                    }}
                                }});
                            }}
                        """
                        )
                        eprint("✅ CAPTCHA solved successfully!")

                        # Submit form if exists
                        await page.evaluate(
                            """
                            const forms = document.querySelectorAll('form');
                            if (forms.length > 0) forms[0].submit();
                        """
                        )

                        return True

            elif captcha_type == "hcaptcha":
                # Find hCaptcha site key
                site_key = await page.evaluate(
                    """
                    () => {
                        const hcap = document.querySelector('[data-sitekey]');
                        if (hcap && hcap.className.includes('h-captcha')) {
                            return hcap.getAttribute('data-sitekey');
                        }
                        return null;
                    }
                """
                )

                if site_key:
                    eprint(f"📝 Found hCaptcha site key: {site_key[:20]}...")
                    eprint("🔄 Solving hCAPTCHA with 2Captcha service...")

                    # Solve with 2Captcha
                    result = self.captcha_solver.hcaptcha(
                        sitekey=site_key, url=page_url
                    )

                    if result and "code" in result:
                        # Inject solution
                        await page.evaluate(
                            f"""
                            document.querySelector('[name="h-captcha-response"]').innerHTML='{result['code']}';
                            document.querySelector('[name="g-recaptcha-response"]').innerHTML='{result['code']}';
                        """
                        )
                        eprint("✅ hCAPTCHA solved successfully!")
                        return True

        except Exception as e:
            eprint(f"❌ CAPTCHA solving failed: {e}")

        return False

    async def discover_from_domain(self, domain: str) -> Optional[SourceRecord]:
        """Main discovery function - finds RSS feeds and site metadata."""
        domain = self._normalize_domain(domain)  # Clean domain format

        # Check cache first
        if domain in self.known:
            eprint(f"Already known: {domain}")
            return self.known[domain]

        eprint(f"🕵️  Stealth discovering: {domain}")

        # Try with basic requests first
        url = f"https://{domain}"
        content = await self._stealth_get(url)

        # If blocked, escalate to browser
        if not content:
            eprint(f"🚀 Escalating to browser mode for {domain}")
            content = await self._stealth_get(url, use_browser=True)

        if not content:
            eprint(f"💀 All stealth methods failed for {domain}")
            # Track failure
            if domain not in self.success_stats:
                self.success_stats[domain] = {"success": 0, "failure": 0}
            self.success_stats[domain]["failure"] += 1
            return None

        protection_level, bypass_method = self._detect_protection_level(
            url, content, 200
        )
        eprint(
            f"🛡️  Protection level: {protection_level}, Bypass method: {bypass_method}"
        )

        # Track success
        if domain not in self.success_stats:
            self.success_stats[domain] = {"success": 0, "failure": 0}
        self.success_stats[domain]["success"] += 1

        # Calculate success rate
        stats = self.success_stats[domain]
        success_rate = stats["success"] / (stats["success"] + stats["failure"])

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
            success_rate=success_rate,
            discovered_at=time.time(),
        )

        self.known[domain] = record
        eprint(
            f"✅ Discovered: {domain} -> {len(rss_feeds)} feeds, protection={protection_level}"
        )
        return record

    async def _find_rss_feeds(self, html: str, domain: str) -> List[str]:
        """Extract and validate RSS/Atom feed URLs from HTML."""
        feeds = []  # Collection of feed URLs

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
        common_paths = [
            "/rss",
            "/feed",
            "/rss.xml",
            "/feed.xml",
            "/atom.xml",
            "/news.rss",
        ]
        for path in common_paths:
            url = f"https://{domain}{path}"
            if await self._is_valid_rss(url):
                feeds.append(url)

        return list(set(feeds))  # Deduplicate

    async def _is_valid_rss(self, url: str) -> bool:
        """Validate RSS feed with stealth."""
        try:
            content = await self._stealth_get(url)
            if not content or len(content) < 100:
                return False

            # Look for RSS indicators
            rss_indicators = [
                "<rss",
                "<feed",
                "</rss>",
                "</feed>",
                "<channel",
                "<item",
                "<entry",
            ]
            content_lower = content.lower()

            if not any(indicator in content_lower for indicator in rss_indicators):
                return False

            # Try to parse as XML
            try:
                root = ET.fromstring(content)
                tag_lower = root.tag.lower()

                valid_formats = ["rss", "feed", "channel"]
                is_valid = any(fmt in tag_lower for fmt in valid_formats)

                if is_valid:
                    eprint(f"✅ Valid RSS: {url}")
                    return True

            except ET.ParseError:
                pass

            return False

        except Exception as e:
            eprint(f"RSS validation error for {url}: {e}")
            return False

    def _normalize_domain(self, domain: str) -> str:
        """Clean and standardize domain format."""
        domain = domain.lower().strip()  # Lowercase
        domain = re.sub(r"^https?://", "", domain)  # Remove protocol
        domain = re.sub(r"^www\.", "", domain)  # Remove www
        domain = domain.rstrip("/")  # Remove trailing slash
        return domain

    def _infer_region(self, domain: str) -> str:
        """Guess geographic region from domain TLD."""
        # European domains
        if (
            domain.endswith(".uk")
            or "bbc" in domain
            or domain.endswith(".fr")
            or domain.endswith(".de")
        ):
            return "europe"
        elif domain.endswith(".com") or domain.endswith(".org"):
            if any(x in domain for x in ["asia", "japan", "china", "india"]):
                return "asia"
            return "americas"
        elif domain.endswith(".au"):
            return "asia"
        else:
            return "unknown"

    def _infer_topics(self, text: str) -> List[str]:
        """Detect content categories from text keywords."""
        text = text.lower()  # Normalize for matching
        topics = []  # Detected topics

        if any(
            word in text
            for word in ["economic", "finance", "business", "market", "trade"]
        ):
            topics.append("economy")
        if any(
            word in text for word in ["politic", "government", "policy", "election"]
        ):
            topics.append("politics")
        if any(
            word in text for word in ["security", "defense", "military", "conflict"]
        ):
            topics.append("security")
        if any(word in text for word in ["technology", "tech", "digital", "ai"]):
            topics.append("tech")
        if any(word in text for word in ["foreign", "international", "diplomatic"]):
            topics.append("diplomacy")

        if not topics:
            topics.append("general")

        return topics

    def _calculate_priority(
        self, domain: str, topics: List[str], protection_level: str
    ) -> float:
        """Score source importance (0-1 scale)."""
        base = 0.5  # Default priority

        # Higher score for trusted/authoritative sources
        if any(x in domain for x in ["gov", "edu", "reuters", "bbc", "economist"]):
            base += 0.3

        # Boost specific topics
        if "economy" in topics or "politics" in topics:
            base += 0.1

        # Adjust for protection level (harder to access = potentially more valuable)
        protection_bonus = {
            "none": 0.0,
            "basic": 0.05,
            "advanced": 0.10,
            "fortress": 0.15,
        }
        base += protection_bonus.get(protection_level, 0.0)

        return min(0.95, base)

    def _extract_title(self, html: str) -> str:
        """Get page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            title = re.sub(r"<[^>]+>", "", match.group(1)).strip()  # Remove HTML tags
            return title[:100]  # Truncate long titles
        return ""

    def _extract_description(self, html: str) -> str:
        """Extract description from HTML."""
        match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:200]  # Limit length
        return ""

    def load_db(self):
        """Load previously discovered sources from disk."""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    data = json.load(f)
                    # Reconstruct SourceRecord objects
                    for domain, record_data in data.items():
                        record = SourceRecord(**record_data)
                        self.known[domain] = record
            except Exception as e:
                eprint(f"Warning: Could not load DB {self.db_path}: {e}")

    def save_db(self):
        """Persist discovered sources to disk."""
        try:
            data = {}  # JSON serializable format
            for domain, record in self.known.items():
                data[domain] = {
                    "domain": record.domain,
                    "name": record.name,
                    "topics": record.topics,
                    "priority": record.priority,
                    "policy": record.policy,
                    "region": record.region,
                    "rss_feeds": record.rss_feeds,
                    "language": record.language,
                    "protection_level": record.protection_level,
                    "bypass_method": record.bypass_method,
                    "success_rate": record.success_rate,
                    "discovered_at": record.discovered_at,
                }
            with open(self.db_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            eprint(f"Warning: Could not save DB {self.db_path}: {e}")

    def to_yaml(self) -> str:
        """Convert discovered sources to YAML format."""
        lines = []  # YAML lines
        for domain, record in sorted(self.known.items()):  # Alphabetical order
            lines.append(f'- domain: "{record.domain}"')
            lines.append(f'  name: "{record.name}"')
            lines.append(f"  topics: {json.dumps(record.topics)}")
            lines.append(f"  priority: {record.priority:.2f}")
            lines.append(f'  policy: "{record.policy}"')
            lines.append(f'  region: "{record.region}"')
            lines.append(f'  protection_level: "{record.protection_level}"')
            if record.bypass_method:
                lines.append(f'  bypass_method: "{record.bypass_method}"')
            if record.success_rate > 0:
                lines.append(f"  success_rate: {record.success_rate:.2f}")
            if record.rss_feeds:
                lines.append(f"  rss_endpoints: {json.dumps(record.rss_feeds)}")
            lines.append("")

        return "\n".join(lines)

    async def close(self):
        """Cleanup resources."""
        if self.playwright:
            await self.playwright.stop()


async def run_stealth_harvest(args) -> int:
    """Main execution function for command-line usage."""
    # Validate input
    if not args.seeds and not args.seed:
        eprint("No seeds provided. Use --seed or --seeds file.")
        return 2

    # Initialize harvester with database
    harvester = StealthHarvester(args.db)

    # Optional: Load proxy list for IP rotation
    if args.proxies:
        try:
            with open(args.proxies, "r") as f:
                harvester.proxy_config.proxies = [
                    line.strip() for line in f if line.strip()
                ]
            eprint(f"🔄 Loaded {len(harvester.proxy_config.proxies)} proxies")
        except Exception as e:
            eprint(f"Warning: Could not load proxies: {e}")

    try:
        # Collect domains from command-line and file
        domains = []
        if args.seed:
            domains.append(args.seed)  # Single domain
        if args.seeds:  # File with domain list
            try:
                with open(args.seeds, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if line.startswith("- "):
                                line = line[2:].strip()
                            domains.append(line)
            except Exception as e:
                eprint(f"Error reading seeds file {args.seeds}: {e}")
                return 1

        eprint(f"🕵️  Starting stealth harvest of {len(domains)} domains...")

        # Process each domain with stealth techniques
        for i, domain in enumerate(domains):
            eprint(f"[{i+1}/{len(domains)}] Processing {domain}...")
            await harvester.discover_from_domain(domain)  # Main discovery

        # Save discoveries
        harvester.save_db()

        # Output YAML
        if args.out:
            try:
                with open(args.out, "w") as f:
                    f.write(harvester.to_yaml())
                eprint(f"📝 Wrote {len(harvester.known)} sources to {args.out}")
            except Exception as e:
                eprint(f"Error writing output {args.out}: {e}")
                return 1
        else:
            print(harvester.to_yaml())

        return 0

    finally:
        await harvester.close()


def main():
    """Command-line interface setup."""
    # Define command-line arguments
    parser = argparse.ArgumentParser(
        description="🛡️ Military-Grade Stealth Source Harvester"
    )
    parser.add_argument("--seed", help="Single domain to discover")
    parser.add_argument("--seeds", help="File with seed domains (one per line)")
    parser.add_argument("--out", help="Output YAML file (default: stdout)")
    parser.add_argument(
        "--db", default=".stealth_harvest_db.json", help="JSON database file"
    )
    parser.add_argument("--proxies", help="File with proxy list (one per line)")

    args = parser.parse_args()

    try:
        return asyncio.run(run_stealth_harvest(args))
    except KeyboardInterrupt:
        eprint("🛑 Stealth harvest interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
