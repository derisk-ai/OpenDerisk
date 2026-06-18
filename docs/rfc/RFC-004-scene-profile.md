# RFC-004 · Scene/Profile 声明式配置

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-18 |

---

## 1. 背景与问题

随着 Agent 应用场景增多（数据诊断、性能分析、代码审查、文档生成等），每种场景在 prompt、可用工具、权限策略、流程阶段上有显著差异。当前的承载方式有：

- `agent/core/agent_info.py:AgentInfo` —— 已有声明式配置（name、prompt、tools、permission 等），支持 `from_markdown` 解析 YAML frontmatter；
- `gpts_app` 数据库表 + `GptsApp` 模型 —— 应用元数据；
- `GptsApp.scenes: List[str]` —— 一组 `.md` 场景文件路径，加载到沙箱供 Agent 使用。

**问题**：

1. **场景文件是裸 markdown**，没有结构定义——一个"诊断场景"可能包含意图说明 + 工具约束 + 阶段流程 + 钩子配置，但当前没有 schema，全靠 prompt 自由文本表达。
2. **AgentInfo 是单一角色配置**，缺少"工作流阶段"（discover → analyze → report）的概念——多阶段任务里每阶段的可用工具、prompt 加成、退出条件都要硬编码到 ReAct loop。
3. **没有 SceneRegistry**，无法在运行时枚举"我有哪些可用场景"，也不便统一发现/加载/版本管理。
4. **场景间切换不显式**：当前没有"我现在在分析阶段，下一步该进入报告阶段"的状态机表达——靠 LLM 在 prompt 里隐式判断，不可控。

## 2. 设计目标与原则

| 原则 | 含义 |
|---|---|
| **以 AgentInfo 为基底** | 不引入并行的"v2 配置体系"；SceneProfile 是 AgentInfo 的扩展，能向下兼容 |
| **声明优于硬编码** | 阶段、工具白名单、权限规则、可选 hook 全部写在配置里；ReAct 循环从配置读取行为 |
| **可枚举可版本化** | SceneRegistry 提供 `list / get / version`，配置文件内带 `version` 字段 |
| **失败回退到通用 Agent** | 无场景配置时回退到现有 AgentInfo 行为，不破坏单 Agent 流程 |
| **解耦机制与策略** | 阶段切换、hook 触发、工具限制是机制；具体业务由配置表达 |

## 3. 核心机制

### 3.1 配置数据模型

`SceneProfile` 继承自 `AgentInfo`，在其上增加阶段与场景维度：

```python
class WorkflowPhase(BaseModel):
    name: str                                  # 阶段名 e.g. "discover"
    description: Optional[str]
    
    # 阶段内 prompt 加成（追加到 system prompt 末尾）
    prompt_addendum: Optional[str] = None
    
    # 阶段内工具白名单（覆盖 SceneProfile.tools）
    tools: Optional[Dict[str, bool]] = None
    
    # 阶段内权限规则（与 SceneProfile.permission 合并，see RFC-003）
    permission: Optional[Dict[str, Any]] = None
    
    # 退出条件：满足任一即视为本阶段完成
    exit_conditions: List[ExitCondition] = []
    
    # 阶段进入/退出钩子（接 RFC-001 SystemEventManager 事件）
    on_enter: Optional[List[str]] = None       # 监听器名列表
    on_exit: Optional[List[str]] = None


class ExitCondition(BaseModel):
    type: Literal["llm_signal", "tool_called", "step_count", "custom"]
    value: Any        # llm_signal: signal name; tool_called: tool name; step_count: int


class SceneProfile(AgentInfo):
    version: str = "1"
    
    # 工作流阶段（按声明顺序前进；无阶段时退化为单阶段 ReAct）
    phases: List[WorkflowPhase] = []
    
    # 场景级 hook 绑定（接 RFC-001）
    hooks: Dict[str, List[str]] = {}    # event_type -> listener names
    
    # 关联的辅助文件（绑定到沙箱）
    scene_files: List[str] = []
    
    # 元数据
    tags: List[str] = []
    author: Optional[str] = None
```

