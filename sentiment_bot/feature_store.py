#!/usr/bin/env python
"""
Feature Store with Timestamped Snapshots
========================================
Reproducible feature storage with versioning and data lineage
"""

import os
import json
import hashlib
import logging
import numpy as np
import pandas as pd
import pickle
import gzip
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class FeatureSnapshot:
    """Feature snapshot with metadata"""
    timestamp: datetime
    feature_name: str
    value: Any
    data_type: str
    source: str
    version: str
    git_sha: Optional[str] = None
    dependencies: List[str] = None
    lag_applied: int = 0  # Lag in days
    ttl_hours: int = 24
    checksum: Optional[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.checksum is None:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """Calculate checksum for data integrity"""
        # Convert value to string for hashing
        if isinstance(self.value, (dict, list)):
            value_str = json.dumps(self.value, sort_keys=True, default=str)
        elif isinstance(self.value, pd.DataFrame):
            value_str = self.value.to_json()
        elif isinstance(self.value, pd.Series):
            value_str = self.value.to_json()
        elif isinstance(self.value, np.ndarray):
            value_str = str(self.value.tolist())
        else:
            value_str = str(self.value)

        return hashlib.sha256(value_str.encode()).hexdigest()[:16]

    def is_stale(self) -> bool:
        """Check if feature is stale"""
        age_hours = (datetime.now() - self.timestamp).total_seconds() / 3600
        return age_hours > self.ttl_hours

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'FeatureSnapshot':
        """Create from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class FeatureVersioning:
    """Handle feature versioning and lineage"""

    def __init__(self):
        self.current_version = self._get_current_version()

    def _get_current_version(self) -> str:
        """Get current system version"""
        # Try to get git SHA
        try:
            import subprocess
            git_sha = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return f"git-{git_sha}"
        except:
            # Fallback to timestamp-based version
            return f"v{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def get_feature_version(self, feature_name: str, dependencies: List[str] = None) -> str:
        """Generate feature version including dependencies"""
        if dependencies:
            dep_hash = hashlib.md5(','.join(sorted(dependencies)).encode()).hexdigest()[:8]
            return f"{self.current_version}-{dep_hash}"
        return self.current_version


class FeatureStorage:
    """Storage backend for features"""

    def __init__(self, storage_dir: str = "features"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (self.storage_dir / "snapshots").mkdir(exist_ok=True)
        (self.storage_dir / "metadata").mkdir(exist_ok=True)
        (self.storage_dir / "lineage").mkdir(exist_ok=True)

    def _get_snapshot_path(self, feature_name: str, timestamp: datetime) -> Path:
        """Get path for feature snapshot"""
        date_prefix = timestamp.strftime('%Y/%m/%d')
        filename = f"{feature_name}_{timestamp.strftime('%H%M%S')}_{timestamp.microsecond // 1000:03d}.parquet.gz"
        path = self.storage_dir / "snapshots" / date_prefix
        path.mkdir(parents=True, exist_ok=True)
        return path / filename

    def _get_metadata_path(self, feature_name: str, timestamp: datetime) -> Path:
        """Get path for metadata"""
        date_prefix = timestamp.strftime('%Y/%m/%d')
        filename = f"{feature_name}_{timestamp.strftime('%H%M%S')}_{timestamp.microsecond // 1000:03d}.json"
        path = self.storage_dir / "metadata" / date_prefix
        path.mkdir(parents=True, exist_ok=True)
        return path / filename

    def store_feature(self, snapshot: FeatureSnapshot) -> bool:
        """Store feature snapshot"""
        try:
            # Store data based on type
            data_path = self._get_snapshot_path(snapshot.feature_name, snapshot.timestamp)

            if isinstance(snapshot.value, pd.DataFrame):
                # Store DataFrame as compressed parquet
                snapshot.value.to_parquet(data_path, compression='gzip')
            elif isinstance(snapshot.value, pd.Series):
                # Convert Series to DataFrame and store
                df = pd.DataFrame({snapshot.feature_name: snapshot.value})
                df.to_parquet(data_path, compression='gzip')
            elif isinstance(snapshot.value, (dict, list)):
                # Store JSON data as compressed pickle
                with gzip.open(data_path.with_suffix('.pkl.gz'), 'wb') as f:
                    pickle.dump(snapshot.value, f)
            else:
                # Store other types as compressed pickle
                with gzip.open(data_path.with_suffix('.pkl.gz'), 'wb') as f:
                    pickle.dump(snapshot.value, f)

            # Store metadata
            metadata_path = self._get_metadata_path(snapshot.feature_name, snapshot.timestamp)
            metadata = snapshot.to_dict()
            metadata.pop('value', None)  # Don't duplicate value in metadata

            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2, default=str)

            logger.debug(f"Stored feature {snapshot.feature_name} at {snapshot.timestamp}")
            return True

        except Exception as e:
            logger.error(f"Failed to store feature {snapshot.feature_name}: {e}")
            return False

    def load_feature(self, feature_name: str, timestamp: datetime) -> Optional[FeatureSnapshot]:
        """Load specific feature snapshot"""
        try:
            # Load metadata first
            metadata_path = self._get_metadata_path(feature_name, timestamp)
            if not metadata_path.exists():
                return None

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            # Load data
            data_path = self._get_snapshot_path(feature_name, timestamp)

            if data_path.with_suffix('.parquet.gz').exists():
                # Load parquet
                value = pd.read_parquet(data_path.with_suffix('.parquet.gz'))
                if len(value.columns) == 1 and value.columns[0] == feature_name:
                    value = value[feature_name]  # Convert back to Series if it was originally
            elif data_path.with_suffix('.pkl.gz').exists():
                # Load pickle
                with gzip.open(data_path.with_suffix('.pkl.gz'), 'rb') as f:
                    value = pickle.load(f)
            else:
                logger.warning(f"No data file found for {feature_name} at {timestamp}")
                return None

            # Reconstruct snapshot
            metadata['value'] = value
            return FeatureSnapshot.from_dict(metadata)

        except Exception as e:
            logger.error(f"Failed to load feature {feature_name} at {timestamp}: {e}")
            return None

    def list_feature_snapshots(self,
                             feature_name: str,
                             start_date: datetime = None,
                             end_date: datetime = None) -> List[datetime]:
        """List available snapshots for a feature"""
        snapshots = []

        # Search through date directories
        snapshots_dir = self.storage_dir / "snapshots"

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        current_date = start_date.date()
        while current_date <= end_date.date():
            date_dir = snapshots_dir / current_date.strftime('%Y/%m/%d')

            if date_dir.exists():
                for file_path in date_dir.iterdir():
                    if file_path.name.startswith(f"{feature_name}_"):
                        # Parse timestamp from filename
                        try:
                            time_part = file_path.stem.split('_')[1]  # Remove extensions
                            if '.' in time_part:
                                time_part = time_part.split('.')[0]

                            timestamp = datetime.combine(
                                current_date,
                                datetime.strptime(time_part[:6], '%H%M%S').time()
                            )

                            # Add microseconds if present
                            if len(time_part) > 6:
                                microseconds = int(time_part[6:]) * 1000
                                timestamp = timestamp.replace(microsecond=microseconds)

                            if start_date <= timestamp <= end_date:
                                snapshots.append(timestamp)
                        except ValueError:
                            continue

            current_date += timedelta(days=1)

        return sorted(snapshots)


class FeatureLineage:
    """Track feature lineage and dependencies"""

    def __init__(self, db_path: str = "features/lineage.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize lineage database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_lineage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    feature_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source TEXT NOT NULL,
                    dependencies TEXT,  -- JSON array
                    data_sources TEXT,  -- JSON array
                    transformation_code TEXT,
                    git_sha TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_lineage_feature_time
                ON feature_lineage(feature_name, timestamp)
            """)

    def record_feature_creation(self,
                               feature_name: str,
                               timestamp: datetime,
                               version: str,
                               source: str,
                               dependencies: List[str] = None,
                               data_sources: List[str] = None,
                               transformation_code: str = None,
                               git_sha: str = None):
        """Record feature creation in lineage"""

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feature_lineage (
                    timestamp, feature_name, version, source,
                    dependencies, data_sources, transformation_code, git_sha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp.isoformat(),
                feature_name,
                version,
                source,
                json.dumps(dependencies or []),
                json.dumps(data_sources or []),
                transformation_code,
                git_sha
            ))

    def get_feature_lineage(self, feature_name: str, timestamp: datetime = None) -> Dict:
        """Get lineage information for a feature"""

        query = """
            SELECT * FROM feature_lineage
            WHERE feature_name = ?
        """
        params = [feature_name]

        if timestamp:
            query += " AND timestamp <= ?"
            params.append(timestamp.isoformat())

        query += " ORDER BY timestamp DESC LIMIT 1"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            row = cursor.fetchone()

            if row:
                result = dict(row)
                result['dependencies'] = json.loads(result['dependencies'])
                result['data_sources'] = json.loads(result['data_sources'])
                return result

        return {}


