# RFC-005 · Agent 资源协议框架

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-07-09 |

---

## 1. 背景与问题

Agent 的外部对接当前以 `AgentResource`(`derisk/agent/resource/base.py:344`)为入口,设计意图是"把外部资源统一转化为 Agent 上下文"。但承载这套意图的实现存在结构性问题,在"一个 Agent 绑定 20 种资源 + Pack 嵌套"的规模下既不优雅也跑不快:

1. **转化出口分裂、无统一契约**。资源转 prompt 片段走 `ResourceInjector.inject_all()`(`shared/prompt_assembly/resource_injector.py:972`,返回单个字符串),资源转工具走 `ToolPack.from_resource()`(`react_master_agent.py:649`)——两条互不相交的旁路。资源"能贡献什么输入"这个最该协议化的属性,被埋进 injector 的 `if resource_type` 枚举 + **类名字符串硬匹配**(`_is_app_resource` / `_is_database_resource` 等靠 `"AppResource" in class_name` 判定)。新增一种资源 = 改 injector,违反开闭。

2. **输入被当成字符串,装不下多模态/RAG**。现有 system prompt 是个拼接好的 `str`。多模态消费工具(把图片加载成 user 多模态消息)、RAG 回注(检索 chunks 注入 user turn)这些"工具行为反向修改输入"的能力,只能各自硬编码特例路径,没有任何统一机制承载。

3. **每轮全量即时渲染,无分层缓存**。`inject_all` 每次 `load_thinking_messages` 都重跑 `get_resources` → `_extract_*` → 模板 render。DB 资源还会**每轮实时查表列表**(`_get_database_table_list` 走 `get_table_names()`,可能全库扫)。配置在会话内不变却每轮重算,是延迟与 token 浪费的主因。

4. **资源与执行环境混为一谈**。`SANDBOX` 被塞进 `ResourceInjector` 当资源处理,但沙箱是执行底座。`ResourceManager.build_resource()`(`resource/manage.py:361`)对每条资源 `execute_to_thread` 丢线程池构造,会话内可复用却零缓存。

5. **演进无版本化**。`AgentResource.from_dict` 只处理 v1→v2 的 value 迁移;"资源贡献输入"的契约一旦演进,无机制保证旧资源行为不变,升级即 breaking。

**真实诉求**:这套"外部数据全资源化"的架构是后续 Agent 能力协议对接的核心。它需要一个稳定的输入层契约,把外部任何可用内容统一转化为 LLM 输入,且能持续演进、可缓存、生命周期可治理。

## 2. 设计目标与原则

| 原则 | 含义 |
|---|---|
| **输入层纯净** | 协议只关心"外部 → LLM 输入"的转化,不碰 model kwargs、不碰执行语义 |
| **统一机制零特例** | DB/知识/App/沙箱/多模态/RAG 全走同一套声明+消费+执行投影,禁止 `if 资源类型==X` 分支 |
| **Capability 双投影** | 不分"资源层 vs 环境层",一个能力有输入投影(declare/consume)+执行投影(executor),靠 `capability_id` 绑定 |
| **配置薄、实现厚** | 配置只存最小稳定标识(type+参数),转化逻辑在实现代码里可演进;新接外部数据 = 写一个类,存量配置零影响 |
| **declare 是纯函数** | 声明面无 I/O,需外部数据(如 DB schema)时声明 `data_requirement` 由执行投影回填;保证可缓存/可并发/可序列化 |
| **三态生命周期** | Contribution 分 CONFIG_STATIC/SESSION/TURN;Executor 有 prepare/execute/release;静态部分不被运行态抹除,保 prefix-cache |
| **演进版本化** | 每 binding 带 `protocol_version`,旧版走兼容 adapter,新旧共存不 breaking |
| **机制 ≠ 框架** | 在现有 `resource/` 与 `prompt_assembly/` 上原地引入,不推倒重写;存量资源默认委托现有 `_format_*_default`,行为字节不变 |

## 3. 核心机制

### 3.1 Capability 双投影模型

一个外部能力(Capability)带两个投影,用 `capability_id` 握手绑定:

```
                     ┌──────────────── Agent ────────────────┐
   外部能力 ───────▶ │  Capability                             │
                     │   ├─ 输入投影 (ResourceProtocol)         │   ──▶ InputBundle ──▶ LLM
                     │   │     declare()   声明面(纯函数)        │
                     │   │     consume()   消费面(工具回调改输入) │
                     │   └─ 执行投影 (Executor)                  │   ◀── ToolCall 执行
                     │           prepare() / execute() / release()│
                     └─────────────────────────────────────────┘
```

沙箱、DB、App、知识全是一等 Capability。沙箱不特殊:其输入投影是标准资源(env 信息进 system + run_python/write_file 进 tools),执行投影是**通用** executor(可被多 capability 的 tool 共享指向)。

### 3.2 输入载体 InputBundle(协议中心)

