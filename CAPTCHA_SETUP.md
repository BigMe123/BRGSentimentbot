# 🔐 CAPTCHA Solver Integration Complete

## ✅ What's Configured

1. **2Captcha API Key**: `ad21dba743166099eabb775dfa61a09e`
   - Hardcoded in `sentiment_bot/stealth_harvester.py`
   - Automatically initializes when harvester starts

2. **Supported CAPTCHA Types**:
   - ✅ **reCAPTCHA v2** - Standard checkbox CAPTCHA
   - ✅ **reCAPTCHA v3** - Invisible score-based CAPTCHA
   - ✅ **hCaptcha** - Privacy-focused alternative to reCAPTCHA
   - 🔄 **Cloudflare** - Detected but requires manual handling

3. **How It Works**:
   - Detects CAPTCHA presence automatically
   - Extracts site key from the page
   - Sends to 2Captcha service for solving
   - Injects solution back into the page
   - Submits form automatically

## ⚠️ Important: Add Funds

Your 2Captcha balance is currently **$0.00**. To use CAPTCHA solving:

1. Go to https://2captcha.com
2. Log into your account
3. Add funds (minimum $3 recommended)
4. CAPTCHAs cost approximately:
   - reCAPTCHA v2: $2.99 per 1000
   - reCAPTCHA v3: $2.99 per 1000
   - hCaptcha: $2.99 per 1000

## 🚀 Usage Examples

### Basic Usage
```bash
# Harvest sites with automatic CAPTCHA solving
python sentiment_bot/stealth_harvester.py --seeds config/protected_sites.txt
```

### Test CAPTCHA Solver
```bash
# Test the integration
python test_captcha_solver.py
```

### In Your Code
```python
from sentiment_bot.stealth_harvester import StealthHarvester

harvester = StealthHarvester()
# Will automatically solve CAPTCHAs when encountered
record = await harvester.discover_from_domain("linkedin.com")
```

## 🛡️ Sites That Often Have CAPTCHAs

- **Social Media**: LinkedIn, Twitter, Facebook, Instagram
- **News Sites**: WSJ (paywall), Bloomberg (anti-bot)
- **E-commerce**: Amazon, eBay (when scraping)
- **Search Engines**: Google (after many queries)

## 📊 Success Tracking

The harvester now tracks:
- Protection level detected
- Bypass method used
- Success rate per domain
- Whether CAPTCHA was solved

Check the database file to see which sites required CAPTCHA solving:
```bash
cat .stealth_harvest_db.json | grep captcha_solver
```

## 🔧 Troubleshooting

1. **"No balance" error**: Add funds to 2Captcha
2. **"Wrong site key"**: Site may have changed, needs manual check
3. **"Timeout"**: CAPTCHA solving can take 10-60 seconds
4. **"Invalid API key"**: Check key is correct in stealth_harvester.py

## 🎯 Next Steps

1. **Add funds** to your 2Captcha account
2. **Test** with a known CAPTCHA site:
   ```bash
   python sentiment_bot/stealth_harvester.py --seed linkedin.com
   ```
3. **Monitor** success rates in the database
4. **Adjust** retry logic if needed

The stealth harvester will now automatically bypass CAPTCHAs when it encounters them, giving you access to heavily protected news sources!