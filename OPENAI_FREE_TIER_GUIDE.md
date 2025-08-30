# OpenAI Free Tier Usage Guide

## Current Issue Analysis

Your OpenAI account has $18 in credits but is hitting rate limits (HTTP 429 errors). This indicates you're likely on the **free tier** with very restrictive limits.

## OpenAI Rate Limits by Tier

| Tier | RPM (Requests/Min) | TPM (Tokens/Min) | Monthly Usage |
|------|-------------------|------------------|---------------|
| **Free** | 3 | 40,000 | $5/month |
| **Tier 1** | 500 | 40,000 | $100/month |
| **Tier 2** | 5,000 | 80,000 | $1,000/month |

## System Configuration for Free Tier

I've configured the system for free tier usage:

```bash
# .env settings optimized for free tier
LLM_CONCURRENCY=1        # Only 1 request at a time
LLM_RATE_DELAY=60        # 60 seconds between requests
```

## Recommended Usage Patterns

### 1. Very Small Batches
```bash
# Process just 2-3 articles (will take 3-4 minutes)
python -m sentiment_bot.cli_unified run --region americas --llm --budget 10 --min-sources 1

# Single source test (fastest)
python -m sentiment_bot.cli_unified run --region americas --llm --budget 5 --min-sources 1
```

### 2. Expected Timing
- **Free Tier**: 1 article per minute (60s delay)
- **10 articles**: ~10 minutes total
- **50 articles**: ~50 minutes total

### 3. Cost Estimation
- **gpt-4o-mini**: ~$0.0001 per article analysis
- **$18 credit**: ~180,000 articles (rate limits are the constraint, not cost)

## Solutions to Rate Limiting

### Option 1: Upgrade Account Tier
1. Go to https://platform.openai.com/settings/organization/billing
2. Add payment method
3. Make qualifying spend to reach Tier 1:
   - Spend $5+ to get 500 RPM (vs 3 RPM)
   - This would allow normal batch processing

### Option 2: Use Free Tier Strategically
1. Process small batches during testing
2. Use caching to avoid re-analyzing same content
3. Run overnight for larger batches

### Option 3: Alternative Models
The system supports fallback to HuggingFace (free):
```bash
# Run without --llm flag for free HuggingFace analysis
python -m sentiment_bot.cli_unified run --region americas --budget 60 --min-sources 10
```

## Current System Status

✅ **LLM System**: Fully implemented and working  
⚠️  **Rate Limits**: Free tier restrictions (3 req/min)  
✅ **Fallback**: HuggingFace models work without limits  
✅ **Caching**: Reduces duplicate API calls  

## Next Steps

**For Testing** (works now):
```bash
# Small test - 2-3 articles, ~3-4 minutes
python -m sentiment_bot.cli_unified run --region americas --llm --budget 10 --min-sources 1
```

**For Production Usage**:
1. Upgrade to Tier 1 by adding billing
2. Run normal batches: `--budget 60 --min-sources 10`

## Alternative: HuggingFace Analysis (Free)

If you want to use the enhanced interactive summaries without API limits:
```bash
# Same enhanced summaries, no API costs or rate limits
python -m sentiment_bot.cli_unified run --region americas --budget 60 --min-sources 10
```

The enhanced interactive display works with both analysis modes!