替代现有"system_prompt 字符串 + tools list 两条旁路"。一切资源/消费工具/Agent 自身的唯一动作都是"写一个 Contribution 写进某个 Slot",bundle 做合并,无外部拼字符串、无类名分发。

```python
class Slot(str, Enum):
    SYSTEM    = "system"      # system prompt(分段+有序)
    USER_PART = "user_part"   # 用户轮内容(含多模态 part)
    TOOLS     = "tools"       # 工具声明
    VAR       = "var"         # 可被模板引用的命名变量
    # model kwargs(temperature/tool_choice/...)永不在其中——不是输入层职责

class Lifetime(str, Enum):
    CONFIG_STATIC = "config"  # 配置态即定 → 缓存到配置变更
    SESSION       = "session" # 会话级(加载的图片/会话级检索)
    TURN          = "turn"    # 仅本轮(RAG inline chunks)

@dataclass
class Contribution:
    capability_id: str        # 来源能力 id
    slot: Slot
    order: int                # 槽内确定性排序
    content: Any              # str | ToolSpec | ContentPart | dict
    lifetime: Lifetime

@dataclass
class InputBundle:
    system: List[Contribution]
    user_parts: List[Contribution]
    tools: List[Contribution]
    vars: Dict[str, Contribution]

    def freeze(self) -> "FrozenBundle":
        """不可变快照:可缓存、可跨进程传递、可作协议对外锚点。"""
        ...
```

`TOOLS` 槽来源统一为两类,不搞第二套机制:资源贡献的 tools(`capability_id` 为各资源)+ Agent 自带 tools(`capability_id="agent:builtin"`,`lifetime=CONFIG_STATIC`)。

### 3.3 资源协议接口

```python
class ResourceProtocol(ABC):
    capability_id: ClassVar[str]
    protocol_version: ClassVar[int] = 1

    @classmethod
    @abstractmethod
    def declare(cls, config: "ResourceConfig") -> List[Contribution]:
        """声明面【纯函数,无 I/O】
        例:DB      → SYSTEM(库/表 schema)+ TOOLS(查表, execute_sql)
           App     → SYSTEM(app列表)+ TOOLS(sub_agent)
           Sandbox → SYSTEM(env信息)+ TOOLS(run_python, write_file, view)
        需外部数据(schema)时,Contribution.content 带 data_requirement,
        由执行投影预取后回填,再格式化。"""

    @classmethod
    def requires(cls, config) -> List[str]:
        """依赖哪些 executor_id。默认空。
        沙箱原生工具 requires=['sandbox'];沙箱-backed 分析工具同。"""
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        """【可选】消费面:工具执行后反改输入。默认不实现。
        ImageLoader → USER_PART(图片, SESSION)
        RagSearch   → USER_PART(chunks, TURN)"""
        return []
```

**关键纪律**:`ResourceProtocol` 的默认实现必须委托现有 `inject_xxx` 的 `_format_*_default` 与 `ToolPack.from_resource` 等价物。存量资源类不迁移、不改字节,仅给新资源覆盖用。

### 3.4 执行投影与生命周期

```python
class ReleaseReason(str, Enum):
    SESSION_END    = "session_end"
    AGENT_END      = "agent_end"
    CONFIG_CHANGED = "config_changed"
    ERROR          = "error"
    EXPLICIT       = "explicit"

class Executor(ABC):
    executor_id: str

    async def prepare(self) -> None:
        """就绪。默认 no-op。DB连接器→建连接池;沙箱→起实例。Agent 级一次。"""
    async def execute(self, call: ToolCall) -> Any: ...
    async def release(self, reason: ReleaseReason) -> None:
        """释放。默认 no-op。"""
```

沙箱的"先初始化"由 `requires()`+`prepare()`+启动拓扑排序表达,不是特例:Agent 启动时收集所有 `requires(executor_id)`,拓扑并行 `prepare`(沙箱先于依赖它的工具),`prepare` 结果按 `(agent_id, executor_id)` 缓存、会话内复用、lazy 阻塞未就绪者。Executor 生命周期建议 **Agent 级引用计数**:一个会话一份沙箱/连接池被多 capability 共享,首个 requires 者触发 prepare,引用归零时 `release`。

Contribution 生命周期:

| Lifetime | 失效键 | 释放点 | 例子 |
|---|---|---|---|
| CONFIG_STATIC | (agent_id, config_hash) | config 变更 / Agent 卸载 | DB schema、app列表、env信息 |
| SESSION | conv_id | SESSION_END | 加载的图片(多模态) |
| TURN | 本轮 hash | 轮次结束 | RAG inline chunks |

### 3.5 配置态存储(与现有 AgentResource 同构)

```python
@dataclass
class ResourceBinding:        # 配置态,落盘
    capability_id: str
    config: dict
    executor_ref: Optional[str] = None   # 指向哪个 executor(专用/共享沙箱)
    version: int = 1
```

