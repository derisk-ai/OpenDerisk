# RFC-003 · 统一权限模型

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-18 |

---

## 1. 背景与问题

工具调用权限是 Agent 框架的关键 trust 边界——危险命令（rm、写远端、网络请求）必须能由用户精细控制。当前 v1 已有两条独立机制，但**没有打通**：

1. **声明式规则**：`agent/core/agent_info.py` 中的 `PermissionRuleset` + `PermissionRule`（含 `pattern` glob + `action ∈ {allow, deny, ask}`），支持 `from_config` 与 `merge`。
2. **交互式追问**：`react_master_agent.py:800 _ask_user_permission` callback + `interaction_extension.request_tool_authorization`——执行前向用户提问拿授权。

**问题**：

- 这两套机制目前是**独立调用点**——`PermissionRuleset` 提供规则但谁去调它没明确；`request_tool_authorization` 直接弹问，不会先查规则。
- 没有"会话级记忆"：用户在第 1 次同意 `bash:git status` 后，第 N 次再被问同样的事。
- 没有"分层规则"概念：系统默认规则 / 应用级规则 / 会话级规则的优先级与合并语义不清晰。
- `PermissionAction` 只有三态（allow/deny/ask），缺少**应用范围**（per-call / per-session / per-app）的表达。

## 2. 设计目标与原则

| 原则 | 含义 |
|---|---|
| **规则优先，交互兜底** | 任何工具调用先查规则；规则=ask 时再发起交互；交互结果可缓存为会话规则 |
| **分层合并语义清晰** | system < app < user-session 三层，后者覆盖前者；任何一层都可显式 deny 兜底 |
| **复用现有抽象** | `PermissionRule` / `PermissionAction` / `PermissionRuleset` 保留；新增的是**编排者** `PermissionService` 与会话层规则缓存 |
| **失败安全方向 = deny** | 规则解析异常、callback 超时、配置缺失 → deny 而非 allow，绝不"放行未知" |
| **可审计** | 每次决策记录"决策结果 + 来源层 + 命中规则"，落入事件流（接 RFC-001）便于审计 |

## 3. 核心机制

### 3.1 决策流水线

```python
class PermissionService:
    """统一的权限决策入口。任何工具调用前必须经此判定。"""
    
    def __init__(
        self,
        system_ruleset: PermissionRuleset,    # 来自系统默认配置
        app_ruleset: PermissionRuleset,       # 来自 agent 应用配置
        ask_callback: AskCallback,            # 交互式追问（已有 _ask_user_permission）
    ):
        self._session_ruleset = PermissionRuleset()    # 会话级动态规则
        ...
    
    async def check(
        self,
        tool_name: str,
        args: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> PermissionDecision:
        # 1. 合并三层规则（顺序：system → app → session，后覆盖前）
        merged = PermissionRuleset.merge(self._system, self._app, self._session_ruleset)
        action = merged.check(tool_name, command=args.get("command"))
        
        # 2. 显式判定
        if action == PermissionAction.DENY:
            return PermissionDecision(allowed=False, source="rule", rule_layer=...)
        if action == PermissionAction.ALLOW:
            return PermissionDecision(allowed=True, source="rule", rule_layer=...)
        
        # 3. ASK：交互式追问
        try:
            user_choice = await self._ask(tool_name, args, reason)
        except (TimeoutError, asyncio.CancelledError):
            return PermissionDecision(allowed=False, source="timeout")
        
        # 4. 把用户选择记入会话规则（供后续同 tool+args 命中复用）
        if user_choice.remember_for_session:
            self._session_ruleset.add_rule(
                PermissionRule(
                    action=PermissionAction.ALLOW if user_choice.allowed else PermissionAction.DENY,
                    pattern=self._signature(tool_name, args),
                    permission=tool_name,
                )
            )
        
        return PermissionDecision(
            allowed=user_choice.allowed,
            source="interactive",
            remembered=user_choice.remember_for_session,
        )
```

### 3.2 用户回答的扩展语义

现有 `_ask_user_permission` 只返回 `bool`。扩展为：

```python
class UserPermissionChoice(BaseModel):
    allowed: bool
    remember_for_session: bool = False    # "本次会话内不再询问"
    remember_for_app: bool = False        # "对此应用永久允许"（写入 app 配置）
```

UI 侧呈现三个选项：**只此一次** / **本次会话内允许** / **永久允许**。

### 3.3 可审计的决策事件

每次 `check` 完成后，发射一个事件（接 RFC-001 的 `SystemEventManager`）：

