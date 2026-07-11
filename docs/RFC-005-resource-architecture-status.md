# RFC-005 资源架构现状(2026-07-11)

> 本文回答"现在资源到底用新协议还是旧协议、为什么旧代码清不干净"。
> 起因:多轮清理后,旧 `Resource` 子类仍存在,触发架构现状澄清。

---

## 一、一句话现状

**RFC-005 把"渲染出口"迁到了新协议(`ResourceFacade` + 各 capability `declare`),但"连接/数据初始化"仍留在旧 `Resource` 子类的构造期(`__init__`),新协议设计的 `Executor.prepare` 基本是空壳。** 两者当前是分工共存,不是谁取代谁。

```
AgentResource 配置(type + value)
   │
   ├─► ResourceManager.build_resource            ──[旧]──► 旧 Resource 子类实例
   │        DatasourceResource.__init__         : 建 DB 连接(I/O)
   │        KnowledgePackSearchResource.__init__: 查 space + rag init(I/O)
   │        MCPSSEToolPack.preload_resource     : 连 MCP server(I/O)
   │        DeriskSkillResource.__init__        : 查 skill_code/path(I/O)
   │        GptAppResource / MemoryResource     : 纯配置,无 I/O
   │
   └─► agent.resource (旧实例的 ResourcePack)
          │
          └─► ResourceFacade.assemble           ──[新]──► _to_resource_protocol
                  旧实例 ──wrapper 包装──► ResourceProtocol
                  各 capability.declare() 渲染 system/tools
                  Executor.prepare = no-op(连接已由旧类构造期建好)
```

---

## 二、各职责当前归属

| 职责 | 谁在做 | 协议归属 |
|---|---|---|
| system prompt / tools **渲染** | `ResourceFacade.assemble` + 各 `capability.declare()` | **新协议** ✅ |
| DB **连接建立** | `DatasourceResource.__init__` 调 `local_db_manager.get_connector` | **旧类构造期** |
| knowledge **space 查询 + rag/yuque init** | `KnowledgePackSearchResource.__init__` | **旧类构造期** |
| MCP **server 连接 + 工具拉取** | `MCPSSEToolPack.preload_resource`(异步) | **旧类** |
| skill **code/path 解析** | `DeriskSkillResource.__init__` 查 Skill service | **旧类构造期** |
| app **属性** | `GptAppResource.__init__`(纯配置) | **旧类但无 I/O** |
| memory **参数** | `MemoryResource.__init__`(纯配置) | **旧类但无 I/O** |
| 沙箱 **实例初始化** | `agent_chat` 独立路径 `sandbox_manager` | 独立于资源系统(非 AgentResource 类型) |
| `Executor.prepare`(RFC-005 §3.4 设计口子) | **基本 no-op** | **新协议但未落实** ⚠️ |

关键事实:`DBExecutor.prepare` 注释自述"connector 由 build_resource 已构造"——即新协议设计了连接就绪口,但实际没把 I/O 挪进去,仍依赖旧类构造期建好。

---

## 三、本已清理的死代码(渲染壳里真死部分)

本轮实际删掉的是"旧协议路径"里**已无运行时引用**的部分,渲染出口因此彻底统一到新协议:

- `core/interface/input.py` + `executor.py` —— 老 import shim(迁到 canonical `core/interface/resource/{bundle,tool_entry,data_requirement,executor,dispatcher}`)
- `prompt_assembly/{resource_facade,resource_protocol,sandbox_resource,resource_injector}.py` —— 4 个 shim/桥接
- `capabilities/legacy_adapter.py`(`LegacyResourceAdapter`)—— facade legacy 桥接兜底
- facade 的 `if not declared_any` legacy fallback —— 换"无资源→空 bundle"早返回
- `PromptAssembler.assemble_system_prompt` + `_assemble_resources` + `_extract_*` + resource_injector import —— 老资源注入路径(system prompt 现全走 facade)
- `react_master` 里 `ResourceContext.from_v1_agent` dead 构建(仅用于日志)

验证:full affected suites 159 passed / 69 skipped(跳过为既有 async 无插件);grep gate 确认零残留引用。

---

## 四、为什么旧 `Resource` 子类清不干净

旧类当前承担两个角色:**(a) `ResourceManager` 的构造入口;(b) 连接/service 初始化的执行者。** 新协议只接管了 (a) 之后的**渲染**。

退役旧类的前置工作量(项项需先做才能删):