与现 `AgentResource`(type/value/name/is_dynamic/context/version)同构:现有 `type`→`capability_id`、`value`→`config`,新增可选 `executor_ref`。存量数据 `version=1` 走默认映射零迁移读取。

### 3.6 协议层独立 + 快照供 v1/v2 共同消费

repo 当前 **v1(react_master_agent)与 v2(BAIZE)两套 Agent 架构并存**。资源协议不能绑死在任一套里,否则演进时被那一套的内部结构拖住。故协议层独立于 v1/v2,产出**可序列化、可哈希校验的不可变快照**,两套架构只消费快照、不感知资源内部。

```python
@dataclass(frozen=True)
class AgentInputsSnapshot:
    """协议对外锚点。v1 / v2 共同消费的唯一输入契约。"""
    system_prompt: str          # bundle.system 按序合并的字符串(v1/v2 现有拼装的等价位)
    user_parts: Tuple[ContentPart, ...]   # 本轮 user(含多模态、SESSION/TURN 注入)
    tools: Tuple[ToolSpec, ...]           # TOOLS 槽合并(资源工具 + agent builtin)
    template_vars: Mapping[str, Any]      # VAR 槽,可被 prompt 模板引用
    config_hash: str            # 命中缓存/失效键;迁移时校验一致性
    protocol_version: int = 1

class ResourceFacade:
    """协议层门面。独立于 v1/v2,两套架构的唯一接入点。"""
    async def assemble(self, agent_id, conv_id, turn_input) -> AgentInputsSnapshot:
        config_hash = self._hash_config(agent_id)
        if cached := self._snapshot_cache.get(agent_id, config_hash):
            snapshot = cached                       # CONFIG_STATIC 命中
        else:
            bundle = await self._build_bundle(agent_id, config_hash)  # declare+缓存
            snapshot = bundle.freeze()
            self._snapshot_cache.put(agent_id, config_hash, snapshot)
        # 叠加会话级 + 本轮运行态(SESSION/TURN),不改静态快照
        return self._apply_runtime(snapshot, conv_id, turn_input)
```

**两条铁律**(保证协议层独立性):

1. `AgentInputsSnapshot` 是**纯数据契约**,不含任何 v1/v2 运行时类型——可跨进程、可序列化、可作 A2A/外部协议对接的 payload,接收方校验 `config_hash` + `protocol_version` 即可信任。
2. v1/v2 各自侧只做"快照 → 自己的 LLM 调用形态"的薄适配,不反向依赖协议内部;协议演进时两套架构的适配层稳定。

repo 中"多层"有两个正交维度,不可混:

- **A. 资源 prompt 分层**(身份层+资源层+控制层,本 RFC 范畴):由 `assemble → InputBundle.SYSTEM` 渲染。
- **B. 历史消息分层**(hot/warm/cold,BAIZE `ContextEngine` 负责):对对话历史做预算压缩。

**核心边界**:资源 Contribution 只进快照的 `system_prompt`/`user_parts`/`tools`,**绝不进 ContextEngine 的历史 timeline**——ContextEngine 只压对话历史单元,资源声明每轮(命中缓存)渲染、不参与 hot/warm/cold、不被 cold 归档。两套机制正交、互不污染。

### 3.7 v1 / v2 接入点(精确到现有代码)

接入原则:每套架构只有一个"快照落地点",其余现状逻辑(minimize 改动)保留。

#### v1(react_master_agent)接入点

v1 当前的 system 与 tools 走两条旁路:

- system:`PromptAssembler.assemble_system_prompt()`(`prompt_assembler.py:127`)产出字符串 → `load_thinking_messages`(`react_master_agent.py:1409`)→ `llm_messages[0] = _new_system_message(system_prompt_text)`(`react_master_agent.py:1896`)。
- tools:`function_calling_params()`(`react_master_agent.py:609`)→ `function_calling_context["tools"]` → `llm_client.create(messages, ..., tools=...)`(`react_master_agent.py:1954`)。

| 接入点 | 现状 | 改为 |
|---|---|---|
| `load_thinking_messages` system 组装 | `assemble_system_prompt()` 返回 str | `snapshot = facade.assemble(...)`,取 `snapshot.system_prompt`(等价字符串);`memory_context` 取自 `snapshot.user_parts` |
| `function_calling_params()` | `available_system_tools` + `ToolPack.from_resource` 拼工具 | 读 `snapshot.tools`(已含 builtin + 资源工具);该方法退化为快照读取或删除 |
| 消费类用户消息 | memory 独立拼 | 读 `snapshot.user_parts`(多模态 ContentPart 直接落 user message) |

`ContextEngine`(若 v1 接入)、`llm_client.create()` 调用形态不变。

#### v2(BAIZE)接入点

v2 的 `make_default_thinking_fn`(`default_thinking.py:23`)收到的 `input_["system_prompt"]` 是字符串、`input_["prompt"]` 是 user 文本;tools 走 thinking 之外的 `unified_tool_adapter`/`tool_resolver` 解析链。ContextEngine 只压历史(`default_thinking.py:64`)。

