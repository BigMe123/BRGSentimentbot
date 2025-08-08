from sentiment_bot.config import load_rss_sources


def test_load_rss_sources(tmp_path, monkeypatch):
    file = tmp_path / "sources.txt"
    file.write_text(
        """# Comment line
https://example.com/feed
https://example.com/feed
https://another.com/rss
"""
    )

    urls = load_rss_sources(file)
    assert urls == [
        "https://example.com/feed",
        "https://another.com/rss",
    ]

    monkeypatch.setenv("RSS_SOURCES_FILE", str(file))
    urls_env = load_rss_sources()
    assert urls_env == urls
