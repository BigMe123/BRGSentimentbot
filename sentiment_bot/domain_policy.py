"""
Domain policy registry for governance and compliance.
Implements Phase 6 of the performance optimization plan.
"""

import json
import yaml
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)


@dataclass
class DomainPolicy:
    """Policy configuration for a domain."""
    domain: str
    status: str = 'allowed'  # 'allowed', 'deny', 'api_only', 'js_allowed'
    respect_robots: bool = True
    max_docs_per_run: int = 10
    max_bytes: int = 2_621_440  # 2.5MB
    rate_limit_ms: int = 100  # Min delay between requests
    custom_headers: Dict[str, str] = field(default_factory=dict)
    api_endpoint: Optional[str] = None
    notes: str = ""


class DomainPolicyRegistry:
    """
    Manages domain-specific policies for fetching.
    
    Features:
    - Allow/deny lists
    - JS rendering allowlist
    - Robots.txt respect flags
    - Per-domain rate limits and caps
    - API-only routing
    """
    
    DEFAULT_POLICIES = {
        # Major news sites - allowed with standard settings
        'feeds.bbci.co.uk': DomainPolicy(
            domain='feeds.bbci.co.uk',
            status='allowed',
            max_docs_per_run=20,
        ),
        'rss.nytimes.com': DomainPolicy(
            domain='rss.nytimes.com',
            status='allowed',
            max_docs_per_run=20,
        ),
        'feeds.reuters.com': DomainPolicy(
            domain='feeds.reuters.com',
            status='allowed',
            max_docs_per_run=20,
        ),
        
        # Sites requiring JS rendering
        'www.bloomberg.com': DomainPolicy(
            domain='www.bloomberg.com',
            status='js_allowed',
            max_docs_per_run=10,
            rate_limit_ms=500,
            notes='Heavy JS, requires rendering'
        ),
        'www.wsj.com': DomainPolicy(
            domain='www.wsj.com',
            status='js_allowed',
            max_docs_per_run=10,
            rate_limit_ms=500,
        ),
        
        # Problematic domains - deny or limit
        'example-spam.com': DomainPolicy(
            domain='example-spam.com',
            status='deny',
            notes='Known spam source'
        ),
        
        # API-only access
        'api.example.com': DomainPolicy(
            domain='api.example.com',
            status='api_only',
            api_endpoint='https://api.example.com/v1/articles',
            custom_headers={'X-API-Key': 'YOUR_KEY_HERE'},
        ),
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.policies: Dict[str, DomainPolicy] = {}
        self.pattern_policies: List[Tuple[re.Pattern, DomainPolicy]] = []
        
        # Stats
        self.stats = {
            'allowed': 0,
            'denied': 0,
            'api_only': 0,
            'js_allowed': 0,
            'robots_denied': 0,
            'policy_denied': 0,
        }
        
        # Load policies
        self._load_default_policies()
        if config_path and config_path.exists():
            self._load_config_file(config_path)
    
    def _load_default_policies(self):
        """Load default domain policies."""
        for domain, policy in self.DEFAULT_POLICIES.items():
            self.policies[domain] = policy
    
    def _load_config_file(self, path: Path):
        """Load policies from YAML or JSON config file."""
        try:
            content = path.read_text()
            
            if path.suffix in ('.yaml', '.yml'):
                data = yaml.safe_load(content)
            elif path.suffix == '.json':
                data = json.loads(content)
            else:
                logger.warning(f"Unknown config format: {path}")
                return
            
            # Load domain policies
            for domain_config in data.get('domains', []):
                domain = domain_config.get('domain')
                if not domain:
                    continue
                
                policy = DomainPolicy(
                    domain=domain,
                    status=domain_config.get('status', 'allowed'),
                    respect_robots=domain_config.get('respect_robots', True),
                    max_docs_per_run=domain_config.get('max_docs_per_run', 10),
                    max_bytes=domain_config.get('max_bytes', 2_621_440),
                    rate_limit_ms=domain_config.get('rate_limit_ms', 100),
                    custom_headers=domain_config.get('custom_headers', {}),
                    api_endpoint=domain_config.get('api_endpoint'),
                    notes=domain_config.get('notes', ''),
                )
                
                # Support wildcards as patterns
                if '*' in domain:
                    pattern = re.compile(domain.replace('*', '.*'))
                    self.pattern_policies.append((pattern, policy))
                else:
                    self.policies[domain] = policy
            
            logger.info(f"Loaded {len(self.policies)} domain policies from {path}")
            
        except Exception as e:
            logger.error(f"Error loading config from {path}: {e}")
    
    def get_policy(self, url: str) -> DomainPolicy:
        """
        Get policy for a URL.
        
        Returns the most specific matching policy or a default policy.
        """
        domain = urlparse(url).netloc
        
        # Check exact match
        if domain in self.policies:
            return self.policies[domain]
        
        # Check pattern matches
        for pattern, policy in self.pattern_policies:
            if pattern.match(domain):
                return policy
        
        # Return default policy
        return DomainPolicy(domain=domain)
    
    def check_access(self, url: str) -> Tuple[str, Optional[str]]:
        """
        Check if URL access is allowed.
        
        Returns:
            Tuple of (decision, reason)
            decision: 'allow', 'deny', 'api_only', 'js_required'
            reason: Optional explanation
        """
        policy = self.get_policy(url)
        
        if policy.status == 'deny':
            self.stats['denied'] += 1
            self.stats['policy_denied'] += 1
            return 'deny', f"Domain denied by policy: {policy.notes}"
        
        if policy.status == 'api_only':
            self.stats['api_only'] += 1
            return 'api_only', f"API-only access: {policy.api_endpoint}"
        
        if policy.status == 'js_allowed':
            self.stats['js_allowed'] += 1
            return 'js_required', "JS rendering allowed for domain"
        
        self.stats['allowed'] += 1
        return 'allow', None
    
    def check_robots(self, url: str, robots_txt: Optional[str] = None) -> bool:
        """
        Check if robots.txt should be respected for this domain.
        
        Returns:
            True if robots should be respected
        """
        policy = self.get_policy(url)
        
        if not policy.respect_robots:
            logger.debug(f"Robots.txt bypassed for {url} by policy")
            return False
        
        # TODO: Parse robots.txt and check if URL is allowed
        # For now, just return the policy setting
        return policy.respect_robots
    
    def get_rate_limit(self, url: str) -> int:
        """Get rate limit in milliseconds for domain."""
        policy = self.get_policy(url)
        return policy.rate_limit_ms
    
    def get_custom_headers(self, url: str) -> Dict[str, str]:
        """Get custom headers for domain."""
        policy = self.get_policy(url)
        return policy.custom_headers
    
    def get_limits(self, url: str) -> Dict[str, int]:
        """Get fetch limits for domain."""
        policy = self.get_policy(url)
        return {
            'max_docs': policy.max_docs_per_run,
            'max_bytes': policy.max_bytes,
        }
    
    def export_stats(self) -> Dict[str, Any]:
        """Export registry statistics."""
        return {
            'policies_loaded': len(self.policies),
            'pattern_policies': len(self.pattern_policies),
            **self.stats
        }
    
    def save_config(self, path: Path):
        """Save current policies to config file."""
        data = {
            'domains': [
                {
                    'domain': policy.domain,
                    'status': policy.status,
                    'respect_robots': policy.respect_robots,
                    'max_docs_per_run': policy.max_docs_per_run,
                    'max_bytes': policy.max_bytes,
                    'rate_limit_ms': policy.rate_limit_ms,
                    'custom_headers': policy.custom_headers,
                    'api_endpoint': policy.api_endpoint,
                    'notes': policy.notes,
                }
                for policy in self.policies.values()
            ]
        }
        
        if path.suffix in ('.yaml', '.yml'):
            path.write_text(yaml.dump(data, default_flow_style=False))
        else:
            path.write_text(json.dumps(data, indent=2))
        
        logger.info(f"Saved {len(self.policies)} policies to {path}")


# Global registry instance
_global_registry: Optional[DomainPolicyRegistry] = None


def get_domain_registry(config_path: Optional[Path] = None) -> DomainPolicyRegistry:
    """Get or create the global domain policy registry."""
    global _global_registry
    
    if _global_registry is None:
        # Try to load from default locations
        if config_path is None:
            for path in [
                Path('domain_policies.yaml'),
                Path('domain_policies.json'),
                Path.home() / '.config' / 'bsgbot' / 'domain_policies.yaml',
            ]:
                if path.exists():
                    config_path = path
                    break
        
        _global_registry = DomainPolicyRegistry(config_path)
    
    return _global_registry


# Example config file content
EXAMPLE_CONFIG = """
# domain_policies.yaml
domains:
  - domain: feeds.bbci.co.uk
    status: allowed
    max_docs_per_run: 20
    respect_robots: true
    
  - domain: www.bloomberg.com
    status: js_allowed
    max_docs_per_run: 10
    rate_limit_ms: 500
    notes: Requires JS rendering for content
    
  - domain: spam-site.example.com
    status: deny
    notes: Known spam source
    
  - domain: api.newsapi.org
    status: api_only
    api_endpoint: https://api.newsapi.org/v2/everything
    custom_headers:
      X-API-Key: YOUR_API_KEY
    
  - domain: "*.government.gov"
    status: allowed
    respect_robots: false
    notes: Government sites - public information
"""