# Core_v2 架构资源绑定修复说明

## 问题总结

Core_v2 架构的 Agent 在应用编辑时存在以下问题：

1. **Agent 类型选项**：`type` 字段默认值为 `'agent'`，可选 `'app'` 或 `'agent'`（在 `models_details.py:32`）
2. **资源绑定缺失**：`app_to_v2_converter.py` 只处理了 `ResourceType.Tool`，未处理 MCP、Knowledge、Skill 等资源
3. **资源解析不完整**：`ResourceResolver` 只返回简单 dict，没有实际解析资源实例
4. **对话体系打通不完整**：Core_v2 Agent 无法使用绑定的 Knowledge 和 Skill 资源

## 修复内容

### 1. 完整的资源转换器 (`app_to_v2_converter.py`)

新增功能：
- **MCP 资源转换**：支持 MCPToolPack、MCPSSEToolPack，从 MCP 服务器加载工具
- **Knowledge 资源转换**：解析知识空间配置，支持 KnowledgePack
- **Skill 资源转换**：解析技能配置，获取沙箱路径
- **混合资源处理**：支持多种资源类型同时绑定

核心函数：
```python
async def convert_app_to_v2_agent(gpts_app, resources: List[Any] = None) -> Dict[str, Any]:
    """
    将 GptsApp 转换为 Core_v2 Agent
    
    Returns:
        {
            "agent": Agent实例,
            "agent_info": AgentInfo配置,
            "tools": 工具字典（包含MCP工具）,
            "knowledge": 知识资源列表,
            "skills": 技能资源列表,
        }
    """
```

### 2. 增强的资源解析器 (`agent_binding.py` - ResourceResolver)

新增功能：
- **MCP 资源解析**：支持 MCP 服务器配置解析
- **Knowledge 资源解析**：查询知识空间详情，获取向量类型等元信息
- **Skill 资源解析**：查询技能详情，获取沙箱路径
- **资源缓存**：避免重复解析相同资源

支持的资源类型：
- `knowledge` / `knowledge_pack`
- `tool` / `local_tool`
- `mcp` / `tool(mcp)` / `tool(mcp(sse))`
- `skill` / `skill(derisk)`
- `database`
- `workflow`

### 3. Agent 资源混入类 (`agent_impl.py` - ResourceMixin)

为 Core_v2 Agent 提供资源处理能力：
- `get_knowledge_context()`: 生成知识资源上下文提示
- `get_skills_context()`: 生成技能资源上下文提示
- `build_resource_prompt(base_prompt)`: 构建包含资源信息的完整提示

示例：
```python
class V2PDCAAgent(AgentBase, ResourceMixin):
    def __init__(self, info, tools, resources, ...):
        self.resources = resources  # {"knowledge": [...], "skills": [...]}
    
    async def _create_plan_with_llm(self, message, **kwargs):
        # 自动包含资源信息
        resource_context = self.build_resource_prompt()
        prompt = f"{base_prompt}\n\n可用资源:\n{resource_context}"
```

### 4. 完整的测试覆盖 (`test_core_v2_resource_binding.py`)

测试内容：
- 知识资源转换测试
- MCP 资源转换测试
- 技能资源转换测试
- 多种资源混合转换测试
- 完整应用转换流程测试
- ResourceResolver 测试
- Agent 资源集成测试
- 完整绑定流程测试

## 使用示例

### 1. 创建带资源的 Core_v2 Agent

```python
from derisk_serve.agent.app_to_v2_converter import convert_app_to_v2_agent
from derisk.agent.resource import AgentResource

# 定义资源
resources = [
    AgentResource(
        type="knowledge",
        name="product_kb",
        value='{"space_id": "kb_001", "space_name": "产品知识库"}'
    ),
    AgentResource(
        type="tool(mcp(sse))",
        name="external_tools",
        value='{"mcp_servers": "http://localhost:8000/sse"}'
    ),
    AgentResource(
        type="skill(derisk)",
        name="code_assistant",
        value='{"skill_code": "s001", "skill_name": "代码助手"}'
    ),
]

# 转换为 Core_v2 Agent
result = await convert_app_to_v2_agent(gpts_app, resources)

agent = result["agent"]
# agent.resources = {
#     "knowledge": [{"space_id": "kb_001", ...}],
#     "skills": [{"skill_code": "s001", ...}]
# }
# agent.tools = {"bash": ..., "mcp_tool1": ..., "mcp_tool2": ...}
```

### 2. 使用绑定资源

```python
# Agent 在规划时会自动包含资源信息
async for chunk in agent.run("帮我查询产品信息"):
    print(chunk)

# 在任务规划时，资源信息会自动注入到 prompt 中：
# <knowledge-resources>
# <knowledge-1>
# <space-id>kb_001</space-id>
# <space-name>产品知识库</space-name>
# </knowledge-1>
# </knowledge-resources>
# 
# <agent-skills>
# <skill-1>
# <name>代码助手</name>
# <code>s001</code>
# <path>/sandbox/skills/s001</path>
# </skill-1>
# </agent-skills>
```

## 架构关系

```
应用构建体系
    ↓
App → AppDetail → AgentResource (knowledge/tool/mcp/skill)
    ↓
convert_app_to_v2_agent()  # 新增的转换器
    ↓
Core_v2 Agent
    ├── tools: Dict[str, ToolBase]  # 包含 MCP 工具
    ├── resources: Dict[str, List]  # knowledge, skills
    └── ResourceMixin  # 资源处理能力
    ↓
ResourceResolver  # 资源解析（查询详情、沙箱路径等）
    ↓
实际资源实例
    ├── KnowledgeService (知识空间)
    ├── SkillService (技能沙箱)
    └── MCPToolPack (MCP 工具)
```

## 兼容性

- **向后兼容**：不影响现有的 v1 Agent
- **资源类型扩展**：通过 `_get_resource_type()` 支持自定义资源类型
- **错误处理**：资源转换失败时会记录日志并继续处理其他资源

## 注意事项

1. MCP 资源需要确保 MCP 服务器可访问
2. Knowledge 资源需要确保知识空间已创建
3. Skill 资源需要确保技能已部署到沙箱环境
4. 资源转换是异步的，需要在异步环境中调用

## 后续优化

1. 添加资源预热机制，在 Agent 启动时预加载资源
2. 支持资源动态更新，无需重启 Agent
3. 添加资源使用统计，监控资源调用情况
4. 支持资源权限控制，限制某些资源的访问