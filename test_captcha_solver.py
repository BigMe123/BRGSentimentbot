#!/usr/bin/env python3
"""
Test 2Captcha integration with stealth harvester
"""

import asyncio
from sentiment_bot.stealth_harvester import StealthHarvester


async def test_captcha_sites():
    """Test sites known to have CAPTCHAs"""

    print("🔐 TESTING CAPTCHA SOLVER INTEGRATION")
    print("=" * 50)

    harvester = StealthHarvester(db_path=".captcha_test_db.json")

    if not harvester.captcha_solver:
        print("❌ 2Captcha not initialized!")
        return

    print("✅ 2Captcha solver initialized with API key")
    print(f"   API Key: ad21dba743...")  # Hardcoded for display

    # Check balance
    try:
        balance = harvester.captcha_solver.balance()
        print(f"💰 2Captcha Balance: ${balance}")

        if float(balance) < 1.0:
            print("⚠️ Low balance! Add funds to your 2Captcha account")
    except Exception as e:
        print(f"⚠️ Could not check balance: {e}")

    # Test sites that might have CAPTCHAs
    test_sites = [
        "linkedin.com",  # Often has CAPTCHA
        "twitter.com",  # Sometimes has CAPTCHA
        "facebook.com",  # Login pages have CAPTCHA
    ]

    print("\n📋 Testing CAPTCHA-protected sites:")
    print("-" * 50)

    for site in test_sites:
        print(f"\n🎯 Testing {site}...")

        try:
            # This will use browser mode and attempt CAPTCHA solving
            record = await harvester.discover_from_domain(site)

            if record:
                print(f"✅ Successfully accessed {site}")
                if record.protection_level in ["advanced", "fortress"]:
                    print(f"   🛡️ Protection level: {record.protection_level}")
                    if record.bypass_method == "captcha_solver":
                        print(f"   🔓 CAPTCHA bypass successful!")
            else:
                print(f"❌ Could not access {site}")

        except Exception as e:
            print(f"⚠️ Error testing {site}: {str(e)[:100]}")

    await harvester.close()

    print("\n" + "=" * 50)
    print("✅ CAPTCHA SOLVER TEST COMPLETE")


async def test_specific_captcha():
    """Test a specific URL known to have CAPTCHA"""

    url = input("Enter URL with CAPTCHA to test (or press Enter to skip): ").strip()

    if not url:
        print("Skipping specific test")
        return

    harvester = StealthHarvester(db_path=".captcha_specific_test.json")

    print(f"\n🔐 Testing CAPTCHA solving for: {url}")

    # Force browser mode for CAPTCHA sites
    content = await harvester._stealth_get(url, use_browser=True)

    if content:
        print("✅ Successfully retrieved content after CAPTCHA!")
        print(f"   Content length: {len(content)} characters")
    else:
        print("❌ Failed to retrieve content")

    await harvester.close()


if __name__ == "__main__":
    print("\n🤖 2CAPTCHA INTEGRATION TEST")
    print("=" * 50)
    print("Your API key is configured and ready to solve CAPTCHAs")
    print("\nChoose test mode:")
    print("1. Test known CAPTCHA sites")
    print("2. Test specific URL")
    print("3. Both")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == "1":
        asyncio.run(test_captcha_sites())
    elif choice == "2":
        asyncio.run(test_specific_captcha())
    elif choice == "3":
        asyncio.run(test_captcha_sites())
        asyncio.run(test_specific_captcha())
    else:
        print("Invalid choice")