```python
SystemEventType.PERMISSION_CHECKED:
    payload = {
        "tool": "bash",
        "args_signature": "git status",
        "decision": "allow" | "deny",
        "source": "rule" | "interactive" | "timeout",
        "rule_layer": "system" | "app" | "session" | None,
        "rule_pattern": "bash:git*" | None,
        "remembered_at_layer": "session" | "app" | None,
    }
```

便于审计与故障排查（"为什么这个工具被拒了？"）。

### 3.4 失败安全

| 异常情况 | 行为 |
|---|---|
| 规则解析异常 | 跳过该规则，记 ERROR；继续按剩余规则判定 |
| 三层规则全无匹配 | 默认 ASK（不是 ALLOW） |
| `ask_callback` 抛异常 / 超时 | 返回 DENY |
| `PermissionService` 自身崩溃 | 上层捕获后默认 DENY 并通知用户 |

绝不出现"未知 → 放行"路径。

## 4. 演进路径

| 步骤 | 改动 | 代码量 | 风险 |
|---|---|---|---|
| **S1** | 新增 `agent/core/permission.py:PermissionService`（编排三层 + ask） | ~200 行 | 中 |
| **S2** | 扩展 `UserPermissionChoice`（含 remember 标志），改造 UI 协议（弹窗组件 + 三按钮） | ~80 行 + 前端 | 中 |
| **S3** | `ReActMasterAgent` / `InteractionExtension.request_tool_authorization` 改为先调 `PermissionService.check` | ~50 行 | 中（影响所有工具调用） |
| **S4** | `DoomLoopDetector` 的 `permission_callback` 改用 `PermissionService` 而非裸 ask | ~20 行 | 低 |
| **S5** | 接入 RFC-001 的 `PERMISSION_CHECKED` 事件 + 决策日志 | ~50 行 | 低 |
| **S6** | "永久允许"写回 app 配置的持久化路径（涉及 gpts_app 表） | ~100 行 | 中 |

**总计**：~500 行新增。`PermissionRuleset` 与 `PermissionRule` 不变。

## 5. 不做什么

- **不做基于角色（RBAC）的权限模型**——agent 框架场景里"用户"是单一交互者，多用户分权是上层（auth / iam）的事。
- **不做工具内权限检查**——权限统一在 `PermissionService.check` 决策，工具自身不再各自实现 `_check_permission`。避免散点决策导致策略不一致。
- **不做"危险等级评分"自动判定**（如 LLM 给出 risk_level）——风险等级是经验决策，不应交给模型；规则 + 用户决策足够。
- **不做"基于上下文的权限"**（如"只在工作时间允许 X"）——超出 agent 框架职责，留给 enterprise 部署层。
- **不做权限规则的版本控制 / 审批工作流**——这是 IAM 系统的事；本 RFC 只解决"运行时决策与执行"。
- **不做"链式 callback"**（多 callback 串行投票）——单一 ask_callback 即可；多决策者场景由更高层封装。

## 6. 验收标准

| 编号 | 项 | 判定 |
|---|---|---|
| AC-1 | system / app / session 三层规则按 `merge` 后顺序匹配，后层覆盖前层 | 单测 |
| AC-2 | 规则=DENY 时不发起交互、立即拒绝，并记决策事件 | 单测 + 事件验证 |
| AC-3 | 规则=ASK 时发起交互，用户选"本次会话内允许"后续相同 tool+args 命中 session 规则不再询问 | 集成测试 |
| AC-4 | `ask_callback` 超时返回 DENY；不出现 silent allow | 故障注入测试 |
| AC-5 | 规则解析异常不导致整个 PermissionService 崩溃，仅跳过该规则 + ERROR 日志 | 单测 |
| AC-6 | "永久允许"选择能写回 app 配置，下次启动仍生效 | e2e |
| AC-7 | 现有 `_ask_user_permission` / `request_tool_authorization` 调用链路语义不退化 | 现有测试 100% 通过 |

## 7. 开放问题

1. 三层之外是否需要"全局组织级"规则（如企业部署中的强制 deny 列表）？建议：**先不引入第四层**；用 system 层加载企业配置即可，结构上仍是三层。
2. `args_signature` 的精度——粗（仅 tool name）则缓存命中高但安全性差；细（含全部 args）则缓存命中低。建议：**白名单字段** + 危险参数（command、url、file path）必入 signature。
3. "永久允许"写回 app 配置是否会被 app 配置 reload 覆盖？需要约定：用户选择写到 app 配置的**独立子节**（如 `permissions.user_overrides`），reload 时 merge 而非 overwrite。
4. 超时阈值（默认多少？）—— 用户可能在做别的事，过短会误拒。建议：交互层支持"提醒重试"（先短超时 30s，超时后转后台等待，最长 5 分钟），而非一次性硬拒。
