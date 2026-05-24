# rules/models.py — 规则系统数据模型

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RuleCategory(str, Enum):
    """规则分类"""
    SAFETY = "safety"       # 安全防护：禁止危险操作，防止崩溃/数据泄露
    STYLE = "style"         # 代码风格：命名规范、格式要求
    QUALITY = "quality"     # 输出质量：答案/代码质量校验
    DOMAIN = "domain"       # 业务领域：行业特定约束


class RuleSeverity(str, Enum):
    """严重等级"""
    CRITICAL = "critical"   # 致命：必须阻断执行
    ERROR = "error"         # 错误：应修复后重试
    WARNING = "warning"     # 警告：建议修复，不阻断
    INFO = "info"           # 提示：仅记录，不影响执行


class RuleType(str, Enum):
    """检查方式"""
    BLOCKLIST = "blocklist"     # 黑名单：匹配到即违规
    ALLOWLIST = "allowlist"     # 白名单：未匹配到即违规
    PATTERN = "pattern"         # 通用正则：匹配结果由 checker 判定
    LLM_CHECK = "llm_check"     # LLM 校验：由 LLM 判断是否合规


class RuleStage(str, Enum):
    """规则执行阶段"""
    PRE_GENERATE = "pre_generate"      # 代码生成前：输入校验
    POST_GENERATE = "post_generate"    # 代码生成后：输出校验（阻断型）
    PRE_EXECUTE = "pre_execute"        # 执行前：最终安全检查
    POST_EXECUTE = "post_execute"      # 执行后：结果校验
    POST_RETRIEVE = "post_retrieve"    # 检索后：答案质量校验


@dataclass
class Rule:
    """单条规则定义"""
    id: str                               # 唯一标识，如 SAFETY-001
    name: str                             # 规则名称
    description: str = ""                 # 规则描述
    category: RuleCategory = RuleCategory.SAFETY
    severity: RuleSeverity = RuleSeverity.ERROR
    type: RuleType = RuleType.BLOCKLIST
    stage: RuleStage = RuleStage.POST_GENERATE
    pattern: Optional[str] = None         # 正则或检查模式
    message: str = ""                     # 违规提示消息
    suggestion: str = ""                  # 修复建议
    enabled: bool = True                  # 是否启用
    applies_to: list[str] = field(default_factory=lambda: ["*"])  # 适用 Agent 列表，* 表示全部


@dataclass
class CheckResult:
    """单条规则检查结果"""
    rule_id: str
    rule_name: str
    passed: bool
    severity: RuleSeverity
    message: str = ""
    suggestion: str = ""
    location: str = ""          # 违规位置（行号、片段等）
    detail: str = ""            # 额外详情


@dataclass
class RuleSet:
    """规则集"""
    name: str
    description: str = ""
    rules: list[Rule] = field(default_factory=list)
    enabled: bool = True

    def get_enabled_rules(self, agent_name: str = "*", stage: Optional[RuleStage] = None) -> list[Rule]:
        """获取启用的规则，可按 agent 和 stage 过滤。agent_name="*" 时返回所有启用的规则"""
        result = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            # agent_name="*" 表示查询全部，不过滤；否则按 applies_to 筛选
            if agent_name != "*":
                if "*" not in rule.applies_to and agent_name not in rule.applies_to:
                    continue
            if stage is not None and rule.stage != stage:
                continue
            result.append(rule)
        return result
