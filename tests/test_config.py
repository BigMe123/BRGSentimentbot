from datetime import timedelta
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import config


def test_windows_mapping() -> None:
    assert config.WINDOWS["hour"] == timedelta(hours=1)
    assert "day" in config.WINDOWS

