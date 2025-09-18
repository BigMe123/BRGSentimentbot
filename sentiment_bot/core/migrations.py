"""
Database migration system for core components.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Migration:
    """Base class for database migrations."""

    def __init__(self, version: int, description: str):
        self.version = version
        self.description = description
        self.applied_at = None

    def up(self, conn: sqlite3.Connection):
        """Apply the migration."""
        raise NotImplementedError

    def down(self, conn: sqlite3.Connection):
        """Rollback the migration."""
        raise NotImplementedError


class CreateMigrationsTable(Migration):
    """Create the migrations tracking table."""

    def __init__(self):
        super().__init__(0, "Create migrations table")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS migrations")
        conn.commit()


class CreateBacktestTables(Migration):
    """Create tables for backtest system."""

    def __init__(self):
        super().__init__(1, "Create backtest system tables")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Backtest runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                rebalance_frequency TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                countries TEXT NOT NULL,
                metrics_tracked TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Backtest results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                country TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                total_return REAL,
                annualized_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                mape REAL,
                rmse REAL,
                directional_accuracy REAL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        """)

        # Backtest trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                country TEXT NOT NULL,
                action TEXT NOT NULL,
                position_size REAL NOT NULL,
                price REAL NOT NULL,
                prediction REAL,
                actual REAL,
                pnl REAL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        """)

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS backtest_trades")
        cursor.execute("DROP TABLE IF EXISTS backtest_results")
        cursor.execute("DROP TABLE IF EXISTS backtest_runs")
        conn.commit()


class CreateRSSMonitorTables(Migration):
    """Create tables for RSS monitoring system."""

    def __init__(self):
        super().__init__(2, "Create RSS monitor tables")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Feed status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feed_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                last_check DATETIME,
                last_success DATETIME,
                consecutive_failures INTEGER DEFAULT 0,
                total_items_fetched INTEGER DEFAULT 0,
                avg_response_time_ms REAL,
                error_message TEXT,
                quarantined_until DATETIME
            )
        """)

        # Feed items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feed_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL,
                item_guid TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                published DATETIME,
                content TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(feed_url, item_guid),
                FOREIGN KEY (feed_url) REFERENCES feed_status(feed_url)
            )
        """)

        # Feed health metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feed_health_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_feeds INTEGER NOT NULL,
                healthy_feeds INTEGER NOT NULL,
                degraded_feeds INTEGER NOT NULL,
                error_feeds INTEGER NOT NULL,
                quarantined_feeds INTEGER NOT NULL,
                avg_response_time_ms REAL,
                total_items_fetched INTEGER
            )
        """)

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS feed_health_metrics")
        cursor.execute("DROP TABLE IF EXISTS feed_items")
        cursor.execute("DROP TABLE IF EXISTS feed_status")
        conn.commit()


class CreateEconomicModelTables(Migration):
    """Create tables for economic models."""

    def __init__(self):
        super().__init__(3, "Create economic model tables")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Model configurations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_type TEXT NOT NULL,
                country TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model_type, country)
            )
        """)

        # Model training history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_type TEXT NOT NULL,
                country TEXT NOT NULL,
                training_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                training_samples INTEGER,
                validation_mape REAL,
                validation_rmse REAL,
                feature_importance TEXT,
                hyperparameters TEXT
            )
        """)

        # Economic forecasts archive
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS economic_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forecast_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                model_type TEXT NOT NULL,
                country TEXT NOT NULL,
                horizon TEXT NOT NULL,
                point_estimate REAL NOT NULL,
                confidence_low REAL NOT NULL,
                confidence_high REAL NOT NULL,
                sentiment_input REAL,
                market_input TEXT,
                features_used TEXT,
                model_version TEXT
            )
        """)

        # Bridge equation coefficients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bridge_coefficients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                target_variable TEXT NOT NULL,
                coefficient_name TEXT NOT NULL,
                coefficient_value REAL NOT NULL,
                standard_error REAL,
                p_value REAL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(country, target_variable, coefficient_name)
            )
        """)

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS bridge_coefficients")
        cursor.execute("DROP TABLE IF EXISTS economic_forecasts")
        cursor.execute("DROP TABLE IF EXISTS model_training")
        cursor.execute("DROP TABLE IF EXISTS model_configs")
        conn.commit()