| 接入点 | 现状 | 改为 |
|---|---|---|
| thinking_fn 的 `system_prompt` | 作字符串收(`default_thinking.py:46`) | 来源改为 `snapshot.system_prompt`(等价字符串) |
| `memory_context` user message | 独立拼(`default_thinking.py:48-58`) | 取 `snapshot.user_parts` 中 lifetime=SESSION/TURN 的部分 |
| tools 注入 | thinking 之外,`unified_tool_adapter`/`tool_resolver` 提供 | 该链路的工具来源改为 `snapshot.tools` |
| ContextEngine.build_messages | 压对话历史(`default_thinking.py:64`) | **零改**;输入仍是历史 messages,不含资源 Contribution |

**两套架构共享的关键不变量**(落地验证用):

- 同一 `(agent_id, config_hash)` 下,v1 拿到的 `snapshot.system_prompt` 与 v2 拿到的**字节一致**(AC-11 的基础)。
- 快照的静态部分两套架构都不修改、各自只做 read-only 消费。
- 运行态(SESSION/TURN)由 facade 在快照之上叠加,两套架构都通过 facade 拿,不各自维护。

协议层(facade)独立于 v1/v2 两套并存架构,产出可序列化 `AgentInputsSnapshot`,让 v1(react_master_agent)与 v2(BAIZE)共同消费,使协议成为两套架构共享的稳定输入契约。

### 3.8 CacheScope 与 prompt 缓存设计(参考 Claude Code)

现有 `Lifetime`(CONFIG_STATIC/SESSION/TURN)描述"何时变化"。但 prompt cache 还需第二个正交维度:**谁能共享缓存**。Claude Code 把 system 切成 5 块并标 `cacheScope`,正是围绕这个维度的一阶设计——我们缺的同等重要。

现有 provider(`claude_provider.py:48-49`)把多 system message **拼接为字符串**,丢弃分块,无法挂 `cache_control`。Anthropic cache 按前缀匹配:块顺序即 cache 断点,乱序即全 miss。故 RFC-005 的 system 必须保留**分块结构直供 provider**,而非渲染成 str。

#### 3.8.1 新增 CacheScope 维度(与 Lifetime 正交)

```python
class CacheScope(str, Enum):
    GLOBAL = "global"    # 跨用户共享(agent 模板:身份/控制层/通用行为块)
    USER   = "user"      # 跨会话但不跨用户(用户级资源声明/偏好)
    ENV    = "env"       # 本会话环境,不跨会话(gitStatus/env info)
    NONE   = "none"      # 不缓存(每轮或随时变:memory_context、MCP instructions)
```

`Contribution` 增字段 `cache_scope: CacheScope = CacheScope.NONE`。

**Lifetime(何时变)与 CacheScope(谁能共享)是完全独立的二维属性**:
- Lifetime 决定"何时重渲染/失效缓存键";
- CacheScope 决定"挂在哪个 cache 断点、命中范围多大"。
- 二者**不互推**:一个 `CONFIG_STATIC + GLOBAL` 的块(通用行为)与一个 `CONFIG_STATIC + USER` 的块(某用户的 DB schema)都是配置态即定,但前者可跨用户命中、后者只在该用户命中。

合法组合矩阵(非法组合在 facade 校验阶段拒绝):

| Lifetime \ CacheScope | GLOBAL | USER | ENV | NONE |
|---|---|---|---|---|
| CONFIG_STATIC | ✅ agent 模板/通用行为块(强缓存,跨用户命中) | ✅ 用户级资源声明/配置 | ✅ gitStatus/env 摘要 | ✅ 极少 |
| SESSION | ❌(会话级不存在跨用户共享) | ✅ 会话级用户态 | ✅ 会话级环境 | ✅ |
| TURN | ❌ | ❌ | ❌ | ✅ RAG inline、memory_context |

> 重要踩坑点:SESSION+GLOBAL 与 TURN+GLOBAL/USER/ENV 是**非法组合**——本就每轮/每会话变化的 Contribution 不可能跨用户/跨会话共享缓存,声明了就是逻辑矛盾。facade 在 assemble 时强制校验,非法组合报错而非静默降级。

#### 3.8.2 system 物理分块与确定性排序

`InputBundle.SYSTEM` 渲染**不再是拼 str**,而是产出有序 `SystemBlock` 列表:

```python
@dataclass(frozen=True)
class SystemBlock:
    text: str
    cache_scope: CacheScope
```

**排序键必须确定且跨轮稳定**(键变则前缀变,cache 全 miss):

```
主序:cache_scope 优先级 GLOBAL < USER < ENV < NONE
      (GLOBAL 在最前,使跨用户共享的前缀最大化)
次序:同一 cache_scope 内,按 Contribution.order 升序
      (同源资源的 order 由 declare 显式给出,默认 0)
```

