"""
Run ID generation for deterministic tracking.
"""

import hashlib
from datetime import datetime
from typing import Optional


def make_run_id(
    region: Optional[str] = None,
    topic: Optional[str] = None,
    started_at: Optional[datetime] = None,
    seed: Optional[str] = None,
) -> str:
    """
    Generate a deterministic run ID.

    Args:
        region: Target region
        topic: Target topic
        started_at: Run start time
        seed: Optional seed for reproducibility

    Returns:
        8-character run ID
    """
    if started_at is None:
        started_at = datetime.now()

    # Build deterministic string
    components = [
        region or "global",
        topic or "general",
        started_at.strftime("%Y%m%d%H%M%S"),
        seed or "",
    ]

    # Generate hash
    input_str = "|".join(components)
    hash_obj = hashlib.sha256(input_str.encode())

    # Return first 8 chars
    return hash_obj.hexdigest()[:8]
