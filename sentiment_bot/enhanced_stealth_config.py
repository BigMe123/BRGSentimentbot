"""
Enhanced Stealth Scraping Configuration
Provides advanced anti-detection capabilities
"""

import random
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import time


@dataclass
class StealthProfile:
    """Complete stealth profile for scraping"""
    user_agent: str
    viewport: Dict[str, int]
    timezone: str
    locale: str
    webgl_vendor: str
    webgl_renderer: str
    hardware_concurrency: int
    device_memory: int
    platform: str
    plugins: List[str]
    canvas_noise: float
    audio_noise: float
    font_list: List[str]


class StealthManager:
    """Manages stealth configurations and rotation"""

    def __init__(self):
        self.profiles = self._generate_profiles()
        self.current_profile_index = 0
        self.request_delays = self._init_delays()
        self.session_history = []

    def _generate_profiles(self) -> List[StealthProfile]:
        """Generate diverse browser profiles"""
        profiles = []

        # Chrome on Windows profiles
        for version in ["120", "121", "122"]:
            profiles.append(StealthProfile(
                user_agent=f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
                viewport={"width": random.choice([1920, 1680, 1440]), "height": random.choice([1080, 900, 768])},
                timezone="America/New_York",
                locale="en-US",
                webgl_vendor="Google Inc. (Intel)",
                webgl_renderer="ANGLE (Intel, Intel(R) HD Graphics 630 Direct3D11 vs_5_0 ps_5_0)",
                hardware_concurrency=random.choice([4, 8, 16]),
                device_memory=random.choice([8, 16, 32]),
                platform="Win32",
                plugins=["Chrome PDF Viewer", "Native Client"],
                canvas_noise=random.random() * 0.001,
                audio_noise=random.random() * 0.0001,
                font_list=["Arial", "Verdana", "Times New Roman", "Georgia", "Helvetica"]
            ))

        # Chrome on Mac profiles
        for version in ["120", "121", "122"]:
            profiles.append(StealthProfile(
                user_agent=f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
                viewport={"width": random.choice([1440, 1680, 1920]), "height": random.choice([900, 1050, 1200])},
                timezone="America/Los_Angeles",
                locale="en-US",
                webgl_vendor="Google Inc. (Apple)",
                webgl_renderer="ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
                hardware_concurrency=random.choice([8, 10, 12]),
                device_memory=random.choice([16, 32, 64]),
                platform="MacIntel",
                plugins=["Chrome PDF Viewer"],
                canvas_noise=random.random() * 0.001,
                audio_noise=random.random() * 0.0001,
                font_list=["Helvetica", "Arial", "Verdana", "Georgia", "Monaco"]
            ))

        # Firefox profiles
        for version in ["121", "122", "123"]:
            profiles.append(StealthProfile(
                user_agent=f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}.0) Gecko/20100101 Firefox/{version}.0",
                viewport={"width": random.choice([1920, 1680]), "height": random.choice([1080, 900])},
                timezone="Europe/London",
                locale="en-GB",
                webgl_vendor="Mozilla",
                webgl_renderer="Mozilla",
                hardware_concurrency=random.choice([4, 8]),
                device_memory=random.choice([8, 16]),
                platform="Win32",
                plugins=[],
                canvas_noise=random.random() * 0.001,
                audio_noise=random.random() * 0.0001,
                font_list=["Arial", "Verdana", "Tahoma", "Segoe UI"]
            ))

        # Safari profiles
        profiles.append(StealthProfile(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            viewport={"width": 1440, "height": 900},
            timezone="America/New_York",
            locale="en-US",
            webgl_vendor="Apple Inc.",
            webgl_renderer="Apple GPU",
            hardware_concurrency=8,
            device_memory=16,
            platform="MacIntel",
            plugins=[],
            canvas_noise=random.random() * 0.001,
            audio_noise=random.random() * 0.0001,
            font_list=["Helvetica Neue", "Helvetica", "Arial", "Lucida Grande"]
        ))

        return profiles

    def _init_delays(self) -> Dict[str, Any]:
        """Initialize realistic request delays"""
        return {
            'min_delay': 1.5,  # Minimum seconds between requests
            'max_delay': 5.0,  # Maximum seconds between requests
            'burst_delay': 0.5,  # Delay within burst requests
            'burst_size': 3,  # Max requests in a burst
            'session_delay': 30,  # Delay between sessions
            'jitter': True,  # Add random jitter
        }

    def get_random_profile(self) -> StealthProfile:
        """Get a random stealth profile"""
        return random.choice(self.profiles)

    def rotate_profile(self) -> StealthProfile:
        """Rotate to next profile in sequence"""
        profile = self.profiles[self.current_profile_index]
        self.current_profile_index = (self.current_profile_index + 1) % len(self.profiles)
        return profile

    def get_delay(self, request_type: str = 'normal') -> float:
        """Get appropriate delay for request type"""
        if request_type == 'burst':
            delay = self.request_delays['burst_delay']
        elif request_type == 'session':
            delay = self.request_delays['session_delay']
        else:
            delay = random.uniform(
                self.request_delays['min_delay'],
                self.request_delays['max_delay']
            )

        if self.request_delays['jitter']:
            delay += random.random() * 0.5

        return delay

    def get_headers(self, profile: StealthProfile, referer: Optional[str] = None) -> Dict[str, str]:
        """Get stealth headers for request"""
        headers = {
            'User-Agent': profile.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': f'{profile.locale},en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin' if referer else 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

        if referer:
            headers['Referer'] = referer

        # Add browser-specific headers
        if 'Chrome' in profile.user_agent:
            headers['Sec-Ch-Ua'] = '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"'
            headers['Sec-Ch-Ua-Mobile'] = '?0'
            headers['Sec-Ch-Ua-Platform'] = '"Windows"' if 'Windows' in profile.user_agent else '"macOS"'

        return headers

    def apply_browser_patches(self, page: Any) -> None:
        """Apply anti-detection patches to browser page"""
        # Inject JavaScript to override detection points
        patches = """
        // Override navigator properties
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Chrome specific
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {}
        };

        // Permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Plugin detection
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Language detection
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });

        // WebGL vendor/renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Google Inc. (Intel)';
            }
            if (parameter === 37446) {
                return 'ANGLE (Intel, Intel(R) HD Graphics Direct3D11 vs_5_0 ps_5_0)';
            }
            return getParameter(parameter);
        };

        // Canvas fingerprinting protection
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            const context = this.getContext('2d');
            const imageData = context.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] = imageData.data[i] ^ (Math.random() * 0.1);
            }
            context.putImageData(imageData, 0, 0);
            return originalToDataURL.apply(this, arguments);
        };

        // Audio fingerprinting protection
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const audioContext = new AudioContext();
        const originalCreateOscillator = audioContext.createOscillator;
        audioContext.createOscillator = function() {
            const oscillator = originalCreateOscillator.apply(this, arguments);
            const originalConnect = oscillator.connect;
            oscillator.connect = function() {
                arguments[0].gain.value = arguments[0].gain.value * (1 + Math.random() * 0.0001);
                return originalConnect.apply(this, arguments);
            };
            return oscillator;
        };
        """

        if hasattr(page, 'add_init_script'):
            page.add_init_script(patches)
        elif hasattr(page, 'evaluate_on_new_document'):
            page.evaluate_on_new_document(patches)

    def should_retry(self, status_code: int, attempt: int) -> bool:
        """Determine if request should be retried"""
        retry_codes = [429, 503, 504, 520, 521, 522, 523, 524]
        max_retries = 3

        if attempt >= max_retries:
            return False

        return status_code in retry_codes

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        base_delay = 2.0
        max_delay = 60.0
        delay = min(base_delay * (2 ** attempt) + random.random(), max_delay)
        return delay


class CloudflareBypass:
    """Bypass Cloudflare protection"""

    def __init__(self):
        self.session = None
        self.cookies = {}

    async def bypass_cloudflare(self, url: str, profile: StealthProfile) -> Optional[str]:
        """Attempt to bypass Cloudflare protection"""
        try:
            # Use curl_cffi for TLS fingerprint evasion
            response = curl_requests.get(
                url,
                impersonate="chrome110",  # Impersonate specific Chrome version
                headers={"User-Agent": profile.user_agent},
                timeout=30,
                allow_redirects=True
            )

            if response.status_code == 200:
                return response.text

            # If challenged, try with browser automation
            if "challenge" in response.text.lower() or response.status_code == 403:
                return await self._browser_bypass(url, profile)

        except Exception as e:
            print(f"Cloudflare bypass failed: {e}")
            return None

    async def _browser_bypass(self, url: str, profile: StealthProfile) -> Optional[str]:
        """Use browser automation to bypass challenges"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-web-security',
                        f'--user-agent={profile.user_agent}',
                    ]
                )

                context = await browser.new_context(
                    viewport=profile.viewport,
                    user_agent=profile.user_agent,
                    locale=profile.locale,
                    timezone_id=profile.timezone,
                )

                page = await context.new_page()

                # Apply stealth patches
                if stealth_async:
                    await stealth_async(page)

                # Navigate and wait for challenge
                await page.goto(url, wait_until='networkidle')
                await page.wait_for_timeout(5000)  # Wait for challenge to complete

                # Get content
                content = await page.content()

                await browser.close()
                return content

        except Exception as e:
            print(f"Browser bypass failed: {e}")
            return None


class ProxyRotator:
    """Manages proxy rotation for IP diversity"""

    def __init__(self, proxy_list: Optional[List[str]] = None):
        self.proxies = proxy_list or self._get_free_proxies()
        self.current_index = 0
        self.failed_proxies = set()

    def _get_free_proxies(self) -> List[str]:
        """Get list of free proxies (for testing only)"""
        # In production, use premium proxy services
        return []

    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        """Get next working proxy"""
        if not self.proxies:
            return None

        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)

            if proxy not in self.failed_proxies:
                return {
                    'http': proxy,
                    'https': proxy
                }

            attempts += 1

        return None

    def mark_failed(self, proxy: str):
        """Mark proxy as failed"""
        self.failed_proxies.add(proxy)


# Export main components
__all__ = ['StealthManager', 'CloudflareBypass', 'ProxyRotator', 'StealthProfile']