#!/usr/bin/env python3
"""
Test script to demonstrate the improvements in BSG Bot.
Shows freshness, smart selection, and increased article scraping.
"""

import subprocess
import json
import sys

def run_test(region, topic, min_sources=15):
    """Run a test and capture key metrics."""
    
    print(f"\n{'='*60}")
    print(f"Testing: {region.upper()} - {topic.upper()}")
    print(f"{'='*60}")
    
    cmd = [
        "poetry", "run", "bsgbot", "run",
        "--region", region,
        "--topic", topic,
        "--budget", "30",
        "--min-sources", str(min_sources),
        "--output", f"test_{region}_{topic}.json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    # Parse output for key metrics
    output = result.stdout
    
    # Extract metrics from output
    metrics = {}
    
    # Sources found
    if "Found" in output and "candidate sources" in output:
        for line in output.split('\n'):
            if "Found" in line and "candidate sources" in line:
                parts = line.split()
                idx = parts.index("Found")
                metrics['sources_found'] = int(parts[idx + 1])
                break
    
    # Articles fetched
    if "Kept" in output and "unique articles" in output:
        for line in output.split('\n'):
            if "unique articles" in line:
                parts = line.split('/')
                if len(parts) >= 2:
                    metrics['unique_articles'] = int(parts[0].split()[-1])
                    metrics['total_fetched'] = int(parts[1].split()[0])
                break
    
    # Freshness rate
    if "Freshness Rate:" in output:
        for line in output.split('\n'):
            if "Freshness Rate:" in line:
                rate_str = line.split("Freshness Rate:")[1].split(')')[0].strip()
                metrics['freshness_rate'] = rate_str
                # Extract fresh count
                parts = line.split('/')
                if parts:
                    metrics['fresh_articles'] = int(parts[0].split(':')[-1].strip())
                break
    
    # Fresh words
    if "Fresh words collected:" in output:
        for line in output.split('\n'):
            if "Fresh words collected:" in line:
                words = line.split(":")[-1].strip().replace(',', '')
                metrics['fresh_words'] = int(words) if words.isdigit() else 0
                break
    
    # Sentiment score
    if "Sentiment Score" in output:
        for line in output.split('\n'):
            if "│ Sentiment Score" in line:
                score_part = line.split('│')[2].strip()
                # Extract number from format like "+26" or "-15"
                import re
                match = re.search(r'[+-]?\d+', score_part)
                if match:
                    metrics['sentiment_score'] = int(match.group())
                break
    
    # Final article count
    if "relevant articles" in output:
        for line in output.split('\n'):
            if "relevant articles" in line:
                parts = line.split('/')
                if parts:
                    metrics['relevant_articles'] = int(parts[0].split()[-1])
                break
    
    return metrics

def main():
    """Run tests for different regions and topics."""
    
    tests = [
        ("asia", "elections"),
        ("asia", "tech"),
        ("europe", "economy"),
        ("europe", "climate"),
        ("middle_east", "security"),
        ("americas", "politics"),
    ]
    
    print("\n🚀 BSG Bot Enhanced Features Test")
    print("Testing freshness filtering, smart selection, and increased scraping\n")
    
    all_metrics = {}
    
    for region, topic in tests:
        try:
            metrics = run_test(region, topic)
            all_metrics[f"{region}_{topic}"] = metrics
            
            # Display results
            print(f"\n📊 Results for {region}/{topic}:")
            print(f"  Sources found: {metrics.get('sources_found', 'N/A')}")
            print(f"  Articles fetched: {metrics.get('total_fetched', 'N/A')}")
            print(f"  Unique articles: {metrics.get('unique_articles', 'N/A')}")
            print(f"  Fresh articles: {metrics.get('fresh_articles', 'N/A')}")
            print(f"  Freshness rate: {metrics.get('freshness_rate', 'N/A')}")
            print(f"  Fresh words: {metrics.get('fresh_words', 'N/A'):,}")
            print(f"  Relevant articles: {metrics.get('relevant_articles', 'N/A')}")
            print(f"  Sentiment score: {metrics.get('sentiment_score', 'N/A'):+d}" if 'sentiment_score' in metrics else "  Sentiment score: N/A")
            
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ Test timed out")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY OF IMPROVEMENTS")
    print("="*60)
    
    total_fresh_words = sum(m.get('fresh_words', 0) for m in all_metrics.values())
    avg_freshness = sum(float(m.get('freshness_rate', '0%').rstrip('%')) for m in all_metrics.values() if 'freshness_rate' in m)
    freshness_count = sum(1 for m in all_metrics.values() if 'freshness_rate' in m)
    
    print(f"✅ Total fresh words collected: {total_fresh_words:,}")
    if freshness_count > 0:
        print(f"✅ Average freshness rate: {avg_freshness/freshness_count:.1f}%")
    print(f"✅ Tests completed: {len(all_metrics)}/{len(tests)}")
    
    # Save detailed results
    with open('test_results.json', 'w') as f:
        json.dump(all_metrics, f, indent=2)
    print("\n📁 Detailed results saved to test_results.json")

if __name__ == "__main__":
    main()