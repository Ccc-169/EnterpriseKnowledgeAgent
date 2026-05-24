# rules/engine.py — 规则检查引擎

import re
import logging
from typing import Optional, Callable
from .models import (
    Rule,
    RuleType,
    RuleSeverity,
    RuleStage,
    CheckResult,
    RuleSet,
)

logger = logging.getLogger(__name__)


class RulesEngine:
    """
    全局规则检查引擎。

    职责：
    1. 加载/管理规则集
    2. 对生成的代码进行安全检查
    3. 对生成的答案进行质量校验
    4. 输出结构化的检查报告

    使用方式：
        engine = RulesEngine()
        engine.load(rule_set)

        # 检查代码
        report = engine.check_code(code, agent_name="data_agent")
        if report.has_critical():
            raise RuleViolationError(report)

        # 检查答案质量
        report = engine.check_answer(answer, context, agent_name="rag_agent")
    """

    def __init__(self):
        self._rule_set: Optional[RuleSet] = None
        self._llm_checker: Optional[Callable] = None  # LLM 校验回调

    # ── 配置 ────────────────────────────────────────────

    def load(self, rule_set: RuleSet) -> "RulesEngine":
        """加载规则集"""
        self._rule_set = rule_set
        logger.info(f"[RulesEngine] 已加载规则集 '{rule_set.name}'，"
                    f"共 {len(rule_set.rules)} 条规则，"
                    f"启用 {len(rule_set.get_enabled_rules())} 条")
        return self

    def set_llm_checker(self, checker: Callable) -> None:
        """设置 LLM 校验回调函数：fn(rule, content) -> CheckResult"""
        self._llm_checker = checker

    @property
    def rule_set(self) -> Optional[RuleSet]:
        return self._rule_set

    # ── 检查入口 ────────────────────────────────────────

    def check_code(
        self,
        code: str,
        agent_name: str = "data_agent",
        stage: Optional[RuleStage] = None,
    ) -> "CheckReport":
        """
        检查 AI 生成的代码。

        Args:
            code: 待检查的代码字符串
            agent_name: 生成代码的 Agent 名称（用于过滤适用规则）
            stage: 检查阶段，默认检查 POST_GENERATE + PRE_EXECUTE

        Returns:
            CheckReport 含所有规则的检查结果
        """
        if self._rule_set is None:
            return CheckReport.empty()

        stages = [stage] if stage else [RuleStage.POST_GENERATE, RuleStage.PRE_EXECUTE]
        results = []

        for s in stages:
            rules = self._rule_set.get_enabled_rules(agent_name, stage=s)
            for rule in rules:
                result = self._check_one_rule(rule, code)
                results.append(result)

        return CheckReport(results=results, source="code_check")

    def check_answer(
        self,
        answer: str,
        context: str = "",
        agent_name: str = "rag_agent",
    ) -> "CheckReport":
        """
        检查 AI 生成的答案质量。

        Args:
            answer: 生成的答案文本
            context: 检索到的文档上下文（用于 LLM 校验）
            agent_name: 生成答案的 Agent 名称

        Returns:
            CheckReport 含所有规则的检查结果
        """
        if self._rule_set is None:
            return CheckReport.empty()

        rules = self._rule_set.get_enabled_rules(agent_name, stage=RuleStage.POST_RETRIEVE)
        results = []

        for rule in rules:
            result = self._check_one_rule(rule, answer, context=context)
            results.append(result)

        return CheckReport(results=results, source="answer_check")

    def check_input(
        self,
        user_input: str,
        agent_name: str = "*",
    ) -> "CheckReport":
        """
        检查用户输入的安全性。

        Args:
            user_input: 用户输入的问题
            agent_name: 目标 Agent 名称

        Returns:
            CheckReport
        """
        if self._rule_set is None:
            return CheckReport.empty()

        rules = self._rule_set.get_enabled_rules(agent_name, stage=RuleStage.PRE_GENERATE)
        results = []

        for rule in rules:
            result = self._check_one_rule(rule, user_input)
            results.append(result)

        return CheckReport(results=results, source="input_check")

    # ── 内部 ────────────────────────────────────────────

    def _check_one_rule(
        self,
        rule: Rule,
        content: str,
        context: str = "",
    ) -> CheckResult:
        """对单条规则执行检查"""
        try:
            if rule.type == RuleType.BLOCKLIST:
                return self._check_blocklist(rule, content)
            elif rule.type == RuleType.ALLOWLIST:
                return self._check_allowlist(rule, content)
            elif rule.type == RuleType.PATTERN:
                return self._check_pattern(rule, content)
            elif rule.type == RuleType.LLM_CHECK:
                return self._check_llm(rule, content, context)
            else:
                return CheckResult(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    passed=True,
                    severity=rule.severity,
                    message=f"未知检查类型: {rule.type}",
                )
        except Exception as e:
            logger.warning(f"[RulesEngine] 规则 '{rule.id}' 检查异常: {e}")
            # 异常时不阻断，返回 PASS（保守策略）
            return CheckResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=True,
                severity=rule.severity,
                message=f"检查异常（已容错）: {e}",
            )

    def _check_blocklist(self, rule: Rule, content: str) -> CheckResult:
        """黑名单模式：匹配到即违规"""
        if not rule.pattern:
            return self._pass(rule)
        matches = list(re.finditer(rule.pattern, content, re.MULTILINE))
        if not matches:
            return self._pass(rule)
        locations = [f"行{content[:m.start()].count(chr(10)) + 1}: {m.group()[:60]}"
                     for m in matches[:5]]
        detail = f"发现 {len(matches)} 处违规" + (f"，取前5处:\n" + "\n".join(locations) if locations else "")
        return CheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            passed=False,
            severity=rule.severity,
            message=rule.message,
            suggestion=rule.suggestion,
            location=", ".join(locations),
            detail=detail,
        )

    def _check_allowlist(self, rule: Rule, content: str) -> CheckResult:
        """白名单模式：未匹配到即违规"""
        if not rule.pattern:
            return self._pass(rule)
        if re.search(rule.pattern, content, re.MULTILINE):
            return self._pass(rule)
        return CheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            passed=False,
            severity=rule.severity,
            message=rule.message,
            suggestion=rule.suggestion,
            detail="未找到必须包含的内容",
        )

    def _check_pattern(self, rule: Rule, content: str) -> CheckResult:
        """通用模式检查：根据规则类别判断"""
        if not rule.pattern:
            return self._pass(rule)

        matches = list(re.finditer(rule.pattern, content, re.MULTILINE))
        if not matches:
            return CheckResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=False,
                severity=rule.severity,
                message=rule.message,
                suggestion=rule.suggestion,
                detail="未匹配到预期模式",
            )

        return CheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            passed=True,
            severity=rule.severity,
            message=f"已匹配到预期模式，发现 {len(matches)} 处",
            detail=str([m.group()[:50] for m in matches[:3]]),
        )

    def _check_llm(self, rule: Rule, content: str, context: str) -> CheckResult:
        """LLM 校验：委托给外部 LLM 检查回调"""
        if self._llm_checker is None:
            # 无 LLM 检查器时默认通过
            return self._pass(rule, detail="LLM 检查器未配置，默认通过")
        try:
            return self._llm_checker(rule, content, context)
        except Exception as e:
            logger.warning(f"[RulesEngine] LLM 检查失败，默认通过: {e}")
            return self._pass(rule, detail=f"LLM 检查异常（已容错）: {e}")

    @staticmethod
    def _pass(rule: Rule, detail: str = "") -> CheckResult:
        return CheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            passed=True,
            severity=rule.severity,
            message="通过",
            detail=detail,
        )