1. **DB 连接建立** → 挪进 `DBExecutor.prepare`(从 `db_name`/`db_id` 重建 connector)。工具层 `_resolve_db_from_agent` 已能从 `db_name` 重建连接,证明可行。
2. **knowledge space 水合 + rag service init** → 挪进 `KnowledgeExecutor.prepare`(declare 只需 name/id/desc 文本,rag service 仅检索用)。
3. **MCP server 连接 + 工具拉取** → 挪进 `MCPExecutor.prepare`(**该 executor 尚未实现**,implementation-summary 已标"MCPExecutor 待续")。
4. **skill_code/path 解析** → 挪进 `SkillExecutor.prepare` 或 lazy `declare`(UI 保存的配置已带 skill_code+path,多数情况免 I/O)。
5. **运行时按旧类型分键的站点** 改成按 `capability_id` 字符串:
   - `extract_resource_map`(`resource_utils.py`,用 `resource.type()`)
   - `base_agent._check_have_resource(DBResource/AppResource/RetrieverResource)`(isinstance)
   - `base_agent._inject_resource_based_tools`(基于 _check_have_resource)
   - `react_master.register_variables` 的 `var_skills`/`var_available_agents`/`var_available_knowledges`(读 `skill_meta`/`app_code`/`knowledge_spaces`)
   - `tool_parser` / `agent_adapter` / `reasoning_action` / `v2 tool_context_factory`(读 `resource_map` 假定旧类型)
6. 然后旧 `Resource` 子类、各 capability `register_wrappers`、`ResourceManager` 旧构造路径才能删。

这是独立的大型重构(动 20+ 文件、4 个 executor 补 prepare I/O、多处运行时消费者重写),非收尾。

---

## 五、各 capability 退役就绪度

| capability | 旧类构造期 I/O | 直接从 config 构造 ResourceProtocol | 退役前置 |
|---|---|---|---|
| App | 无 | ✅ 原生构造已全 | 仅需步骤 5 |
| Memory | 无 | ✅ declare 空,无需 config | 仅需步骤 5 |
| Skill(AgentSkill 普通) | 无 | ✅ 纯 dict 组装 | 仅需步骤 5 |
| Skill(derisk) | skill_code/path 查询 + FS 检查 | ✅ 若 config 已带 code/path | 步骤 4 + 5 |
| DB | 建 live connector + 查 connect_config | ❌ db_type/dialect/connector 非在 config | 步骤 1 + 5 |
| Knowledge | per-id get_knowledge_space + rag init | ❌ config 只有 id,文本需查 | 步骤 2 + 5 |
| MCP | preload 连 server 拉工具 | ❌ declare 依赖已加载工具 | 步骤 3 + 5 |
| Sandbox | 无(非 AgentResource 类型) | N/A(走 runtime sandbox_manager) | 不参与 |
| Workflow / ReasoningEngine | 无 | 无 wrapper | 部署 0 出现,暂挂 |

---

## 六、建议的退役推进顺序(独立任务)

1. **阶段 A**:迁零 I/O 路径(App / Memory / 普通 Skill)——证明"构造入口切到 ResourceProtocol"可行。
2. **阶段 B**:补 `DBExecutor.prepare` 的 connector 建立(从 db_name/db_id),让 DB capability 不再依赖旧 `DatasourceResource` 构造期。
3. **阶段 C**:补 `KnowledgeExecutor.prepare` 的 space 水合 + rag service init。
4. **阶段 D**:实现 `MCPExecutor.prepare` 的 MCP 连接 + 工具拉取(替代 `preload_resource`)。
5. **阶段 E**:把 `extract_resource_map` / `_check_have_resource` / `register_variables` 等运行时站点改成按 `capability_id` 分键。
6. **阶段 F**:删旧 `Resource` 子类 + 各 capability `register_wrappers` + `ResourceManager` 旧构造路径。

每个阶段前跑 `packages/derisk-core/tests/agent/capabilities/` + `packages/derisk-serve/tests/derisk_serve/agent/capabilities/` + `packages/derisk-core/tests/core/interface/` + react_master 套件。

---

## 七、附:沙箱为何独立

沙箱不在 `ResourceType` enum(`base.py` 无 Sandbox),不注册进 `ResourceManager`,不是 `AgentResource` 类型。它在 `agent_chat.py` 走独立创建路径(`sandbox_manager` → `improved_local_runtime`),sandbox env 经 `extra_static_contribs` 注入 facade。故沙箱初始化**不属于"资源协议旧/新"讨论范围**,其 `SandboxResource.declare_env` 已是新协议路径且独立可用。