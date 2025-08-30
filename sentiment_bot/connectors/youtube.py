"""YouTube RSS connector with channel/query fan-out."""

import asyncio
import aiohttp
import re
from typing import AsyncIterator, Dict, Any, List, Optional
from xml.etree import ElementTree
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class YouTubeConnector(Connector):
    """Fetch videos from YouTube channels with fan-out."""

    name = "youtube"

    def __init__(
        self,
        channels: List[str] = None,
        search_queries: List[str] = None,
        fetch_transcript: bool = False,
        fetch_comments: bool = False,
        max_per_channel: int = 50,
        delay_ms: int = 500,
        **kwargs,
    ):
        """
        Initialize YouTube connector.

        Args:
            channels: Channel IDs or handles (fan-out)
            search_queries: Search queries (limited RSS support)
            fetch_transcript: Whether to fetch video transcripts (experimental)
            fetch_comments: Whether to fetch comments (not implemented)
            max_per_channel: Max videos per channel
            delay_ms: Delay between channel requests in milliseconds
        """
        super().__init__(**kwargs)
        self.channels = channels or []
        self.search_queries = search_queries or []
        self.fetch_transcript = fetch_transcript
        self.fetch_comments = fetch_comments
        self.max_per_channel = max_per_channel
        self.delay_ms = delay_ms

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch videos from YouTube - channel fan-out."""

        headers = {"User-Agent": "BSGBOT/1.0 (+https://github.com/BigMe123/BSGBOT)"}

        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            # Channel fan-out - one request per channel
            for channel in self.channels:
                try:
                    async for item in self._fetch_channel(session, channel):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to fetch YouTube channel {channel}: {e}")
                    continue

                # Rate limiting between channels
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

            # Note: YouTube search RSS is very limited, consider disabling
            for query in self.search_queries:
                try:
                    async for item in self._fetch_search(session, query):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to fetch YouTube search '{query}': {e}")
                    continue

                # Rate limiting between search queries
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

    async def _fetch_channel(
        self, session: aiohttp.ClientSession, channel: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch videos from a YouTube channel."""

        # Handle both channel IDs and @handles
        if channel.startswith("@"):
            # Convert handle to channel ID (simplified - may need actual lookup)
            channel_id = channel
        elif channel.startswith("UC"):
            channel_id = channel
        else:
            channel_id = f"UC{channel}"  # Assume it's a partial ID

        # RSS feed URL
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        logger.info(f"Fetching YouTube channel: {channel}")

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"YouTube RSS returned {resp.status} for {channel}")
                    return

                content = await resp.text()
                root = ElementTree.fromstring(content)

                # Parse RSS entries
                ns = {
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                    "media": "http://search.yahoo.com/mrss/",
                    "": "http://www.w3.org/2005/Atom",
                }

                entries = root.findall(".//entry", ns)[: self.max_per_channel]

                for entry in entries:
                    try:
                        video_id = entry.find("yt:videoId", ns).text
                        title = entry.find("title", ns).text
                        author = entry.find("author/name", ns).text
                        published = entry.find("published", ns).text

                        # Get description
                        desc_elem = entry.find("media:group/media:description", ns)
                        description = desc_elem.text if desc_elem is not None else ""

                        # Build text content
                        text_parts = [title, description]

                        # Fetch transcript if requested (experimental)
                        if self.fetch_transcript:
                            transcript = await self._fetch_transcript(session, video_id)
                            if transcript:
                                text_parts.append(f"\n\nTranscript:\n{transcript}")

                        yield {
                            "id": make_id(self.name, video_id),
                            "source": self.name,
                            "subsource": channel,
                            "author": author,
                            "title": title,
                            "text": clean_text("\n\n".join(text_parts)),
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "published_at": parse_date(published),
                            "lang": "en",
                            "raw": {"video_id": video_id, "channel": channel},
                        }

                    except Exception as e:
                        logger.warning(f"Failed to process YouTube entry: {e}")
                        continue

                logger.info(
                    f"Fetched {len(entries)} videos from YouTube channel: {channel}"
                )

        except Exception as e:
            logger.error(f"Failed to fetch YouTube channel RSS: {e}")

    async def _fetch_search(
        self, session: aiohttp.ClientSession, query: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch videos from YouTube search (limited RSS support)."""

        logger.warning(
            f"YouTube search RSS is very limited and may not return recent results. Query: {query}"
        )

        # YouTube doesn't provide a good RSS search endpoint
        # Would need to use YouTube Data API v3 for proper search
        # For now, return empty to avoid false expectations
        return
        yield  # Make it a generator

    async def _fetch_transcript(
        self, session: aiohttp.ClientSession, video_id: str
    ) -> Optional[str]:
        """Fetch video transcript."""

        try:
            # Try to get transcript via direct API
            # Note: This is a simplified approach - for production use youtube-transcript-api
            url = f"https://www.youtube.com/watch?v={video_id}"

            async with session.get(url) as resp:
                if resp.status != 200:
                    return None

                html = await resp.text()

                # Extract captions URL from HTML (simplified)
                match = re.search(
                    r'"captions":\{"playerCaptionsTracklistRenderer":\{"captionTracks":\[(\{[^]]+\})',
                    html,
                )
                if not match:
                    return None

                # For now, transcript fetching is experimental and disabled
                # In production, would need to parse the captions JSON and fetch the actual transcript
                # Consider using youtube-transcript-api library
                return None

        except Exception as e:
            logger.debug(f"Failed to fetch transcript for {video_id}: {e}")
            return None
