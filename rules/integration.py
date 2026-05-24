# rules/integration.py — 规则引擎集成层（v2.0 柔性拦截）
"""
规则引擎集成层。
核心理念：只有真正危险的操作才阻断（CRITICAL），其余仅为警告/建议。
"""

import logging
import json
from typing import Optional
from .models import (
    Rule,
    RuleCategory,
    RuleSeverity,
    RuleType,
    RuleStage,
    CheckResult,
)
from .engine import RulesEngine, RuleViolationError, CheckReport
from .loader import load_rules_from_yaml

logger = logging.getLogger(__name__)

# 全局引擎（懒初始化）
_engine: Optional[RulesEngine] = None
_llm_instance = None


# ── 单例管理 ──────────────────────────────────────────

def get_engine() -> RulesEngine:
    """获取全局规则引擎（懒加载）"""
    global _engine
    if _engine is None:
        _engine = RulesEngine()
        try:
            rule_set = load_rules_from_yaml()
            _engine.load(rule_set)
            logger.info(f"[RulesIntegration] 引擎已初始化，{len(rule_set.rules)} 条规则")
        except FileNotFoundError:
            logger.warning("[RulesIntegration] 规则文件未找到，引擎以空集运行")
        except Exception as e:
            logger.error(f"[RulesIntegration] 规则加载失败: {e}")
    return _engine


def init_engine(llm=None) -> RulesEngine:
    """显式初始化规则引擎，传入 LLM 实例用于 LLM_CHECK 类型规则"""
    global _engine, _llm_instance
    _engine = RulesEngine()
    _llm_instance = llm

    try:
        rule_set = load_rules_from_yaml()
        _engine.load(rule_set)
        if llm is not None:
            _engine.set_llm_checker(_create_llm_checker(llm))
        logger.info("[RulesIntegration] 引擎已初始化（含 LLM 检查器）")
    except FileNotFoundError:
        logger.warning("[RulesIntegration] 规则文件未找到")
    except Exception as e:
        logger.error(f"[RulesIntegration] 初始化失败: {e}")

    return _engine


# ── 便捷检查函数（v2.0：仅 CRITICAL 阻断）────────────

def check_generated_code(
    code: str,
    agent_name: str = "data_agent",
    raise_on_critical: bool = True,
) -> CheckReport:
    """
    检查 LLM 生成的沙箱代码。仅 CRITICAL 级别违规才阻断执行。

    Returns:
        CheckReport — 通过 report.has_critical() 判断是否需要阻断
    """
    engine = get_engine()
    report = engine.check_code(code, agent_name=agent_name)

    if raise_on_critical and report.has_critical():
        logger.warning(
            f"[Rules] 代码存在 CRITICAL 违规，阻断执行: "
            f"{', '.join(f.rule_id for f in report.get_critical_failures())}"
        )
        raise RuleViolationError(report)

    # WARNING/INFO 不阻断，仅日志记录
    failures = report.get_failures()
    if failures:
        logger.info(f"[Rules] 代码有 {len(failures)} 条建议: {', '.join(f.rule_id for f in failures[:3])}")

    return report


def check_generated_answer(
    answer: str,
    context: str = "",
    agent_name: str = "rag_agent",
) -> CheckReport:
    """
    检查 LLM 生成的答案质量。不修改原答案，仅返回报告供调用方决策。
    """
    engine = get_engine()
    report = engine.check_answer(answer, context=context, agent_name=agent_name)

    failures = report.get_failures()
    if failures:
        logger.info(f"[Rules] 答案有 {len(failures)} 条质量建议: {', '.join(f.rule_id for f in failures[:3])}")

    return report


def check_user_input(user_input: str) -> CheckReport:
    """
    检查用户输入安全性。仅提示词注入类攻击才阻断。
    """
    engine = get_engine()
    report = engine.check_input(user_input)

    if report.has_critical():
        logger.warning(f"[Rules] 用户输入存在 CRITICAL 违规: {report.summary()}")
        raise RuleViolationError(report)

    return report


def get_rule_summary() -> dict:
    """获取当前规则集摘要"""
    engine = get_engine()
    rule_set = engine.rule_set
    if rule_set is None:
        return {"name": "空规则集", "total_rules": 0, "enabled_rules": 0}

    all_rules = rule_set.rules
    enabled = rule_set.get_enabled_rules()
    by_category = {}
    for r in enabled:
        by_category[r.category.value] = by_category.get(r.category.value, 0) + 1

    return {
        "name": rule_set.name,
        "description": rule_set.description,
        "total_rules": len(all_rules),
        "enabled_rules": len(enabled),
        "by_category": by_category,
    }


# ── LLM 检查器（仅在 LLM_CHECK 类型规则触发时调用）──

def _create_llm_checker(llm):
    """创建 LLM 规则检查回调"""

    LLM_CHECK_PROMPT = """你是一个代码/答案质量审核员。请根据以下规则检查内容是否合规。

规则：{rule_name}
规则描述：{rule_description}
违规标准：{rule_message}
修复建议：{rule_suggestion}

待检查内容：
{content}

上下文（如有）：
{context}

请只返回一个 JSON：
{{"passed": true/false, "reason": "判决理由（中文，一句话）"}}
只返回 JSON，不要有任何其他内容。"""

    def checker(rule: Rule, content: str, context: str = "") -> CheckResult:
        try:
            from langchain_core.messages import HumanMessage

            prompt = LLM_CHECK_PROMPT.format(
                rule_name=rule.name,
                rule_description=rule.description,
                rule_message=rule.message,
                rule_suggestion=rule.suggestion,
                content=content[:3000],
                context=context[:2000] if context else "无",
            )

            result = llm.invoke([HumanMessage(content=prompt)])
            text = result.content if hasattr(result, "content") else str(result)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(text)

            passed = parsed.get("passed", True)
            reason = parsed.get("reason", "")

            return CheckResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=passed,
                severity=rule.severity,
                message=rule.message if not passed else "通过",
                suggestion=rule.suggestion if not passed else "",
                detail=reason,
            )
        except Exception as e:
            logger.warning(f"[LLMChecker] 规则 '{rule.id}' 检查异常: {e}")
            return CheckResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=True,
                severity=rule.severity,
                message=f"LLM 检查异常（已容错）",
            )

    return checker
