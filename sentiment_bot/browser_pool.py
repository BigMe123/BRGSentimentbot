"""
Playwright persistent browser pool for efficient JS rendering.
Reuses browser context and pages to avoid startup overhead.
"""

import asyncio
import logging
import random
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, List
from contextlib import asynccontextmanager

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)


class PlaywrightPool:
    """
    Manages a pool of Playwright pages for concurrent rendering.
    Uses persistent context to maintain cookies/state across renders.
    """
    
    def __init__(self, pages: int = 5, browser_type: str = 'chromium'):
        """
        Initialize the pool.
        
        Args:
            pages: Number of concurrent pages to maintain
            browser_type: 'chromium', 'firefox', or 'webkit'
        """
        if not HAS_PLAYWRIGHT:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install")
        
        self.num_pages = pages
        self.browser_type = browser_type
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page_queue: Optional[asyncio.Queue] = None
        self.pages: List[Page] = []
        self.user_data_dir = None
        self.is_started = False
        
        # Stats
        self.stats = {
            'renders': 0,
            'errors': 0,
            'total_time_ms': 0,
        }
    
    async def start(self):
        """Start the browser and create page pool."""
        if self.is_started:
            return
        
        logger.info(f"[BROWSER_POOL] Starting {self.browser_type} with {self.num_pages} pages")
        
        # Create temp directory for user data
        self.user_data_dir = Path(tempfile.mkdtemp(prefix="brgsentiment_"))
        
        # Start Playwright
        self.playwright = await async_playwright().start()
        
        # Launch browser with persistent context
        browser_class = getattr(self.playwright, self.browser_type)
        
        # Browser arguments for stealth
        args = []
        if self.browser_type == 'chromium':
            args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        
        # Launch persistent context (keeps cookies, localStorage, etc.)
        self.context = await browser_class.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=True,
            args=args,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            ignore_https_errors=False,  # Keep SSL verification
            java_script_enabled=True,
        )
        
        # Anti-detection scripts
        await self.context.add_init_script("""
            // Override webdriver detection
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Add realistic plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Set realistic languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Hide automation
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """)
        
        # Create page pool
        self.page_queue = asyncio.Queue()
        for i in range(self.num_pages):
            page = await self.context.new_page()
            self.pages.append(page)
            await self.page_queue.put(page)
            logger.debug(f"[BROWSER_POOL] Created page {i+1}/{self.num_pages}")
        
        self.is_started = True
        logger.info(f"[BROWSER_POOL] Started successfully with {len(self.pages)} pages")
    
    async def render(self, url: str, extra_headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Render a URL using a page from the pool.
        
        Args:
            url: URL to render
            extra_headers: Optional additional headers
        
        Returns:
            HTML content or None if failed
        """
        if not self.is_started:
            await self.start()
        
        page = None
        start_time = time.time()
        
        try:
            # Get page from pool (wait if none available)
            page = await asyncio.wait_for(self.page_queue.get(), timeout=30)
            
            # Set headers if provided
            if extra_headers:
                # Filter out headers that Playwright doesn't like
                safe_headers = {
                    k: v for k, v in extra_headers.items()
                    if k.lower() not in ['host', 'content-length', 'connection']
                }
                await page.set_extra_http_headers(safe_headers)
            
            # Random delay to mimic human behavior
            await asyncio.sleep(random.uniform(0.1, 0.5))
            
            # Navigate to URL
            response = await page.goto(
                url,
                wait_until='domcontentloaded',
                timeout=30000
            )
            
            # Wait a bit for dynamic content
            await page.wait_for_timeout(random.randint(500, 1500))
            
            # Random scroll to trigger lazy loading
            if random.random() < 0.3:  # 30% chance
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(random.randint(200, 500))
            
            # Get content
            content = await page.content()
            
            # Update stats
            elapsed_ms = int((time.time() - start_time) * 1000)
            self.stats['renders'] += 1
            self.stats['total_time_ms'] += elapsed_ms
            
            logger.debug(f"[BROWSER_POOL] Rendered {url} in {elapsed_ms}ms")
            
            return content
            
        except asyncio.TimeoutError:
            logger.error(f"[BROWSER_POOL] Timeout rendering {url}")
            self.stats['errors'] += 1
            return None
            
        except Exception as e:
            logger.error(f"[BROWSER_POOL] Error rendering {url}: {e}")
            self.stats['errors'] += 1
            
            # If page crashed, create a new one
            if page and page.is_closed():
                try:
                    self.pages.remove(page)
                    new_page = await self.context.new_page()
                    self.pages.append(new_page)
                    page = new_page
                    logger.info("[BROWSER_POOL] Replaced crashed page")
                except Exception as replace_error:
                    logger.error(f"[BROWSER_POOL] Failed to replace page: {replace_error}")
                    page = None
            
            return None
            
        finally:
            # Return page to pool
            if page and not page.is_closed():
                # Clear page state for next use
                try:
                    await page.goto('about:blank', timeout=5000)
                except:
                    pass
                await self.page_queue.put(page)
    
    async def close(self):
        """Close all pages and browser."""
        if not self.is_started:
            return
        
        logger.info(f"[BROWSER_POOL] Closing pool. Stats: {self.stats}")
        
        # Close all pages
        for page in self.pages:
            try:
                await page.close()
            except:
                pass
        
        # Close context
        if self.context:
            try:
                await self.context.close()
            except:
                pass
        
        # Stop Playwright
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
        
        # Clean up temp directory
        if self.user_data_dir and self.user_data_dir.exists():
            import shutil
            try:
                shutil.rmtree(self.user_data_dir)
            except:
                pass
        
        self.is_started = False
        logger.info("[BROWSER_POOL] Closed successfully")
    
    async def get_stats(self) -> Dict[str, any]:
        """Get pool statistics."""
        stats = self.stats.copy()
        if stats['renders'] > 0:
            stats['avg_time_ms'] = stats['total_time_ms'] // stats['renders']
        stats['pages'] = len(self.pages)
        stats['queue_size'] = self.page_queue.qsize() if self.page_queue else 0
        return stats
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Convenience function for one-off renders
async def render_with_pool(url: str, pool_size: int = 3) -> Optional[str]:
    """
    Render a single URL using a temporary pool.
    
    Args:
        url: URL to render
        pool_size: Number of pages in pool
    
    Returns:
        HTML content or None
    """
    async with PlaywrightPool(pages=pool_size) as pool:
        return await pool.render(url)