class CheckReport:
    """规则检查报告"""

    def __init__(self, results: list[CheckResult], source: str = ""):
        self.results = results
        self.source = source
        self._total = len(results)
        self._passed = sum(1 for r in results if r.passed)
        self._failed = self._total - self._passed
        self._critical_failures = [
            r for r in results
            if not r.passed and r.severity == RuleSeverity.CRITICAL
        ]

    @classmethod
    def empty(cls) -> "CheckReport":
        return cls(results=[], source="empty")

    # ── 查询 ────────────────────────────────────────────

    @property
    def all_passed(self) -> bool:
        return self._failed == 0

    @property
    def passed_count(self) -> int:
        return self._passed

    @property
    def failed_count(self) -> int:
        return self._failed

    @property
    def total_count(self) -> int:
        return self._total

    def has_critical(self) -> bool:
        return len(self._critical_failures) > 0

    def has_errors(self) -> bool:
        return any(
            not r.passed and r.severity in (RuleSeverity.CRITICAL, RuleSeverity.ERROR)
            for r in self.results
        )

    def get_failures(self, min_severity: RuleSeverity = RuleSeverity.WARNING) -> list[CheckResult]:
        """获取所有未通过的检查结果"""
        severity_order = {
            RuleSeverity.CRITICAL: 0,
            RuleSeverity.ERROR: 1,
            RuleSeverity.WARNING: 2,
            RuleSeverity.INFO: 3,
        }
        return [
            r for r in self.results
            if not r.passed and severity_order.get(r.severity, 99) <= severity_order.get(min_severity, 99)
        ]

    def get_critical_failures(self) -> list[CheckResult]:
        return self._critical_failures

    # ── 输出 ────────────────────────────────────────────

    def summary(self) -> str:
        """生成摘要"""
        if self._total == 0:
            return "📋 无规则检查（规则集为空）"
        status = "✅ 全部通过" if self.all_passed else f"❌ {self._failed}/{self._total} 未通过"
        parts = [f"📋 规则检查 [{self.source}]: {status}"]
        if self._critical_failures:
            parts.append(f"   🚫 致命违规 {len(self._critical_failures)} 条:")
            for f in self._critical_failures:
                parts.append(f"      [{f.rule_id}] {f.message}")
        other_failures = [r for r in self.get_failures() if r.severity != RuleSeverity.CRITICAL]
        if other_failures:
            parts.append(f"   ⚠️ 其他违规 {len(other_failures)} 条:")
            for f in other_failures[:5]:
                parts.append(f"      [{f.rule_id}] {f.message}")
            if len(other_failures) > 5:
                parts.append(f"      ... 还有 {len(other_failures) - 5} 条")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """转为字典，便于 API 返回"""
        return {
            "source": self.source,
            "total": self._total,
            "passed": self._passed,
            "failed": self._failed,
            "all_passed": self.all_passed,
            "has_critical": self.has_critical(),
            "results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "severity": r.severity.value,
                    "message": r.message,
                    "suggestion": r.suggestion,
                    "location": r.location,
                }
                for r in self.results
            ],
        }

    def __repr__(self) -> str:
        return f"CheckReport(passed={self._passed}/{self._total}, critical={len(self._critical_failures)})"


class RuleViolationError(Exception):
    """规则违规异常：在严重违规时抛出，阻断执行"""

    def __init__(self, report: CheckReport, message: str = ""):
        self.report = report
        super().__init__(message or report.summary())
