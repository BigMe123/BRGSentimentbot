#!/usr/bin/env python3
"""BRG Sentiment Analysis Platform - Main Launcher."""

import sys

def main():
    from sentiment_bot.cli_unified import app
    app()

if __name__ == "__main__":
    main()
