# rules/loader.py — YAML 规则加载器

import os
import yaml
import logging
from pathlib import Path
from .models import Rule, RuleCategory, RuleSeverity, RuleType, RuleStage, RuleSet

logger = logging.getLogger(__name__)

# 默认规则配置文件路径（相对于项目根目录）
_DEFAULT_RULE_FILE = "rules/rule_config.yaml"


def get_default_rule_path() -> str:
    """获取默认规则配置文件绝对路径"""
    # 从当前文件所在目录往上找 rules/rule_config.yaml
    current = Path(__file__).resolve().parent
    default_path = current / "rule_config.yaml"
    if default_path.exists():
        return str(default_path)
    # 回退：从项目根目录找
    project_root = current.parent
    fallback = project_root / _DEFAULT_RULE_FILE
    return str(fallback)


def load_rules_from_yaml(filepath: str = None) -> RuleSet:
    """
    从 YAML 文件加载规则集。

    Args:
        filepath: YAML 文件路径，默认使用内置的 rule_config.yaml

    Returns:
        RuleSet 含所有规则

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: YAML 格式错误
    """
    if filepath is None:
        filepath = get_default_rule_path()

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"规则配置文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"规则配置文件为空: {filepath}")

    meta = data.get("meta", {})
    rules_raw = data.get("rules", [])

    rules = [_parse_rule(item) for item in rules_raw]
    valid_rules = [r for r in rules if r is not None]

    skipped = len(rules) - len(valid_rules)
    if skipped > 0:
        logger.warning(f"[RuleLoader] 跳过 {skipped} 条无效规则")

    return RuleSet(
        name=meta.get("name", "默认规则集"),
        description=meta.get("description", ""),
        rules=valid_rules,
        enabled=meta.get("enabled", True),
    )


def _parse_rule(item: dict) -> Rule | None:
    """解析单条规则字典为 Rule 对象"""
    try:
        rule_id = item.get("id", "")
        if not rule_id:
            logger.warning(f"[RuleLoader] 跳过缺少 id 的规则: {item}")
            return None

        return Rule(
            id=rule_id,
            name=item.get("name", rule_id),
            description=item.get("description", ""),
            category=RuleCategory(item.get("category", "safety")),
            severity=RuleSeverity(item.get("severity", "error")),
            type=RuleType(item.get("type", "blocklist")),
            stage=RuleStage(item.get("stage", "post_generate")),
            pattern=item.get("pattern"),
            message=item.get("message", ""),
            suggestion=item.get("suggestion", ""),
            enabled=item.get("enabled", True),
            applies_to=item.get("applies_to", ["*"]),
        )
    except (ValueError, KeyError) as e:
        logger.warning(f"[RuleLoader] 解析规则失败: {item.get('id', 'unknown')}, 错误: {e}")
        return None
