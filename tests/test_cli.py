import json
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def test_cli_limit_zero() -> None:
    cmd = [
        sys.executable,
        "-m",
        "sentiment_bot",
        "--window",
        "day",
        "--limit",
        "0",
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    assert data["meta"]["analyzed"] == 0

