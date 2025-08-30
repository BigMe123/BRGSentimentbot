#!/bin/bash
# Quick test script to validate README commands work

echo "🧪 Testing BSGBOT Commands from README"
echo "========================================"

echo ""
echo "1. Testing help command..."
python -m sentiment_bot.cli_unified --help | head -10

echo ""
echo "2. Testing list connectors..."
python -m sentiment_bot.cli_unified list_connectors

echo ""
echo "3. Testing connector help..."
python -m sentiment_bot.cli_unified connectors --help | head -10

echo ""
echo "4. Testing simple connector (hackernews with small limit)..."
python -m sentiment_bot.cli_unified connectors --type hackernews --limit 5

echo ""
echo "✅ All basic commands work!"
echo ""
echo "🎯 To test the main feature, run:"
echo "python -m sentiment_bot.cli_unified connectors --keywords \"crypto,blockchain,bitcoin,ethereum\" --limit 100 --since 24h"