class CreateRealtimePipelineTables(Migration):
    """Create tables for real-time pipeline."""

    def __init__(self):
        super().__init__(4, "Create real-time pipeline tables")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Pipeline runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME,
                status TEXT NOT NULL,
                feeds_processed INTEGER DEFAULT 0,
                articles_ingested INTEGER DEFAULT 0,
                articles_analyzed INTEGER DEFAULT 0,
                errors_encountered INTEGER DEFAULT 0,
                config TEXT
            )
        """)

        # Article processing log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_processing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                title TEXT NOT NULL,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                stage_reached TEXT NOT NULL,
                processing_time_ms INTEGER,
                error_message TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
            )
        """)

        # Deduplication cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dedup_cache (
                hash TEXT PRIMARY KEY,
                article_id TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                seen_count INTEGER DEFAULT 1
            )
        """)

        # Entity extraction cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT NOT NULL,
                entity_text TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                confidence REAL,
                extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_article_id (article_id)
            )
        """)

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS entity_cache")
        cursor.execute("DROP TABLE IF EXISTS dedup_cache")
        cursor.execute("DROP TABLE IF EXISTS article_processing")
        cursor.execute("DROP TABLE IF EXISTS pipeline_runs")
        conn.commit()


class AddIndicesForPerformance(Migration):
    """Add database indices for better query performance."""

    def __init__(self):
        super().__init__(5, "Add performance indices")

    def up(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Predictions table indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_model_country
            ON predictions(model_type, country, timestamp DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_timestamp
            ON predictions(timestamp DESC)
        """)

        # Backtest results indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_results_run_country
            ON backtest_results(run_id, country)
        """)

        # Feed status indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feed_status_url
            ON feed_status(feed_url)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feed_items_feed_published
            ON feed_items(feed_url, published DESC)
        """)

        # Economic forecasts indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecasts_country_date
            ON economic_forecasts(country, forecast_date DESC)
        """)

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("DROP INDEX IF EXISTS idx_predictions_model_country")
        cursor.execute("DROP INDEX IF EXISTS idx_predictions_timestamp")
        cursor.execute("DROP INDEX IF EXISTS idx_backtest_results_run_country")
        cursor.execute("DROP INDEX IF EXISTS idx_feed_status_url")
        cursor.execute("DROP INDEX IF EXISTS idx_feed_items_feed_published")
        cursor.execute("DROP INDEX IF EXISTS idx_forecasts_country_date")
        conn.commit()