class ReproducibleFeatureStore:
    """Main feature store with reproducibility guarantees"""

    def __init__(self, storage_dir: str = "features"):
        self.storage = FeatureStorage(storage_dir)
        self.versioning = FeatureVersioning()
        self.lineage = FeatureLineage(f"{storage_dir}/lineage.db")

        # Current session features (in-memory cache)
        self.session_features: Dict[str, FeatureSnapshot] = {}

    def create_feature(self,
                      feature_name: str,
                      value: Any,
                      source: str,
                      dependencies: List[str] = None,
                      data_sources: List[str] = None,
                      lag_days: int = 0,
                      ttl_hours: int = 24,
                      transformation_code: str = None) -> bool:
        """Create and store a feature with full lineage"""

        timestamp = datetime.now()

        # Apply lag if specified
        if lag_days > 0:
            timestamp = timestamp - timedelta(days=lag_days)

        # Determine data type
        if isinstance(value, pd.DataFrame):
            data_type = 'dataframe'
        elif isinstance(value, pd.Series):
            data_type = 'series'
        elif isinstance(value, (dict, list)):
            data_type = 'json'
        elif isinstance(value, (int, float)):
            data_type = 'numeric'
        else:
            data_type = 'object'

        # Generate version
        version = self.versioning.get_feature_version(feature_name, dependencies)

        # Create snapshot
        snapshot = FeatureSnapshot(
            timestamp=timestamp,
            feature_name=feature_name,
            value=value,
            data_type=data_type,
            source=source,
            version=version,
            git_sha=self.versioning.current_version,
            dependencies=dependencies or [],
            lag_applied=lag_days,
            ttl_hours=ttl_hours
        )

        # Store feature
        success = self.storage.store_feature(snapshot)

        if success:
            # Record lineage
            self.lineage.record_feature_creation(
                feature_name=feature_name,
                timestamp=timestamp,
                version=version,
                source=source,
                dependencies=dependencies,
                data_sources=data_sources,
                transformation_code=transformation_code,
                git_sha=self.versioning.current_version
            )

            # Cache in session
            self.session_features[feature_name] = snapshot

            logger.info(f"Created feature {feature_name} with version {version}")

        return success

    def get_feature(self,
                   feature_name: str,
                   as_of_date: datetime = None,
                   max_age_hours: int = None) -> Optional[FeatureSnapshot]:
        """Get feature with temporal consistency"""

        # Check session cache first
        if as_of_date is None and feature_name in self.session_features:
            cached = self.session_features[feature_name]
            if max_age_hours is None or not cached.is_stale():
                return cached

        # Search storage
        if as_of_date is None:
            as_of_date = datetime.now()

        # Get available snapshots
        snapshots = self.storage.list_feature_snapshots(
            feature_name,
            start_date=as_of_date - timedelta(days=7),  # Search last week
            end_date=as_of_date
        )

        if not snapshots:
            logger.warning(f"No snapshots found for feature {feature_name}")
            return None

        # Find best snapshot (latest before as_of_date)
        valid_snapshots = [ts for ts in snapshots if ts <= as_of_date]

        if not valid_snapshots:
            logger.warning(f"No valid snapshots for {feature_name} before {as_of_date}")
            return None

        best_timestamp = max(valid_snapshots)

        # Check age constraint
        if max_age_hours:
            age_hours = (as_of_date - best_timestamp).total_seconds() / 3600
            if age_hours > max_age_hours:
                logger.warning(f"Best snapshot for {feature_name} is {age_hours:.1f}h old (max: {max_age_hours}h)")
                return None

        # Load snapshot
        return self.storage.load_feature(feature_name, best_timestamp)

    def get_feature_batch(self,
                         feature_names: List[str],
                         as_of_date: datetime = None) -> Dict[str, FeatureSnapshot]:
        """Get multiple features consistently"""

        result = {}
        for feature_name in feature_names:
            snapshot = self.get_feature(feature_name, as_of_date)
            if snapshot:
                result[feature_name] = snapshot

        return result

    def create_feature_point_in_time(self,
                                   feature_names: List[str],
                                   as_of_date: datetime) -> pd.DataFrame:
        """Create point-in-time feature matrix"""

        features_data = []
        available_features = []

        batch = self.get_feature_batch(feature_names, as_of_date)

        for feature_name in feature_names:
            if feature_name in batch:
                snapshot = batch[feature_name]

                if isinstance(snapshot.value, (pd.Series, pd.DataFrame)):
                    # Use most recent value
                    if isinstance(snapshot.value, pd.Series):
                        value = snapshot.value.iloc[-1] if len(snapshot.value) > 0 else np.nan
                    else:
                        value = snapshot.value.iloc[-1, 0] if len(snapshot.value) > 0 else np.nan
                elif isinstance(snapshot.value, (int, float)):
                    value = snapshot.value
                else:
                    value = str(snapshot.value)

                features_data.append(value)
                available_features.append(feature_name)
            else:
                logger.warning(f"Feature {feature_name} not available as of {as_of_date}")

        if available_features:
            return pd.DataFrame([features_data], columns=available_features, index=[as_of_date])
        else:
            return pd.DataFrame()

    def get_reproducibility_report(self, feature_names: List[str] = None) -> Dict:
        """Generate reproducibility report"""

        if feature_names is None:
            # Get all features from recent session
            feature_names = list(self.session_features.keys())

        report = {
            'generated_at': datetime.now().isoformat(),
            'system_version': self.versioning.current_version,
            'features': {}
        }

        for feature_name in feature_names:
            lineage = self.lineage.get_feature_lineage(feature_name)
            snapshots = self.storage.list_feature_snapshots(
                feature_name,
                start_date=datetime.now() - timedelta(days=7)
            )

            report['features'][feature_name] = {
                'available_snapshots': len(snapshots),
                'latest_snapshot': snapshots[-1].isoformat() if snapshots else None,
                'lineage': lineage,
                'dependencies': lineage.get('dependencies', []),
                'data_sources': lineage.get('data_sources', [])
            }

        return report

    def cleanup_old_features(self, days_to_keep: int = 30):
        """Clean up old feature snapshots"""

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cleanup_count = 0

        snapshots_dir = self.storage.storage_dir / "snapshots"

        for year_dir in snapshots_dir.iterdir():
            if not year_dir.is_dir():
                continue

            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue

                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir():
                        continue

                    try:
                        dir_date = datetime.strptime(f"{year_dir.name}/{month_dir.name}/{day_dir.name}", "%Y/%m/%d")

                        if dir_date.date() < cutoff_date.date():
                            # Remove all files in this day directory
                            for file_path in day_dir.iterdir():
                                file_path.unlink()
                                cleanup_count += 1

                            # Remove empty directory
                            day_dir.rmdir()

                    except ValueError:
                        continue

        logger.info(f"Cleaned up {cleanup_count} old feature snapshots")


# Export main classes
__all__ = [
    'ReproducibleFeatureStore',
    'FeatureSnapshot',
    'FeatureVersioning',
    'FeatureLineage'
]