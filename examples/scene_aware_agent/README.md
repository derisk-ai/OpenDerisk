# 场景化 Agent 架构使用指南

## 概述

场景化 Agent 架构允许您通过 Markdown 文件定义 Agent 角色和工作场景，实现灵活的场景切换和工具注入。

## 架构组件

```
┌─────────────────────────────────────────────────────────────────┐
│                场景化 Agent 架构                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 定义层（MD 文件）                                             │
│     ├─ agent-role.md          # Agent 基础角色定义                │
│     └─ scenes/                                                 │
│         ├─ scene-fault-diagnosis.md    # 故障诊断场景             │
│         └─ scene-performance-analysis.md # 性能分析场景            │
│                                                                  │
│  2. 数据层（数据模型）                                            │
│     ├─ AgentRoleDefinition     # Agent 角色定义数据模型           │
│     └─ SceneDefinition         # 场景定义数据模型                 │
│                                                                  │
│  3. 解析层                                                       │
│     └─ SceneDefinitionParser   # MD 文件解析器                   │
│                                                                  │
│  4. 检测层                                                       │
│     └─ SceneSwitchDetector     # 场景切换检测器                   │
│         ├─ 关键词匹配                                           │
│         ├─ 语义相似度                                           │
│         └─ LLM 分类                                             │
│                                                                  │
│  5. 管理层                                                       │
│     └─ SceneRuntimeManager     # 场景运行时管理器                 │
│         ├─ 场景激活/切换                                        │
│         ├─ 工具注入/清理                                        │
│         └─ 钩子执行                                             │
│                                                                  │
│  6. Agent 层                                                     │
│     └─ SceneAwareAgent         # 场景感知 Agent                  │
│         └─ ReActReasoningAgent # ReAct 推理 Agent（基类）        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 定义 Agent 角色（agent-role.md）

创建一个 Agent 基础角色定义文件：

```markdown
# Agent: SRE-Diagnostic-Agent

## 基本信息

- 名称: SRE诊断助手
- 版本: 1.0.0
- 描述: 专业的系统可靠性工程诊断 Agent

## 核心能力

- 系统故障诊断与根因分析
- 性能问题识别与优化建议
- 容量评估与规划

## 工作原则

1. 数据驱动决策
2. 系统性思维
3. 循证分析

## 可用场景

- fault_diagnosis
- performance_analysis

## 全局工具

- read
- grep
- bash
- webfetch

## 全局约束

- 不执行危险操作
- 保留完整审计日志
```

### 2. 定义场景（scene-fault-diagnosis.md）

创建场景定义文件：

```markdown
# Scene: fault_diagnosis

## 场景信息

- 名称: 故障诊断
- 场景ID: fault_diagnosis
- 触发关键词: 故障, 异常, 报错, 失败, crash
- 优先级: 10

## 场景角色设定

你是一个专业的 SRE 故障诊断专家...

## 工作流程

### 阶段1: 信息收集
1. 确认故障现象
2. 收集日志和指标
3. 确定时间线

### 阶段2: 假设生成
1. 生成初步假设
2. 排序假设
3. 识别关键点

## 场景工具

- read
- grep
- bash
- trace_analyzer

## 输出格式

1. 故障摘要
2. 根因分析
3. 证据链
4. 修复建议
```

### 3. 使用 Agent

```python
from derisk.agent.core_v2.scene_definition_parser import SceneDefinitionParser
from derisk.agent.core_v2.scene_runtime_manager import SceneRuntimeManager
from derisk.agent.core_v2.scene_switch_detector import SceneSwitchDetector

# 1. 解析 Agent 角色定义
parser = SceneDefinitionParser()
agent_role = await parser.parse_agent_role("path/to/agent-role.md")

# 2. 解析场景定义
scene_definitions = {}
for scene_md in ["scene-fault-diagnosis.md", "scene-performance-analysis.md"]:
    scene_def = await parser.parse_scene_definition(f"path/to/scenes/{scene_md}")
    scene_definitions[scene_def.scene_id] = scene_def

# 3. 初始化场景管理器
scene_manager = SceneRuntimeManager(
    agent_role=agent_role,
    scene_definitions=scene_definitions
)

# 4. 初始化场景检测器
detector = SceneSwitchDetector(
    available_scenes=list(scene_definitions.values()),
    llm_client=llm_client  # 可选，用于高级检测
)

# 5. 激活初始场景
await scene_manager.activate_scene(
    scene_id="fault_diagnosis",
    session_id="session_001",
    agent=agent
)

# 6. 检测场景切换
from derisk.agent.core_v2.scene_switch_detector import SessionContext

context = SessionContext(
    session_id="session_001",
    conv_id="conv_001",
    current_scene_id="fault_diagnosis",
    message_count=3
)

decision = await detector.detect_scene(
    user_input="系统性能很慢，CPU占用很高",
    session_context=context
)

if decision.should_switch:
    # 执行场景切换
    await scene_manager.switch_scene(
        from_scene=current_scene,
        to_scene=decision.target_scene,
        session_id="session_001",
        agent=agent,
        reason=decision.reasoning
    )
