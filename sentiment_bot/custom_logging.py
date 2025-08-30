"""
Structured logging configuration for the fast pipeline.
Provides consistent, colored, and efficient logging across all components.
"""

import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

# Color codes for terminal output
COLORS = {
    "RESET": "\033[0m",
    "RED": "\033[91m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "MAGENTA": "\033[95m",
    "CYAN": "\033[96m",
    "WHITE": "\033[97m",
    "GRAY": "\033[90m",
    "BOLD": "\033[1m",
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and structured output."""

    LEVEL_COLORS = {
        logging.DEBUG: COLORS["GRAY"],
        logging.INFO: COLORS["CYAN"],
        logging.WARNING: COLORS["YELLOW"],
        logging.ERROR: COLORS["RED"],
        logging.CRITICAL: COLORS["MAGENTA"],
    }

    COMPONENT_COLORS = {
        "PIPELINE": COLORS["BLUE"],
        "FETCH": COLORS["GREEN"],
        "RENDER": COLORS["MAGENTA"],
        "PARSE": COLORS["YELLOW"],
        "BROWSER_POOL": COLORS["CYAN"],
        "STATS": COLORS["WHITE"],
    }

    def format(self, record):
        # Add color based on level
        levelcolor = self.LEVEL_COLORS.get(record.levelno, COLORS["RESET"])

        # Extract component from message if present
        component = ""
        message = record.getMessage()
        if message.startswith("[") and "]" in message:
            end = message.index("]")
            component = message[1:end]
            message = message[end + 1 :].strip()
            component_color = self.COMPONENT_COLORS.get(component, COLORS["WHITE"])
            component = f"{component_color}[{component}]{COLORS['RESET']}"

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        # Build formatted message
        if record.levelno == logging.DEBUG:
            # Minimal debug format
            return f"{COLORS['GRAY']}{timestamp}{COLORS['RESET']} {component} {message}"
        else:
            # Standard format with level
            level = f"{levelcolor}{record.levelname:7}{COLORS['RESET']}"
            return f"{COLORS['GRAY']}{timestamp}{COLORS['RESET']} {level} {component} {message}"


class PerformanceLogger:
    """Logger for tracking performance metrics."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.timings: Dict[str, list] = {}

    def log_timing(
        self,
        operation: str,
        duration_ms: int,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log a timing measurement."""
        if operation not in self.timings:
            self.timings[operation] = []
        self.timings[operation].append(duration_ms)

        # Log if slow
        if duration_ms > 1000:
            self.logger.warning(
                f"[STATS] Slow {operation}: {duration_ms}ms {metadata or ''}"
            )
        elif self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"[STATS] {operation}: {duration_ms}ms")

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        stats = {}
        for op, times in self.timings.items():
            if times:
                stats[op] = {
                    "count": len(times),
                    "total_ms": sum(times),
                    "avg_ms": sum(times) // len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                }
        return stats

    def log_summary(self):
        """Log a summary of all timings."""
        stats = self.get_stats()
        if stats:
            self.logger.info("[STATS] Performance Summary:")
            for op, data in stats.items():
                self.logger.info(
                    f"[STATS]   {op}: {data['count']} ops, "
                    f"avg={data['avg_ms']}ms, min={data['min_ms']}ms, max={data['max_ms']}ms"
                )


def setup_logging(
    level: str = "INFO", log_file: Optional[Path] = None, use_colors: bool = True
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
        use_colors: Whether to use colored output (auto-disabled for files)
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if use_colors and sys.stdout.isatty():
        console_handler.setFormatter(ColoredFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s - %(message)s")
        )

    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s - %(message)s")
        )
        root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("newspaper").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.ERROR)

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(f"[LOGGING] Initialized at level {level}")
    if log_file:
        logger.info(f"[LOGGING] Writing to {log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def get_performance_logger(name: str) -> PerformanceLogger:
    """Get a performance logger instance."""
    return PerformanceLogger(name)


# Quick setup for scripts
def quick_setup(debug: bool = False):
    """Quick logging setup for scripts."""
    setup_logging(level="DEBUG" if debug else "INFO")
