"""
AgentInfo - Agent配置模型

参考OpenCode的Zod Schema设计,使用Pydantic实现类型安全的Agent定义
支持任务场景和策略配置
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
import fnmatch

from derisk.agent.core_v2.task_scene import (
    TaskScene,
    ContextPolicy,
    PromptPolicy,
    ToolPolicy,
)


class AgentMode(str, Enum):
    """Agent模式 - 参考OpenCode Agent.Info.mode"""

    PRIMARY = "primary"  # 主Agent - 执行核心任务
    SUBAGENT = "subagent"  # 子Agent - 被委派任务
    UTILITY = "utility"  # 工具Agent - 内部辅助


class PermissionAction(str, Enum):
    """权限动作 - 参考OpenCode Permission Ruleset"""

    ALLOW = "allow"  # 允许执行
    DENY = "deny"  # 拒绝执行
    ASK = "ask"  # 询问用户确认


class PermissionRule(BaseModel):
    """权限规则"""

    pattern: str  # 工具名称模式,支持通配符
    action: PermissionAction  # 执行动作
    description: Optional[str] = None  # 规则描述

    def matches(self, tool_name: str) -> bool:
        """检查工具名称是否匹配模式"""
        return fnmatch.fnmatch(tool_name, self.pattern)


class PermissionRuleset(BaseModel):
    """
    权限规则集 - 参考OpenCode的Permission Ruleset

    示例:
        ruleset = PermissionRuleset(
            rules=[
                PermissionRule(pattern="*", action=PermissionAction.ALLOW),
                PermissionRule(pattern="*.env", action=PermissionAction.ASK),
                PermissionRule(pattern="bash", action=PermissionAction.ASK),
            ],
            default_action=PermissionAction.DENY
        )
    """

    rules: List[PermissionRule] = Field(default_factory=list)
    default_action: PermissionAction = PermissionAction.ASK

    def check(self, tool_name: str) -> PermissionAction:
        """
        检查工具权限

        按顺序匹配规则,返回第一个匹配的规则动作
        如果没有匹配的规则,返回默认动作
        """
        for rule in self.rules:
            if rule.matches(tool_name):
                return rule.action
        return self.default_action

    def add_rule(
        self, pattern: str, action: PermissionAction, description: Optional[str] = None
    ):
        """添加权限规则"""
        self.rules.append(
            PermissionRule(pattern=pattern, action=action, description=description)
        )

    @classmethod
    def from_dict(cls, config: Dict[str, str]) -> "PermissionRuleset":
        """
        从字典创建权限规则集

        示例:
            ruleset = PermissionRuleset.from_dict({
                "*": "allow",
                "*.env": "ask",
                "bash": "deny"
            })
        """
        rules = []
        for pattern, action_str in config.items():
            action = PermissionAction(action_str)
            rules.append(PermissionRule(pattern=pattern, action=action))
        return cls(rules=rules)

    @classmethod
    def default(cls) -> "PermissionRuleset":
        """创建默认权限规则集（允许所有操作）"""
        return cls(
            rules=[
                PermissionRule(pattern="*", action=PermissionAction.ALLOW),
            ],
            default_action=PermissionAction.ALLOW,
        )


class AgentInfo(BaseModel):
    """
    Agent配置信息 - 参考OpenCode的Agent.Info

    示例:
        agent_info = AgentInfo(
            name="primary",
            description="主Agent - 执行核心任务",
            mode=AgentMode.PRIMARY,
            model_id="claude-3-opus",
            max_steps=20,
            permission=PermissionRuleset.from_dict({
                "*": "allow",
                "*.env": "ask"
            })
        )
    """

    name: str
    description: Optional[str] = None
    mode: AgentMode = AgentMode.PRIMARY
    hidden: bool = False

    model_id: Optional[str] = None
    provider_id: Optional[str] = None

    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)

    max_steps: int = Field(default=200, gt=0, description="最大执行步骤数")
    timeout: int = Field(default=300, gt=0, description="超时时间(秒)")

    permission: PermissionRuleset = Field(default_factory=PermissionRuleset)

    color: str = Field(default="#4A90E2", description="颜色标识")

    prompt: Optional[str] = None
    prompt_file: Optional[str] = None

    options: Dict[str, Any] = Field(default_factory=dict)

    tools: List[str] = Field(default_factory=list, description="可用的工具列表")
    excluded_tools: List[str] = Field(
        default_factory=list, description="排除的工具列表"
    )

    # VIS 推送配置
    enable_vis_push: bool = Field(
        default=True, description="是否启用 VIS 消息推送（用于 vis_window3 渲染）"
    )
    vis_push_thinking: bool = Field(
        default=True, description="是否推送 thinking 内容到 VIS"
    )
    vis_push_tool_calls: bool = Field(
        default=True, description="是否推送工具调用信息到 VIS"
    )

    task_scene: TaskScene = Field(
        default=TaskScene.GENERAL,
        description="任务场景类型，决定默认的上下文和Prompt策略",
    )

    context_policy: Optional[ContextPolicy] = Field(
        default=None, description="上下文策略配置，覆盖场景默认配置"
    )

    prompt_policy: Optional[PromptPolicy] = Field(
        default=None, description="Prompt策略配置，覆盖场景默认配置"
    )

    tool_policy: Optional[ToolPolicy] = Field(
        default=None, description="工具策略配置，覆盖场景默认配置"
    )

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "name": "primary",
                "description": "主Agent - 执行核心任务",
                "mode": "primary",
                "model_id": "claude-3-opus",
                "max_steps": 20,
                "permission": {
                    "rules": [
                        {"pattern": "*", "action": "allow"},
                        {"pattern": "*.env", "action": "ask"},
                    ],
                    "default_action": "ask",
                },
            }
        }

    def get_effective_context_policy(self) -> ContextPolicy:
        """
        获取生效的上下文策略

        优先级：自定义配置 > 场景默认配置

        Returns:
            ContextPolicy: 生效的上下文策略
        """
        if self.context_policy:
            return self.context_policy

        from derisk.agent.core_v2.scene_registry import SceneRegistry

        profile = SceneRegistry.get(self.task_scene)
        if profile:
            return profile.context_policy

        return ContextPolicy()

    def get_effective_prompt_policy(self) -> PromptPolicy:
        """
        获取生效的Prompt策略

        优先级：自定义配置 > 场景默认配置

        Returns:
            PromptPolicy: 生效的Prompt策略
        """
        if self.prompt_policy:
            return self.prompt_policy

        from derisk.agent.core_v2.scene_registry import SceneRegistry

        profile = SceneRegistry.get(self.task_scene)
        if profile:
            return profile.prompt_policy

        return PromptPolicy()

    def get_effective_tool_policy(self) -> ToolPolicy:
        """
        获取生效的工具策略

        优先级：自定义配置 > 场景默认配置 > 工具列表

        Returns:
            ToolPolicy: 生效的工具策略
        """
        if self.tool_policy:
            return self.tool_policy

        from derisk.agent.core_v2.scene_registry import SceneRegistry

        profile = SceneRegistry.get(self.task_scene)
        if profile:
            tool_policy = profile.tool_policy.copy()
            if self.tools:
                tool_policy.preferred_tools = self.tools
            if self.excluded_tools:
                tool_policy.excluded_tools = self.excluded_tools
            return tool_policy

        return ToolPolicy(
            preferred_tools=self.tools,
            excluded_tools=self.excluded_tools,
        )

    def get_effective_temperature(self) -> float:
        """获取生效的温度参数"""
        if self.temperature is not None:
            return self.temperature
        prompt_policy = self.get_effective_prompt_policy()
        return prompt_policy.temperature

    def get_effective_max_tokens(self) -> int:
        """获取生效的最大token数"""
        if self.max_tokens is not None:
            return self.max_tokens
        prompt_policy = self.get_effective_prompt_policy()
        return prompt_policy.max_tokens

    def with_scene(self, scene: TaskScene) -> "AgentInfo":
        """
        创建指定场景的新AgentInfo

        Args:
            scene: 任务场景

        Returns:
            AgentInfo: 新的配置实例
        """
        return AgentInfo(**{**self.dict(), "task_scene": scene})

    def with_context_policy(self, policy: ContextPolicy) -> "AgentInfo":
        """创建指定上下文策略的新AgentInfo"""
        return AgentInfo(**{**self.dict(), "context_policy": policy})

    def with_prompt_policy(self, policy: PromptPolicy) -> "AgentInfo":
        """创建指定Prompt策略的新AgentInfo"""
        return AgentInfo(**{**self.dict(), "prompt_policy": policy})


# ========== 预定义Agent ==========

PRIMARY_AGENT = AgentInfo(
    name="primary",
    description="主Agent - 执行核心任务,具备完整工具权限",
    mode=AgentMode.PRIMARY,
    permission=PermissionRuleset(
        rules=[
            PermissionRule(
                pattern="*",
                action=PermissionAction.ALLOW,
                description="默认允许所有工具",
            ),
            PermissionRule(
                pattern="*.env",
                action=PermissionAction.ASK,
                description="敏感配置文件需要确认",
            ),
            PermissionRule(
                pattern="doom_loop",
                action=PermissionAction.ASK,
                description="死循环风险操作需要确认",
            ),
        ],
        default_action=PermissionAction.ALLOW,
    ),
    max_steps=30,
    color="#4A90E2",
)

PLAN_AGENT = AgentInfo(
    name="plan",
    description="规划Agent - 只读分析和代码探索",
    mode=AgentMode.PRIMARY,
    permission=PermissionRuleset(
        rules=[
            PermissionRule(
                pattern="read",
                action=PermissionAction.ALLOW,
                description="允许读取文件",
            ),
            PermissionRule(
                pattern="glob",
                action=PermissionAction.ALLOW,
                description="允许文件搜索",
            ),
            PermissionRule(
                pattern="grep",
                action=PermissionAction.ALLOW,
                description="允许内容搜索",
            ),
            PermissionRule(
                pattern="webfetch",
                action=PermissionAction.ALLOW,
                description="允许网页抓取",
            ),
            PermissionRule(
                pattern="write",
                action=PermissionAction.DENY,
                description="禁止写入文件",
            ),
            PermissionRule(
                pattern="edit", action=PermissionAction.DENY, description="禁止编辑文件"
            ),
            PermissionRule(
                pattern="bash",
                action=PermissionAction.ASK,
                description="Shell命令需确认",
            ),
        ],
        default_action=PermissionAction.DENY,
    ),
    max_steps=15,
    color="#7B68EE",
)

EXPLORE_SUBAGENT = AgentInfo(
    name="explore",
    description="代码库探索子Agent",
    mode=AgentMode.SUBAGENT,
    hidden=False,
    max_steps=10,
    permission=PermissionRuleset(
        rules=[
            PermissionRule(pattern="read", action=PermissionAction.ALLOW),
            PermissionRule(pattern="glob", action=PermissionAction.ALLOW),
            PermissionRule(pattern="grep", action=PermissionAction.ALLOW),
        ],
        default_action=PermissionAction.DENY,
    ),
    color="#32CD32",
)

CODE_SUBAGENT = AgentInfo(
    name="code",
    description="代码编写子Agent",
    mode=AgentMode.SUBAGENT,
    max_steps=15,
    permission=PermissionRuleset(
        rules=[
            PermissionRule(pattern="read", action=PermissionAction.ALLOW),
            PermissionRule(pattern="write", action=PermissionAction.ALLOW),
            PermissionRule(pattern="edit", action=PermissionAction.ALLOW),
            PermissionRule(pattern="glob", action=PermissionAction.ALLOW),
            PermissionRule(pattern="grep", action=PermissionAction.ALLOW),
            PermissionRule(pattern="bash", action=PermissionAction.ASK),
        ],
        default_action=PermissionAction.DENY,
    ),
    color="#FF6347",
)

# 内置Agent注册表
BUILTIN_AGENTS: Dict[str, AgentInfo] = {
    "primary": PRIMARY_AGENT,
    "plan": PLAN_AGENT,
    "explore": EXPLORE_SUBAGENT,
    "code": CODE_SUBAGENT,
}


def get_agent_info(name: str) -> Optional[AgentInfo]:
    """获取预定义的Agent配置"""
    return BUILTIN_AGENTS.get(name)


def register_agent(info: AgentInfo):
    """注册自定义Agent"""
    BUILTIN_AGENTS[info.name] = info