### 3.2 配置文件格式（保持 markdown + YAML frontmatter）

```markdown
---
name: db-diagnosis
version: 1
description: 数据库性能诊断
mode: primary
prompt_file: ./prompts/db-diagnosis.md
tools:
  bash: true
  query_db: true
  view: true
permission:
  bash: ask
  query_db: allow
phases:
  - name: discover
    description: 收集现场信息（schema / 慢查询 / 监控指标）
    tools:
      bash: false      # 发现阶段不允许 bash
      query_db: true
    exit_conditions:
      - type: tool_called
        value: collect_metrics
  - name: analyze
    description: 形成假设并验证
    prompt_addendum: |
      你现在进入分析阶段，必须基于已收集数据形成假设
      在没有充分证据前不要给出最终结论。
    exit_conditions:
      - type: llm_signal
        value: ANALYSIS_DONE
  - name: report
    description: 生成诊断报告
    tools:
      query_db: false  # 报告阶段不再查库
hooks:
  agent_build_complete: [diagnosis_session_init]
  llm_before_thinking: [inject_diagnosis_context]
  agent_run_complete: [generate_diagnosis_report]
scene_files:
  - schemas/users_schema.md
  - runbooks/slow_query_playbook.md
tags: [database, diagnosis]
author: dba-team
---

# 数据库性能诊断 Agent

你是一个专业的数据库诊断助手 ……
```

### 3.3 SceneRegistry

```python
class SceneRegistry:
    """场景配置的中心仓储。"""
    
    def register(self, profile: SceneProfile) -> None
    def get(self, name: str, version: Optional[str] = None) -> SceneProfile
    def list(self, tag: Optional[str] = None) -> List[SceneProfile]
    
    @classmethod
    def from_directory(cls, path: str) -> "SceneRegistry":
        """扫描 .md 场景文件，解析 frontmatter，注册全部 profile。"""
```

加载源：
- 内置场景：`packages/derisk-core/src/derisk/agent/scenes/builtin/*.md`
- 用户场景：`${DERISK_HOME}/scenes/*.md`
- 应用关联：`GptsApp.scenes` 仍是文件路径列表，加载时由 SceneRegistry 解析

### 3.4 阶段引擎

ReAct 主循环增加最小的"当前阶段"状态：

```python
class PhaseRunner:
    def __init__(self, profile: SceneProfile, agent: ConversableAgent):
        self._phases = profile.phases
        self._index = 0
    
    @property
    def current(self) -> Optional[WorkflowPhase]:
        return self._phases[self._index] if self._index < len(self._phases) else None
    
    def effective_prompt(self, base_prompt: str) -> str:
        """合并 base prompt + 当前阶段 prompt_addendum。"""
        if self.current and self.current.prompt_addendum:
            return f"{base_prompt}\n\n{self.current.prompt_addendum}"
        return base_prompt
    
    def effective_tools(self) -> Dict[str, bool]:
        """合并 SceneProfile.tools + current.tools（后者覆盖前者）。"""
        ...
    
    def check_exit(self, event: SystemEvent) -> bool:
        """根据 exit_conditions 判定是否进入下一阶段。"""
        ...
    
    def advance(self) -> None:
        """触发 on_exit / on_enter hook，进入下一阶段。"""
        ...
```

阶段切换发射 `SystemEventType.PHASE_TRANSITION`（接 RFC-001）。

### 3.5 失败回退

- 配置缺失 / 解析失败 → 回退到现有 `AgentInfo` 行为，记 WARN 日志，不中断流程；
- 阶段定义不完整（无 phases / 单 phase）→ 退化为现有单阶段 ReAct，行为与今天一致；
- hook 名解析失败 → 跳过该 hook，记 WARN，不影响主流程（与 RFC-001 listener 异常隔离一致）。

## 4. 演进路径