```

## 核心特性

### 1. MD 格式定义

- **易读易写**: 使用 Markdown 格式，便于编辑和维护
- **结构化**: 自动映射到结构化数据模型
- **可扩展**: 支持自定义字段和扩展

### 2. 场景检测

支持三种检测策略：

| 策略 | 速度 | 准确性 | 适用场景 |
|------|------|--------|---------|
| 关键词匹配 | 快 | 中 | 通用场景 |
| 语义相似度 | 中 | 中高 | 复杂场景 |
| LLM 分类 | 慢 | 高 | 高级场景 |

### 3. 场景切换

- **自动检测**: 根据用户输入自动判断场景切换
- **平滑切换**: 执行钩子、清理工具、注入新工具
- **历史追踪**: 记录场景切换历史

### 4. 工具管理

- **全局工具**: 所有场景共享的基础工具
- **场景工具**: 场景特定的专用工具
- **动态注入**: 按需注入和清理工具

### 5. 钩子机制

支持的生命周期钩子：

- `on_enter`: 进入场景时执行
- `on_exit`: 退出场景时执行
- `before_think`: 思考前执行
- `after_act`: 行动后执行
- `before_tool`: 工具调用前执行
- `after_tool`: 工具调用后执行

## 前端集成方案

### 1. 场景管理 API

```python
# 创建场景定义 CRUD API
from fastapi import APIRouter

router = APIRouter()

@router.get("/scenes")
async def list_scenes():
    """列出所有可用场景"""
    pass

@router.get("/scenes/{scene_id}")
async def get_scene(scene_id: str):
    """获取场景定义"""
    pass

@router.post("/scenes")
async def create_scene(scene_md: str):
    """创建新场景"""
    pass

@router.put("/scenes/{scene_id}")
async def update_scene(scene_id: str, scene_md: str):
    """更新场景定义"""
    pass

@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    """删除场景"""
    pass
```

### 2. 前端组件

#### 场景管理页面

```typescript
// 场景列表组件
function SceneManager() {
  const [scenes, setScenes] = useState([]);
  
  useEffect(() => {
    fetchScenes().then(setScenes);
  }, []);
  
  return (
    <div>
      <SceneList scenes={scenes} />
      <SceneEditor onSave={handleSave} />
    </div>
  );
}
```

#### MD 编辑器组件

```typescript
// MD 编辑器
function SceneEditor({ sceneId, onSave }) {
  const [content, setContent] = useState("");
  
  return (
    <div>
      <MarkdownEditor
        value={content}
        onChange={setContent}
        preview={true}
      />
      <Button onClick={() => onSave(content)}>
        保存场景
      </Button>
    </div>
  );
}
```

### 3. 场景引用管理

在 Agent 的 Prompt 中维护场景引用：

```python
# 构建 System Prompt 时包含场景信息
system_prompt = scene_manager.build_system_prompt(scene_id="fault_diagnosis")

# 输出示例：
"""
# 角色定位

你是一个专业的 SRE 故障诊断专家...

# 核心能力

- 系统故障诊断与根因分析
- 性能问题识别与优化建议

# 工作流程

## 阶段1: 信息收集
1. 确认故障现象
2. 收集日志和指标
...
"""
```

## 完整样例

查看完整样例代码和 MD 文件：

- **Agent 定义**: `examples/scene_aware_agent/sre_diagnostic/agent-role.md`
- **故障诊断场景**: `examples/scene_aware_agent/sre_diagnostic/scenes/scene-fault-diagnosis.md`
- **性能分析场景**: `examples/scene_aware_agent/sre_diagnostic/scenes/scene-performance-analysis.md`

## 下一步计划

### 待完善功能

- [ ] 实现完整的 SceneAwareAgent 类
- [ ] 完善钩子执行机制
- [ ] 实现工具动态注入和清理
- [ ] 添加前端管理界面
- [ ] 集成 LLM 分类检测
- [ ] 添加单元测试和集成测试

### API 集成

- [ ] 创建场景定义 CRUD API
- [ ] 实现场景切换 API
- [ ] 添加场景统计分析 API

### 前端功能

- [ ] 场景管理页面
- [ ] MD 编辑器组件
- [ ] 场景预览和测试功能
- [ ] 场景切换可视化

## 技术栈

- **后端**: Python, Pydantic, FastAPI
- **前端**: React/TypeScript (推荐)
- **MD 渲染**: react-markdown + MDX
- **编辑器**: Monaco Editor / CodeMirror

## 参考资料

- [Core V2 架构文档](../../../../docs/architecture/CORE_V2_ARCHITECTURE.md)
- [SceneStrategy 文档](../../../../packages/derisk-core/src/derisk/agent/core_v2/scene_strategy.py)
- [SceneRegistry 文档](../../../../packages/derisk-core/src/derisk/agent/core_v2/scene_registry.py)

## 贡献指南

欢迎贡献力量来完善场景化 Agent 架构：

1. Fork 项目
2. 创建功能分支
3. 提交 PR

特别欢迎以下方面的贡献：
- 新的场景定义模板
- 前端管理界面
- 检测算法优化
- 使用文档改进

## 许可证

MIT License

---

**创建时间**: 2026-03-04
**作者**: Derisk Team
**状态**: 核心框架已完成，待完善细节