> 重要踩坑点:**`Contribution.order` 仅在"同一 cache_scope 内"生效**。跨 scope 的顺序由 cache_scope 优先级硬定,order 不能跨 scope 重排——否则实现者可能用 order 把一个 USER 块排到 GLOBAL 前,破坏前缀稳定性。facade 排序分两步:先按 scope 分桶,桶内按 order,再按 scope 优先级拼桶。

#### 3.8.3 cache_control 挂载规则(钉死,避免超限报错)

Anthropic 约束:每个 block 至多 1 个 `cache_control`;单请求 **最多 4 个** cache_creation 断点(默认)。挂载规则:

```
对排序后的 SystemBlock 列表,从后往前找:
  - 每个 cache_scope 非 NONE 的"该 scope 最后一个块"末尾,挂 cache_control: {type: ephemeral}
  - NONE 块不挂
  - 若非 NONE 的 scope 数 > 可用断点余量(4 减去 history/tools 已占),按优先级丢弃
    低(scope 越靠后优先丢弃:先丢 NONE-邻接的 ENV,再丢 USER),保证 GLOBAL 断点最后丢
```

断点 budget 分配顺序(整请求 4 个上限共享):
```
1. system 的 GLOBAL 块末尾     ← 最值得保,跨用户命中
2. system 的 USER 块末尾
3. system 的 ENV 块末尾        ← 若 budget 不足,从这里开始丢
4. history 的最新稳态点(由 ContextEngine 标记)
```

> 重要踩坑点:不是"每个块都挂 cache_control"——那会轻松超 4 个并被 API 拒绝。只在"scope 边界(该 scope 最后一个块)"挂。ContextEngine 的 history 断点计入同一 budget,所以 system 最多实际占 3 个,留 1 个给 history。这条分配顺序要在 provider 层集中实现,**不要让 v1/v2 各自挂**——否则两套架构各挂各的会超限。

#### 3.8.4 动态内容移出 system prefix(判定准则)

借鉴 Claude Code:逐用户/逐会话/inflight 变化的上下文不进 system,进 user 消息。落到 RFC-005 的判定准则:

| 内容 | 放哪 | cache_scope | 判定依据 |
|---|---|---|---|
| 通用行为块/agent 模板/控制层 | system | GLOBAL | 跨用户字节一致 |
| 用户级资源声明(某用户绑定的 DB schema、app 列表) | system | USER | 跨会话同用户一致、跨用户不同 |
| 静态环境摘要(平台/shell/模型名,会话内稳) | system | ENV | 本会话不变,跨会话变 |
| memory_context(每轮检索) | user_parts | NONE(不进 system) | 每轮内容变,进 system 会击穿前缀 |
| gitStatus(每会话变) | user_parts | NONE | 跨会话变,且非"声明"而是"现场" |
| MCP instructions(连接变化即破) | user_parts | NONE | DANGEROUS_uncached,移出 system 最安全 |
| 多模态加载图片(SESSION) | user_parts | — | 本就属 user 多模态消息 |

> 重要踩坑点:判定准则的核心是"**它是否参与跨用户/跨会话的稳定前缀**"。memory/gitStatus/MCP 即便标 ENV 也只是"本会话稳",但它们内容大、变化频繁,放进 system 会让 GLOBAL/USER 断点前面的前缀每轮重算——净亏。所以准则一刀切:凡 Lifetime ∈ {SESSION, TURN} 的内容**一律进 user_parts,不进 system**,无论 cache_scope 标什么(3.8.1 矩阵已让这些组合非法或限于 NONE)。这样 system 永远只含 CONFIG_STATIC,前缀稳定。

这条准则强化 AC-7:不仅 SESSION 不动 system,**所有非 CONFIG_STATIC 内容都移出 system prefix**。

#### 3.8.5 跨会话 cache 失效语义

Anthropic `ephemeral` cache 默认 5 分钟 TTL,但本协议的失效语义要明确:

| 触发 | 失效范围 | 谁负责 |
|---|---|---|
| config_hash 变更(资源配置改) | 该 agent_id 的所有 USER scope 块 | facade 重算 snapshot,新 config_hash |
| 用户切换(conv_id 同 agent 不同 user) | USER scope 块(不同用户不共享) | USER 块内容随 user 变,前缀自然不同 |
| 会话环境变(平台/shell/git 摘要) | ENV scope 块 | ENV 块重渲染 |
| 5 分钟无活动 | Anthropic 侧 TTL 回收(无需本协议动作) | provider 层,透明 |

> 重要踩坑点:**本协议不手动管理 TTL**,只管"内容正确性"——即确保同 `(agent_id, config_hash, user, env_hash)` 下 SystemBlock 字节一致。是否真命中 Anthropic cache 是 provider 侧透明行为,本协议不承诺命中、只承诺"前缀稳定可被命中"。GLOBAL 块的跨用户命中要求其内容**绝对不含用户身份信息**(用户名/user_id 不能进 GLOBAL 块)——这是 GLOBAL 的硬约束,违反则跨用户命中失效但不报错(静默降级),需由测试(AC-15)守护。

