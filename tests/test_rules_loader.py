import json
import tempfile
from pathlib import Path

import pytest
import yaml

from src.rules.loader import load_rules_from_dir, load_rules_from_file


def _write_yaml(path: Path, content: dict) -> None:
    path.write_text(yaml.dump(content), encoding="utf-8")


def _write_json(path: Path, content: dict) -> None:
    path.write_text(json.dumps(content), encoding="utf-8")


def _valid_rule(rule_id: str = "r1") -> dict:
    return {
        "id": rule_id,
        "name": f"Rule {rule_id}",
        "description": "Test rule",
        "condition": {
            "metric": "events_per_minute",
            "operator": ">",
            "threshold": 10,
            "window_seconds": 60,
        },
        "severity": "high",
        "enabled": True,
    }


def test_load_yaml_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.yaml"
        _write_yaml(path, {"rules": [_valid_rule("r1"), _valid_rule("r2")]})
        rules = load_rules_from_file(path)
        assert len(rules) == 2
        assert rules[0].id == "r1"


def test_load_json_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.json"
        _write_json(path, {"rules": [_valid_rule("r3")]})
        rules = load_rules_from_file(path)
        assert len(rules) == 1
        assert rules[0].name == "Rule r3"


def test_load_unsupported_extension() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.txt"
        path.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_rules_from_file(path)


def test_load_malformed_rule_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.yaml"
        bad = {"id": "bad", "name": "Bad Rule"}  # missing condition
        good = _valid_rule("good")
        _write_yaml(path, {"rules": [bad, good]})
        rules = load_rules_from_file(path)
        assert len(rules) == 1
        assert rules[0].id == "good"


def test_load_from_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        _write_yaml(p / "a.yaml", {"rules": [_valid_rule("a")]})
        _write_json(p / "b.json", {"rules": [_valid_rule("b")]})
        rules = load_rules_from_dir(p)
        ids = {r.id for r in rules}
        assert ids == {"a", "b"}


def test_load_from_dir_deduplication() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        _write_yaml(p / "a.yaml", {"rules": [_valid_rule("dup")]})
        _write_yaml(p / "b.yaml", {"rules": [_valid_rule("dup")]})
        rules = load_rules_from_dir(p)
        assert len(rules) == 1


def test_load_from_nonexistent_dir() -> None:
    rules = load_rules_from_dir(Path("/nonexistent/path/xyz"))
    assert rules == []
