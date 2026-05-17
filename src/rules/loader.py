import json
import logging
from pathlib import Path
from typing import Any

import yaml

from src.models.alert import AlertRule, AlertSeverity, RuleCondition

logger = logging.getLogger(__name__)


def _parse_rule_dict(d: dict[str, Any]) -> AlertRule | None:
    """Parse a raw rule dict into an AlertRule, returning None on failure.

    Args:
        d: Raw dict representing a single rule.

    Returns:
        AlertRule on success, None on validation error.
    """
    try:
        condition_raw = d.get("condition", {})
        condition = RuleCondition(**condition_raw)
        return AlertRule(
            id=d.get("id", ""),
            name=d["name"],
            description=d.get("description", ""),
            condition=condition,
            severity=AlertSeverity(d.get("severity", "medium")),
            enabled=bool(d.get("enabled", True)),
            source="config",
        )
    except Exception as exc:
        logger.warning("Rule parse error (id=%s): %s", d.get("id", "unknown"), exc)
        return None


def load_rules_from_file(path: Path) -> list[AlertRule]:
    """Load alert rules from a single YAML or JSON file.

    Args:
        path: Path to a .yaml, .yml, or .json rules file.

    Returns:
        List of parsed AlertRule objects. Malformed entries are skipped with a warning.

    Raises:
        ValueError: If the file extension is not supported.
    """
    suffix = path.suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        raise ValueError(f"Unsupported rules file extension: {suffix}")

    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        raw: dict[str, Any] = json.loads(text)
    else:
        raw = yaml.safe_load(text)

    rule_list: list[dict[str, Any]] = raw.get("rules", [])
    rules: list[AlertRule] = []
    for entry in rule_list:
        rule = _parse_rule_dict(entry)
        if rule is not None:
            rules.append(rule)

    logger.info("Loaded %d rules from %s", len(rules), path)
    return rules


def load_rules_from_dir(rules_dir: Path) -> list[AlertRule]:
    """Recursively load all rules from .yaml, .yml and .json files in a directory.

    Args:
        rules_dir: Directory containing rules files.

    Returns:
        Deduplicated list of AlertRule objects. Rules with duplicate IDs keep the first occurrence.
    """
    if not rules_dir.exists():
        logger.warning("Rules directory does not exist: %s", rules_dir)
        return []

    all_rules: list[AlertRule] = []
    seen_ids: set[str] = set()

    for path in sorted(rules_dir.rglob("*")):
        if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            continue
        try:
            for rule in load_rules_from_file(path):
                if rule.id in seen_ids:
                    logger.warning("Duplicate rule id=%s in %s -- skipping", rule.id, path)
                    continue
                seen_ids.add(rule.id)
                all_rules.append(rule)
        except Exception as exc:
            logger.error("Failed to load rules from %s: %s", path, exc)

    logger.info("Total rules loaded from directory: %d", len(all_rules))
    return all_rules