#### 3.8.6 降级矩阵(穷举,保证向后等价)

provider 层据能力降级,每种路径的等价性判定:

| 场景 | system 形态 | cache_control | 等价判定 |
|---|---|---|---|
| Anthropic + 启用 cache(S12 目标) | 数组式 `[{type:text,text,cache_control?}, ...]` | 按 3.8.3 挂 | system 拼接文本 ≡ 旧 str;多出的只是 cache_control 标记 |
| Anthropic + 关 cache(配置/降级) | 数组式 或 合并 str | 不挂 | system 文本 ≡ 旧 str |
| 非 Anthropic 数组式 system(如部分 OpenAI 兼容) | 数组式 | 不挂/不支持 | 文本等价 |
| 非 Anthropic 纯 str system(现 claude/openai provider) | **合并 str** | 不挂 | 必须与现有 `claude_provider.py:48-49` 拼接输出**字节一致** |
| provider 不支持 system 多块 | 合并 str,块间 `\n\n` | 不挂 | 文本等价 |

> 重要踩坑点:降级时块间分隔符**统一 `\n\n`**,与现 `PromptAssembler` 的 `section_separator`(`prompt_assembler.py:77` 为 `"\n\n---\n\n"`)不一致——这是已知差异,S2 默认委托时要用现 separator 保字节等价,只有原生 declare 路径才用 `\n\n`。**两条路径的 separator 不能混**,否则存量回归会 diff。facade 提供 `merge_to_str(separator)` 显式参数,默认走存量 separator。
>
> 第二个踩坑点:降级到 str 时,**仍按 3.8.2 排序**再拼,不能按 declare 返回顺序拼——否则 cache 路径与降级路径输出不一致,测试会摇摆。排序是 facade 的统一行为,先于"拼 str 还是块数组"的形态选择。

#### 3.8.7 与 v1/v2 现状对接

- v1 `llm_client.create()` / v2 `llm_stream_fn`:system 参数从 str 改为消费 `snapshot.system`(SystemBlock 列表)。**provider 层集中负责"块→数组式 system + cache_control"或降级合并 str**,v1/v2 只透传 `snapshot.system`,不做格式转换。
- `ContextEngine` 历史仍零改。history 的 cache 断点由 provider 按 3.8.3 budget 顺序自行标注(在最新稳态消息挂),与 system 块的断点共享 4 上限但**由 provider 统一调度**。
- tools 的 `cache_control`(S12 同时引入):tools 列表稳态时在末尾挂一个 cache_control,计入 3.8.3 budget(优先级低于 system GLOBAL)。

### 3.9 用此模型重述各能力(自检一致)

| Capability | 配置(薄) | declare 声明面 | consume(可选) | 执行投影 | 释放 |
|---|---|---|---|---|---|
| DB | 连接信息 | SYSTEM(schema)+TOOLS(查表/execute_sql) | — | DB连接器 | 归还连接 |
| App | app code | SYSTEM(app列表)+TOOLS(sub_agent) | — | 子Agent运行时 | 释放子agent |
| Sandbox | 镜像/workdir | SYSTEM(env)+TOOLS(run_python/write_file/view) | — | 沙箱运行时(共享底座) | 销毁容器 |
| Knowledge | 库id | SYSTEM(库列表)+TOOLS(search) | USER_PART(TURN) | 检索后端 | 关检索会话 |
| ImageLoader | 加载配置 | TOOLS(加载工具) | USER_PART(图片,SESSION) | 沙箱/直接 | 会话结束随 SESSION |
| builtin | — | TOOLS(spawn/check_tasks/…) | — | Agent本地 | no-op |

## 4. 演进路径