class MigrationManager:
    """Manages database migrations for all core systems."""

    def __init__(self, db_paths: Optional[Dict[str, str]] = None):
        self.db_paths = db_paths or {
            "performance": "state/performance_monitor.db",
            "backtest": "state/backtest_results.db",
            "rss": "state/rss_monitor.db",
            "economic": "state/economic_models.db",
            "pipeline": "state/realtime_pipeline.db"
        }

        # Define migrations in order
        self.migrations = [
            CreateMigrationsTable(),
            CreateBacktestTables(),
            CreateRSSMonitorTables(),
            CreateEconomicModelTables(),
            CreateRealtimePipelineTables(),
            AddIndicesForPerformance()
        ]

    def ensure_db_exists(self, db_path: str):
        """Ensure database file and directory exist."""
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Create empty database
            conn = sqlite3.connect(db_path)
            conn.close()

    def get_current_version(self, conn: sqlite3.Connection) -> int:
        """Get current migration version."""
        cursor = conn.cursor()

        # Check if migrations table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='migrations'
        """)

        if not cursor.fetchone():
            return -1

        # Get latest migration version
        cursor.execute("SELECT MAX(version) FROM migrations")
        result = cursor.fetchone()
        return result[0] if result[0] is not None else -1

    def apply_migration(self, conn: sqlite3.Connection, migration: Migration):
        """Apply a single migration."""
        logger.info(f"Applying migration {migration.version}: {migration.description}")

        try:
            migration.up(conn)

            # Record migration
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO migrations (version, description)
                VALUES (?, ?)
            """, (migration.version, migration.description))
            conn.commit()

            logger.info(f"Successfully applied migration {migration.version}")

        except Exception as e:
            logger.error(f"Failed to apply migration {migration.version}: {e}")
            conn.rollback()
            raise

    def rollback_migration(self, conn: sqlite3.Connection, migration: Migration):
        """Rollback a single migration."""
        logger.info(f"Rolling back migration {migration.version}: {migration.description}")

        try:
            migration.down(conn)

            # Remove migration record
            cursor = conn.cursor()
            cursor.execute("DELETE FROM migrations WHERE version = ?", (migration.version,))
            conn.commit()

            logger.info(f"Successfully rolled back migration {migration.version}")

        except Exception as e:
            logger.error(f"Failed to rollback migration {migration.version}: {e}")
            conn.rollback()
            raise

    def migrate(self, target_version: Optional[int] = None):
        """Run migrations up to target version (or latest if None)."""

        if target_version is None:
            target_version = max(m.version for m in self.migrations)

        results = {}

        for db_name, db_path in self.db_paths.items():
            logger.info(f"Migrating database: {db_name} ({db_path})")

            self.ensure_db_exists(db_path)
            conn = sqlite3.connect(db_path)

            try:
                current_version = self.get_current_version(conn)
                logger.info(f"Current version: {current_version}")

                # Apply migrations
                applied = 0
                for migration in self.migrations:
                    if current_version < migration.version <= target_version:
                        self.apply_migration(conn, migration)
                        applied += 1

                results[db_name] = {
                    "status": "success",
                    "migrations_applied": applied,
                    "current_version": target_version if applied > 0 else current_version
                }

                logger.info(f"Completed migration for {db_name}: {applied} migrations applied")

            except Exception as e:
                results[db_name] = {
                    "status": "error",
                    "error": str(e)
                }
                logger.error(f"Migration failed for {db_name}: {e}")

            finally:
                conn.close()

        return results

    def rollback(self, target_version: int = 0):
        """Rollback migrations to target version."""

        results = {}

        for db_name, db_path in self.db_paths.items():
            if not Path(db_path).exists():
                continue

            logger.info(f"Rolling back database: {db_name} ({db_path})")
            conn = sqlite3.connect(db_path)

            try:
                current_version = self.get_current_version(conn)

                # Rollback migrations in reverse order
                rolled_back = 0
                for migration in reversed(self.migrations):
                    if target_version < migration.version <= current_version:
                        self.rollback_migration(conn, migration)
                        rolled_back += 1

                results[db_name] = {
                    "status": "success",
                    "migrations_rolled_back": rolled_back,
                    "current_version": target_version
                }

            except Exception as e:
                results[db_name] = {
                    "status": "error",
                    "error": str(e)
                }

            finally:
                conn.close()

        return results

    def status(self) -> Dict[str, Dict]:
        """Get migration status for all databases."""

        status = {}

        for db_name, db_path in self.db_paths.items():
            if not Path(db_path).exists():
                status[db_name] = {
                    "exists": False,
                    "version": -1
                }
                continue

            conn = sqlite3.connect(db_path)
            try:
                version = self.get_current_version(conn)
                status[db_name] = {
                    "exists": True,
                    "version": version,
                    "path": db_path
                }
            finally:
                conn.close()

        return status


def run_migrations():
    """Convenience function to run all migrations."""
    manager = MigrationManager()
    results = manager.migrate()

    for db_name, result in results.items():
        if result["status"] == "success":
            print(f"✅ {db_name}: Applied {result['migrations_applied']} migrations")
        else:
            print(f"❌ {db_name}: Migration failed - {result['error']}")

    return results


if __name__ == "__main__":
    # Run migrations when script is executed directly
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "rollback":
            target = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            manager = MigrationManager()
            results = manager.rollback(target)
            print(f"Rolled back to version {target}")
        elif sys.argv[1] == "status":
            manager = MigrationManager()
            status = manager.status()
            for db, info in status.items():
                print(f"{db}: Version {info['version']} ({'exists' if info['exists'] else 'not found'})")
    else:
        run_migrations()