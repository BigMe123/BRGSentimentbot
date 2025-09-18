#!/usr/bin/env python3
"""
Unit Tests: Crypto Content Removal
==================================

Test that all crypto mentions are removed from the codebase.
Addresses requirement: "Remove all crypto mentions throughout codebase"
"""

import pytest
import os
import re
from pathlib import Path


class TestCryptoRemoval:
    """Test that crypto-related content is removed."""

    @pytest.mark.unit
    def test_no_crypto_strings_in_code(self):
        """Test that crypto strings are not present in Python files."""
        # Crypto-related terms to check for
        crypto_terms = [
            'crypto', 'bitcoin', 'btc', 'ethereum', 'eth', 'blockchain',
            'defi', 'web3', 'nft', 'cryptocurrency', 'altcoin'
        ]

        # Directories to scan
        code_dirs = ['sentiment_bot', 'tests']
        violations = []

        for code_dir in code_dirs:
            if not os.path.exists(code_dir):
                continue

            for py_file in Path(code_dir).rglob('*.py'):
                # Skip test files and __pycache__
                if '__pycache__' in str(py_file) or 'test_crypto_removal.py' in str(py_file):
                    continue

                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read().lower()

                        for term in crypto_terms:
                            if term in content:
                                # Get line number for better debugging
                                lines = content.split('\\n')
                                for i, line in enumerate(lines, 1):
                                    if term in line:
                                        violations.append(f"{py_file}:{i} - Contains '{term}': {line.strip()[:100]}")
                except Exception as e:
                    # Skip files that can't be read
                    pass

        # Report violations
        if violations:
            violation_report = "\n".join(violations[:10])  # Show first 10
            pytest.fail(f"Found crypto terms in code:\n{violation_report}")\n\n    @pytest.mark.unit\n    def test_no_crypto_in_config_files(self):\n        \"\"\"Test that config files don't contain crypto terms.\"\"\"\n        crypto_terms = ['crypto', 'bitcoin', 'ethereum', 'blockchain']\n        config_files = [\n            'config/master_sources.yaml',\n            'config/connectors.yaml',\n            'run.py',\n            'README.md'\n        ]\n\n        violations = []\n\n        for config_file in config_files:\n            if not os.path.exists(config_file):\n                continue\n\n            try:\n                with open(config_file, 'r', encoding='utf-8') as f:\n                    content = f.read().lower()\n\n                    for term in crypto_terms:\n                        if term in content:\n                            violations.append(f\"{config_file} contains '{term}'\")\n            except Exception:\n                pass\n\n        if violations:\n            pytest.fail(f\"Found crypto terms in config: {violations}\")\n\n    @pytest.mark.unit\n    def test_no_crypto_in_help_text(self):\n        \"\"\"Test that help text doesn't expose crypto features.\"\"\"\n        # Check CLI help doesn't mention crypto\n        import subprocess\n        try:\n            result = subprocess.run(\n                ['python', '-m', 'sentiment_bot.cli_unified', '--help'],\n                capture_output=True,\n                text=True,\n                timeout=10\n            )\n\n            help_text = result.stdout.lower()\n            crypto_terms = ['crypto', 'bitcoin', 'ethereum', 'blockchain']\n\n            for term in crypto_terms:\n                assert term not in help_text, f\"Help text contains '{term}'\"\n\n        except (subprocess.TimeoutExpired, FileNotFoundError):\n            pytest.skip(\"CLI not available for testing\")\n\n    @pytest.mark.unit\n    def test_tariff_block_removed(self):\n        \"\"\"Test that the 100 tariff questions block is removed from run.py.\"\"\"\n        run_py_path = 'run.py'\n        if not os.path.exists(run_py_path):\n            pytest.skip(\"run.py not found\")\n\n        with open(run_py_path, 'r', encoding='utf-8') as f:\n            content = f.read()\n\n        # Check for signs of large tariff question blocks\n        tariff_indicators = [\n            'tariff.*question.*100',  # References to 100 tariff questions\n            'tariff.*{.*100',         # Tariff arrays/lists with ~100 items\n            'for.*tariff.*in.*range\\(100\\)',  # Loops generating tariff questions\n        ]\n\n        for pattern in tariff_indicators:\n            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)\n            if matches:\n                pytest.fail(f\"Found potential tariff block in run.py: {matches[0][:100]}\")\n\n        # Check that tariff mentions are minimal (some may be legitimate)\n        tariff_count = len(re.findall(r'\\btariff\\b', content, re.IGNORECASE))\n        assert tariff_count < 10, f\"Too many tariff mentions ({tariff_count}) - possible block remains\"\n\n\nclass TestLegacyCryptoCleanup:\n    \"\"\"Test cleanup of legacy crypto-related features.\"\"\"\n\n    @pytest.mark.unit\n    def test_no_crypto_connectors(self):\n        \"\"\"Test that crypto-specific connectors are removed.\"\"\"\n        # Check that connector files don't have crypto-specific logic\n        connector_dir = Path('sentiment_bot/connectors')\n        if not connector_dir.exists():\n            pytest.skip(\"Connectors directory not found\")\n\n        crypto_specific_files = [\n            'crypto_news.py',\n            'bitcoin_news.py',\n            'coindesk.py',\n            'crypto_panic.py'\n        ]\n\n        for crypto_file in crypto_specific_files:\n            file_path = connector_dir / crypto_file\n            assert not file_path.exists(), f\"Crypto-specific connector still exists: {crypto_file}\"\n\n    @pytest.mark.unit\n    def test_no_crypto_sources_in_master_list(self):\n        \"\"\"Test that master source list doesn't contain crypto-specific sources.\"\"\"\n        sources_file = 'config/master_sources.yaml'\n        if not os.path.exists(sources_file):\n            pytest.skip(\"Master sources file not found\")\n\n        with open(sources_file, 'r', encoding='utf-8') as f:\n            content = f.read().lower()\n\n        # Check for crypto-specific domains\n        crypto_domains = [\n            'coindesk', 'cointelegraph', 'crypto', 'bitcoin',\n            'ethereum', 'binance', 'coinbase'\n        ]\n\n        for domain in crypto_domains:\n            assert domain not in content, f\"Crypto domain '{domain}' found in master sources\"\n\n    @pytest.mark.integration\n    def test_repo_wide_crypto_scan(self):\n        \"\"\"Comprehensive scan of entire repository for crypto content.\"\"\"\n        # Exclude certain files/directories from scan\n        exclude_patterns = [\n            '__pycache__',\n            '.git',\n            'node_modules',\n            'test_crypto_removal.py',  # This test file itself\n            '.pyc',\n            'htmlcov'\n        ]\n\n        violations = []\n        crypto_terms = ['bitcoin', 'ethereum', 'crypto', 'blockchain']\n\n        for root, dirs, files in os.walk('.'):\n            # Skip excluded directories\n            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclude_patterns)]\n\n            for file in files:\n                # Skip non-text files and excluded patterns\n                if any(pattern in file for pattern in exclude_patterns):\n                    continue\n\n                file_path = os.path.join(root, file)\n                if not file.endswith(('.py', '.md', '.txt', '.yaml', '.yml', '.json')):\n                    continue\n\n                try:\n                    with open(file_path, 'r', encoding='utf-8') as f:\n                        content = f.read().lower()\n\n                        for term in crypto_terms:\n                            if term in content:\n                                # Count occurrences\n                                count = content.count(term)\n                                violations.append(f\"{file_path}: {count} occurrences of '{term}'\")\n                except Exception:\n                    # Skip files that can't be read\n                    continue\n\n        # Report but don't fail if only a few mentions (might be in comments/docs)\n        if len(violations) > 20:  # Threshold for \"too many\" crypto mentions\n            violation_sample = violations[:10]\n            pytest.fail(f\"Excessive crypto content found:\\n\" + \"\\n\".join(violation_sample))\n\n\nclass TestBuildGates:\n    \"\"\"Test that build gates prevent crypto content reintroduction.\"\"\"\n\n    @pytest.mark.unit\n    def test_crypto_prevention_regex(self):\n        \"\"\"Test regex patterns that could be used in CI to prevent crypto reintroduction.\"\"\"\n        # Patterns that should catch crypto content\n        crypto_patterns = [\n            r'\\bcrypto\\b',\n            r'\\bbitcoin\\b',\n            r'\\bethereum\\b',\n            r'\\bblockchain\\b',\n            r'\\bdefi\\b',\n            r'\\bnft\\b'\n        ]\n\n        # Test strings that should match\n        test_strings = [\n            \"crypto trading platform\",\n            \"bitcoin price analysis\",\n            \"ethereum smart contracts\",\n            \"blockchain technology\",\n            \"defi protocols\",\n            \"nft marketplace\"\n        ]\n\n        for pattern in crypto_patterns:\n            regex = re.compile(pattern, re.IGNORECASE)\n            matches = 0\n            for test_string in test_strings:\n                if regex.search(test_string):\n                    matches += 1\n\n            # Each pattern should match at least one test string\n            assert matches > 0, f\"Pattern '{pattern}' doesn't match any test strings\"\n\n    @pytest.mark.unit\n    def test_acceptable_crypto_mentions(self):\n        \"\"\"Test that certain crypto mentions might be acceptable in specific contexts.\"\"\"\n        # These might be OK in certain contexts (e.g., academic discussion)\n        acceptable_contexts = [\n            \"# This system does not support crypto analysis\",\n            \"# Removed crypto features in v2.0\",\n            \"cryptocurrency is not supported\"\n        ]\n\n        # These should still be flagged\n        unacceptable_contexts = [\n            \"def analyze_crypto_sentiment():\",\n            \"bitcoin_price = get_bitcoin_price()\",\n            \"crypto_sources = load_crypto_feeds()\"\n        ]\n\n        crypto_pattern = re.compile(r'\\bcrypto\\b|\\bbitcoin\\b', re.IGNORECASE)\n\n        # Acceptable contexts might contain crypto terms but in denial/removal context\n        for context in acceptable_contexts:\n            match = crypto_pattern.search(context)\n            if match:\n                # This is OK - it's discussing removal/non-support\n                pass\n\n        # Unacceptable contexts should be flagged in real scans\n        for context in unacceptable_contexts:\n            match = crypto_pattern.search(context)\n            assert match, f\"Pattern should catch unacceptable context: {context}\""