| 步骤 | 改动 | 验证 | 风险/兼容 |
|---|---|---|---|
| **S1** | 新增 `InputBundle`/`Contribution`/`Slot`/`Lifetime` 数据模型 + 单测 | 合并/排序/freeze 单测 | 纯增量,零破坏 |
| **S2** | `ResourceProtocol.declare` 默认实现委托现 `inject_xxx`·`ToolPack.from_resource` | 存量输出字节不变(回归) | 等价重构 |
| **S3** | `inject_all` 改为遍历资源调 declare,删类名硬匹配 | 回归 + 新资源可声明 UserPrompt/VAR | 等价重构 |
| **S4** | `Executor` 抽象 + `prepare/requires` + 启动拓扑;现 DB连接器/沙箱包成 executor | 行为不变,prepare 可缓存 | 包一层 |
| **S5** | `release()` + Agent 级引用计数 + `end_session` 释放链 | 会话结束 DB连接/沙箱实例确实释放 | 行为新增,需测 |
| **S6** | 构建态缓存(declare+prepare 按 config_hash)+ SESSION/TURN 运行态缓存 | 多轮 DB扫表/沙箱重起次数↓ | 可旁路可关 |
| **S7** | DB 表列表按规模:小库全量注入、大库改 `data_requirement` 按需拉取(不注入 system) | token↓、首座延迟↓ | **行为变:大库不再每轮注入**,需确认 |
| **S8** | `ConsumerProtocol` 统一 RAG/多模态回注,替换现特例路径 | 多模态加载/RAG 走同 hook | 替换特例 |
| **S9** | `protocol_version` + 兼容 adapter;`ResourceFacade` + `AgentInputsSnapshot` 不可变快照作对外锚点(独立于 v1/v2) | 快照可序列化/可校验/跨进程一致 | 协议层发布 |
| **S10** | v1 接入:system 组装改读 `snapshot.system`(SystemBlock 列表);`function_calling_params` 改读 `snapshot.tools`;user memory 改读 `snapshot.user_parts` | v1 行为字节等价(AC-2、AC-13) | v1 改造,可回滚到旧拼装 |
| **S11** | v2 接入:thinking_fn 的 `system_prompt` 来源改 `snapshot.system`(块列表);`memory_context` 改 `snapshot.user_parts`;tools 注入链来源改 `snapshot.tools`;ContextEngine 零改 | v2 行为字节等价(AC-8、AC-13) | v2 改造,可回滚 |
| **S12** | provider 层 cache_control:Anthropic provider 消费 `snapshot.system` SystemBlock,按 3.8.3 在 scope 边界插 `cache_control`(不超 4 上限);非 Anthropic 降级合并 str(按 3.8.6 等价);memory/gitStatus/MCP 按 3.8.4 移出 system 进 user_parts | 跨用户 GLOBAL cache 命中↑、多轮 system input tokens↓、降级路径字节等价 | 行为新增(缓存),降级兼容可关 |
| **S13** | 存量资源直接迁移原生 `declare`:DB/App/Skill/Tool 等存量 `Resource` 子类直接改造为实现 `ResourceProtocol.declare`(declare 内部仍可复用现 `_format_*` 渲染,只换出口不重写渲染)。兼容**仅在配置层**(老 `AgentResource` type/value 可读),代码层直接改。桥接(`LegacyResourceAdapter`)仅作迁移过渡——每迁一个资源、桥接对应分支删除,最终桥接废弃 | 类名硬匹配逐个消除;无长期双路径债 | 渐进迁移,可分 PR |

**S7 是唯一需拍板的语义变化**:大库表列表不再每轮注入 system prompt,改按需拉取。保守可只加缓存不做降级。**S10/S11 互相独立**:v1、v2 可分别上线,各自可回滚到原拼装;两者都接好后即可下线旧 `PromptAssembler`/`function_calling_params`/`ToolPack.from_resource` 路径。

## 5. 不做什么

- **不引入"资源层 vs 环境层"的对象二分**——一个 Capability 双投影,沙箱/DB 同模型;不为沙箱开"特殊资源"代码分支。
- **不让资源声明面有 I/O**(declare 纯函数)——需数据用 `data_requirement` 由执行投影回填;禁止在 declare 里直接查 DB/起沙箱。
- **不把 model kwargs 纳入输入协议**(temperature/tool_choice/stream 等)——这些是 Agent/LLM 层职责,资源碰即越界,破坏分层纪律。
- **不把 Executor 当资源特例**——沙箱的"先初始化/共享底座/慢启动/释放"全用 `requires`/`prepare`/`executor_ref`/`release` 表达,不开 `if 资源==sandbox` 分支。
- **不让资源 Contribution 进 ContextEngine 历史分层**——资源声明是每轮(命中缓存)渲染的 system 部分,绝不进 hot/warm/cold 被 cold 归档;两套机制正交。
- **不改配置态持久化格式**——`ResourceBinding` 与现 `AgentResource` 同构存量零迁移;新增 UserPrompt/multimodal 不加持久化字段,仅运行态。
- **不做配置热更新**——profile/资源配置改动需 Agent 重建,避免运行中一致性漂移。
- **不重写 v1/v2 任一架构**——协议 facade 独立产出快照,v1/v2 各自微调接入,ContextEngine 零改。
- **不保留桥接为长期兜底**——`LegacyResourceAdapter` 仅是迁移过渡;存量资源直接改代码迁原生 `declare`,兼容只在配置层(老 `AgentResource` 可读),不为"零代码改动"长期维护双渲染路径。

## 6. 验收标准