| 步骤 | 改动 | 代码量 | 风险 |
|---|---|---|---|
| **S1** | 新增 `agent/core/scene_profile.py:SceneProfile`（继承 AgentInfo，加 phases/hooks/scene_files 字段） | ~150 行 | 低 |
| **S2** | 新增 `agent/core/scene_registry.py:SceneRegistry` + `.md` 扫描加载 | ~200 行 | 低 |
| **S3** | 新增 `agent/core/phase_runner.py:PhaseRunner` + 4 个 `ExitCondition` 类型 | ~250 行 | 中 |
| **S4** | `ReActMasterAgent` 集成 PhaseRunner：每步合并 effective_prompt / effective_tools；阶段切换发事件 | ~100 行 | 中 |
| **S5** | 在 `gpts_app` 加载链路中：若 app 关联 scene name，加载到 SceneRegistry → 实例化 SceneProfile | ~80 行 | 中 |
| **S6** | 内置 2-3 个示例 SceneProfile（如 generic-react, db-diagnosis-template） | ~200 行（含 prompt） | 低 |

**总计**：~980 行新增。AgentInfo 与 ReAct 主流程仅打补丁，不重写。

## 5. 不做什么

- **不引入 SceneSwitchDetector / SceneAwareAgent / SceneRuntimeManager 等多层管理器**——`PhaseRunner` 单类够用；多类拆分等出现真实诉求再做。
- **不做"场景间动态切换"**（即 LLM 中途判定"应该切换到另一场景"）——阶段是声明式的有向流程；跨场景切换是上层 orchestration，不在本 RFC。
- **不做可视化场景编辑器**——本 RFC 只定义后端模型与运行时；前端配置 UI 是独立产品工作。
- **不做"自适应阶段"**（运行中根据 LLM 判断动态插入新阶段）——配置是契约，运行时不应自改。
- **不引入"AgentRoleDefinition / SceneTriggerType"** 等高阶抽象——单 Agent + Phase 序列已能覆盖 90% 场景；多角色协作交给 [多 Agent RFC]。
- **不在 SceneProfile 里耦合数据存储**（如直接绑 DB connection）—— 配置只声明 tools / permission，资源装配仍由现有 ResourceManager 处理。
- **不做配置热更新**——profile 改动需 Agent 重建；运行中改配置带来一致性问题不值得换便利。

## 6. 验收标准

| 编号 | 项 | 判定 |
|---|---|---|
| AC-1 | `.md` 场景文件能被 SceneRegistry 解析为 SceneProfile，frontmatter schema 校验生效 | 单测（含合法/非法两套 fixture） |
| AC-2 | SceneProfile 在 ReAct 主流程中按 phases 顺序推进；每阶段 effective_prompt / effective_tools 与配置一致 | 集成测试 |
| AC-3 | 阶段切换发射 `PHASE_TRANSITION` 事件，订阅者能收到 from/to phase 信息 | 单测 |
| AC-4 | exit_conditions 四种类型（llm_signal / tool_called / step_count / custom）均能正确触发阶段切换 | 单测 × 4 |
| AC-5 | 配置缺失 / 解析失败时，Agent 退化为 AgentInfo 行为，不中断 | 故障注入测试 |
| AC-6 | hook 名解析失败时跳过该 hook，记 WARN，不影响主流程 | 单测 |
| AC-7 | SceneRegistry.list 能按 tag 过滤；同名不同 version 共存 | 单测 |
| AC-8 | 现有不依赖场景的 Agent 流程行为不退化 | 现有测试 100% 通过 |

## 7. 开放问题

1. SceneProfile 与 GptsApp 的关系：app 一对一绑 profile，还是 app 配置可继承/覆盖 profile？建议：app 引用 profile.name + 可选 overrides 块，避免双重事实源。
2. 阶段失败如何处理？exit_conditions 全部不满足且达到 step 上限时，是回到上一阶段、跳到下一阶段、还是终止？建议：默认终止 + 可在阶段配置 `on_failure: next | retry | abort`。
3. `prompt_file: ./prompts/x.md` 的相对路径基准——相对于场景 .md 所在目录，还是相对于工作目录？建议：相对于场景 .md 所在目录，便于场景包整体迁移。
4. SceneProfile 是否进入 DB？建议：本 RFC 不做。先以文件 + Registry 为权威，简化版本管理；如未来需要在线编辑再补 DB 后端。
