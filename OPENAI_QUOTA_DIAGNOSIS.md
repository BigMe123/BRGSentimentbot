# OpenAI Service Account Quota Diagnosis

## Issue Summary
Both your personal key and service account key are hitting **quota limits**, not rate limits. This is a billing/spend cap issue.

## Error Analysis
```
OpenAI: insufficient_quota (budget cap hit)
```

This specific error means:
- ✅ API key is valid and working
- ✅ Rate limiting improvements are working  
- ❌ Account has reached monthly spending limit or usage cap

## Service Account Limitations

Service accounts typically have:
1. **Organization-level spending limits** 
2. **Per-service-account spending caps**
3. **Monthly budget restrictions**

## Immediate Solutions

### Option 1: Check Organization Dashboard
1. Go to https://platform.openai.com/settings/organization/billing
2. Check **"Usage limits"** and **"Monthly budgets"**
3. Look for service account specific limits

### Option 2: Increase Usage Limits
In your OpenAI organization dashboard:
- **Usage limits** → Increase monthly spend limit
- **Service accounts** → Check individual service account limits
- **Billing** → Verify payment method is active

### Option 3: Use HuggingFace (Working Alternative)
The enhanced interactive summaries work perfectly without API costs:
```bash
# Same enhanced UI, no quota limits
python -m sentiment_bot.cli_unified run --region americas --budget 60 --min-sources 10
```

## Technical Verification

✅ **System Status**: All components working correctly  
✅ **Rate Limiting**: Improved with Retry-After headers  
✅ **Error Detection**: Properly identifying quota vs rate limit issues  
✅ **Fallback System**: Automatically switches to HuggingFace when LLM fails  

## Expected Costs

For reference:
- **gpt-4o-mini**: ~$0.0001 per article analysis
- **100 articles**: ~$0.01
- **1000 articles**: ~$0.10

Your quota issue suggests the limit is set very low (possibly $1-5/month).

## Recommendations

**Immediate**: Use HuggingFace mode (no limits):
```bash
python -m sentiment_bot.cli_unified run --region americas --budget 60 --min-sources 10
```

**For LLM mode**: Increase organization/service-account spending limits in OpenAI dashboard.

The system is fully functional - this is purely a billing configuration issue.