| 编号 | 项 | 判定 |
|---|---|---|
| AC-1 | `InputBundle` 四槽位合并、`order` 排序、`freeze` 产出不可变快照 | 单测(含多资源多槽合并 fixture) |
| AC-2 | 存量配置下 `bundle.system.freeze_str()` ≡ 现有 `assemble_system_prompt()` 输出 | 回归 diff 为空 |
| AC-3 | `inject_all` 无类名字符串匹配;新资源子类仅靠 `declare` 即可声明任意槽 | 单测 + 无 `in class_name` 残留检查 |
| AC-4 | Executor `prepare` 按 `requires` 拓扑并行;沙箱先于依赖它的 tool 就绪 | 单测(构造依赖图 + 验证顺序) |
| AC-5 | 会话结束触发 `release(SESSION_END)`;DB连接/沙箱实例确实释放(引用计数归零) | 集成测试 |
| AC-6 | 多轮对话下 CONFIG_STATIC 资源构建+渲染只发生一次(命中 config_hash 缓存) | 多轮性能测试,build 次数断言 |
| AC-7 | SESSION 级 Contribution(多模态)不破坏 system prefix-cache;system 跨轮稳定 | cache 命中率测试 |
| AC-8 | ContextEngine 的 `build_out.messages` 中无任何资源 Contribution 内容 | 断言 history 无 DB schema 等 |
| AC-9 | `consume` 在工具回调链统一介入;RAG 回注与多模态加载走同一 hook、不进特例路径 | 单测两类 consumer |
| AC-10 | 大库表列表不进 system prompt(S7 生效后),按需走工具拉取 | token 数断言 + tool 调用断言 |
| AC-11 | v1 与 v2 均消费同一 `AgentInputsSnapshot`;快照可序列化/反序列化且 hash 一致 | 跨架构一致性测试 |
| AC-12 | 新 `protocol_version` 的资源与旧版共存,旧版走兼容 adapter 行为不变 | 版本混存测试 |
| AC-13 | v1 接入点(system 组装、`function_calling_params` tools、user memory)与 v2 接入点(system_prompt 来源、user_parts、tools 注入链)全部改为读快照;ContextEngine 零改(provider 对 system 的 cache_control 处理见 AC-14) | 静态断言 + 接入点改造 checklist 核对 |
| AC-14 | `Contribution` 带 `cache_scope`;`snapshot.system` 为 `Tuple[SystemBlock, ...]`;非法组合(SESSION+GLOBAL / TURN+非NONE)被 facade 拒绝 | 单测(矩阵合法/非法用例) |
| AC-15 | 排序确定且跨轮稳定:先 cache_scope 优先级分桶(GLOBAL<USER<ENV<NONE),桶内按 Contribution.order;降级拼 str 与块数组路径**同序**,只分隔符不同 | 单测(排序 + 两路径序一致断言) |
| AC-16 | Anthropic provider cache_control 挂载:仅在非 NONE scope 的"该 scope 最后一块"末尾挂;单请求总挂载数 ≤4(含 history 断点),超限按 3.8.3 优先级丢弃 | 单测(挂载点 + budget 超限用例) |
| AC-17 | 降级等价:非 Anthropic / 关 cache 路径,`merge_to_str` 输出 ≡ 现 `claude_provider.py:48-49` 拼接(存量 separator `\n\n---\n\n`);原生 declare 路径用 `\n\n`;两路径 separator 不混 | 回归 diff + 双 separator 单测 |
| AC-18 | GLOBAL scope 块不含用户身份信息(user_name/user_id 等);不同用户下 GLOBAL 块字节一致(可跨用户命中);SESSION/TURN 内容一律在 user_parts、不在 system | 跨用户 GLOBAL 字节断言 + system 内容扫描禁含用户字段 |

## 7. 开放问题

1. **Executor lifecycle owner**:建议 Agent 级引用计数(一会话一沙箱/连接池被多 capability 共享)。值得确认的是否需要 Agent-pool 级(跨多会话复用沙箱底座),还是会话级隔离更安全?建议先 Agent 级,需隔离再升。
2. **prepare 未就绪策略**:lazy 阻塞(调到时才等就绪,超时报错) vs 预声明禁用(沙箱没好前这批 tool 不进 TOOLS 槽)。建议 lazy 阻塞——工具声明可预先有,真执行才需沙箱就绪;但需确认流式首 token 延迟可接受。
3. **大库降级阈值**(S7):沿用现有 `<100 全量 / 100-500 紧凑 / >500 统计` 策略,还是统一改为"全部按需、小库也走 data_requirement"?建议保留分级,大库才降级,小库继续注入保交互连贯。
4. **multi-packing 路径缓存**:Pack 嵌套下同一知识库在不同 Agent 实例的注入产物不同,`ResourcePath` 是否需要作为缓存键?建议是——按叶子资源路径索引,避免重复渲染。但需确认路径计算开销可接受。
5. **存量资源迁移**:S2-S3 后存量资源**直接改造**迁原生 `declare`(非保留桥接,见「不做什么」)。需确认迁移顺序——建议 DB(类名硬匹配最重、S7 大库降级也依赖它)优先,再 App/Skill,最后 Tool(ToolPack 本即是 tool 聚合,declare 只需暴露 tools 槽)。