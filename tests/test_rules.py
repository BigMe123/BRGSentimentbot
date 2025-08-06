import pathlib
import sys

# Ensure package root on path for direct pytest invocation
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sentiment_bot import rules, analyzer, config


def test_apply_rules(tmp_path, monkeypatch) -> None:
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text("- when: snapshot.volatility > 0.5\n  then: alert\n")
    monkeypatch.setattr(config.settings, "RULES_PATH", str(rules_file))
    snap = analyzer.Snapshot(ts="now", volatility=0.6, confidence=0.5, triggers=[])
    alerts = rules.apply_rules(snap)
    assert alerts == ["alert"]
