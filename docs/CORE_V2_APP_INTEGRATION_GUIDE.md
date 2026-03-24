# Core_v2 Agent 应用集成指南

本指南详细说明如何在现有服务中创建和使用 Core_v2 Agent。

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     现有服务应用层                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               FastAPI 服务启动                        │   │
│  │  - /api/v2/chat (Core_v2 API)                       │   │
│  │  - /api/app/chat (原有 API)                          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                     Core_v2 集成层                          │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐  │
│  │ V2AgentRuntime │ │V2AgentDispatcher│ │ V2AgentAPI     │  │
│  └────────────────┘ └────────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                     Core_v2 核心层                          │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐  │
│  │ V2PDCAAgent    │ │ ToolSystem     │ │ Permission     │  │
│  │ V2SimpleAgent  │ │ BashTool       │ │ PermissionRuleset│  │
│  └────────────────┘ └────────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                     原有系统集成                             │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐  │
│  │ GptsMemory     │ │ AgentResource  │ │ VisConverter   │  │
│  │ Canvas         │ │ AppBuilding    │ │ Sandbox        │  │
│  └────────────────┘ └────────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 二、服务启动集成

### 2.1 在现有服务中注册 Core_v2 组件

创建文件: `packages/derisk-serve/src/derisk_serve/agent/core_v2_adapter.py`

```python
"""
Core_v2 适配器 - 在现有服务中集成 Core_v2
"""
import logging
from typing import Optional

from derisk.component import SystemApp, ComponentType, BaseComponent
from derisk._private.config import Config
from derisk.agent.core_v2.integration import (
    V2AgentRuntime,
    RuntimeConfig,
    V2AgentDispatcher,
    V2ApplicationBuilder,
    create_v2_agent,
)
from derisk.agent.core_v2.integration.api import V2AgentAPI, APIConfig
from derisk.agent.tools_v2 import BashTool

logger = logging.getLogger(__name__)
CFG = Config()


class CoreV2Component(BaseComponent):
    """Core_v2 组件 - 注册到 SystemApp"""
    
    name = "core_v2_runtime"
    
    def __init__(self, system_app: SystemApp):
        super().__init__(system_app)
        self.runtime: Optional[V2AgentRuntime] = None
        self.dispatcher: Optional[V2AgentDispatcher] = None
        self.builder: Optional[V2ApplicationBuilder] = None
        self.api: Optional[V2AgentAPI] = None
    
    def init_app(self, system_app: SystemApp):
        """初始化 Core_v2 组件"""
        self.system_app = system_app
    
    async def start(self):
        """启动 Core_v2 运行时"""
        # 1. 获取 GptsMemory (如果存在)
        gpts_memory = None
        try:
            from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
            gpts_memory = self.system_app.get_component(
                ComponentType.GPTS_MEMORY, GptsMemory
            )
        except Exception:
            logger.warning("GptsMemory not found, Core_v2 will run without memory sync")
        
        # 2. 创建 Runtime
        self.runtime = V2AgentRuntime(
            config=RuntimeConfig(
                max_concurrent_sessions=100,
                session_timeout=3600,
                enable_streaming=True,
            ),
            gpts_memory=gpts_memory,
        )
        
        # 3. 注册默认 Agent
        self._register_default_agents()
        
        # 4. 创建 Dispatcher
        self.dispatcher = V2AgentDispatcher(
            runtime=self.runtime,
            max_workers=10,
        )
        
        # 5. 启动
        await self.dispatcher.start()
        
        # 6. 创建 API
        self.api = V2AgentAPI(
            dispatcher=self.dispatcher,
            config=APIConfig(port=8080),
        )
        
        logger.info("Core_v2 component started successfully")
    
    async def stop(self):
        """停止 Core_v2 运行时"""
        if self.dispatcher:
            await self.dispatcher.stop()
        logger.info("Core_v2 component stopped")
    
    def _register_default_agents(self):
        """注册默认 Agent"""
        # 注册简单对话 Agent
        self.runtime.register_agent_factory(
            "simple_chat",
            lambda context, **kw: create_v2_agent(
                name="simple_chat",
                mode="primary",
            )
        )
        
        # 注册带工具的 Agent
        self.runtime.register_agent_factory(
            "tool_agent",
            lambda context, **kw: create_v2_agent(
                name="tool_agent",
                mode="planner",
                tools={"bash": BashTool()},
                permission={"bash": "allow"},
            )
        )


# 全局组件实例
_core_v2_component: Optional[CoreV2Component] = None


def get_core_v2() -> CoreV2Component:
    """获取 Core_v2 组件"""
    global _core_v2_component
    if _core_v2_component is None:
        _core_v2_component = CoreV2Component(CFG.SYSTEM_APP)
    return _core_v2_component
```

### 2.2 在服务启动时初始化

修改服务启动文件 (通常是 `main.py` 或 `server.py`):

```python
from derisk_serve.agent.core_v2_adapter import get_core_v2

# 在 FastAPI app 启动时
@app.on_event("startup")
async def startup_event():
    # 启动 Core_v2
    core_v2 = get_core_v2()
    await core_v2.start()

@app.on_event("shutdown")
async def shutdown_event():
    # 停止 Core_v2
    core_v2 = get_core_v2()
    await core_v2.stop()
```

## 三、注册 Core_v2 API 路由

### 3.1 创建 API 路由

创建文件: `packages/derisk-serve/src/derisk_serve/agent/core_v2_api.py`

```python
"""
Core_v2 API 路由
"""
import asyncio
from typing import Optional
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from derisk_serve.agent.core_v2_adapter import get_core_v2

router = APIRouter(prefix="/api/v2", tags=["Core_v2 Agent"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    agent_name: str = "simple_chat"


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: str = "simple_chat"


@router.post("/chat")
async def chat(request: ChatRequest):
    """发送消息 (流式响应)"""
    core_v2 = get_core_v2()
    
    async def generate():
        async for chunk in core_v2.dispatcher.dispatch_and_wait(
            message=request.message,
            session_id=request.session_id,
            agent_name=request.agent_name,
        ):
            import json
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/session")
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    core_v2 = get_core_v2()
    session = await core_v2.runtime.create_session(
        user_id=request.user_id,
        agent_name=request.agent_name,
    )
    return {
        "session_id": session.session_id,
        "conv_id": session.conv_id,
        "agent_name": session.agent_name,
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    core_v2 = get_core_v2()
    session = await core_v2.runtime.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session.session_id,
        "conv_id": session.conv_id,
        "state": session.state.value,
        "message_count": session.message_count,
    }


@router.delete("/session/{session_id}")
async def close_session(session_id: str):
    """关闭会话"""
    core_v2 = get_core_v2()
    await core_v2.runtime.close_session(session_id)
    return {"status": "closed"}


@router.get("/status")
async def get_status():
    """获取 Core_v2 状态"""
    core_v2 = get_core_v2()
    return core_v2.dispatcher.get_status()
```

### 3.2 注册路由到主应用

```python
from derisk_serve.agent.core_v2_api import router as core_v2_router

# 在 main.py 中
app.include_router(core_v2_router, prefix="/api/v2")
```

## 四、从 App 构建 Core_v2 Agent

### 4.1 创建 App 到 Core_v2 的转换器

创建文件: `packages/derisk-serve/src/derisk_serve/agent/app_to_v2_converter.py`

```python
"""
App 构建 -> Core_v2 Agent 转换器
"""
import logging
from typing import Dict, Any, Optional, List

from derisk.agent.core_v2 import AgentInfo, AgentMode, PermissionRuleset, PermissionAction
from derisk.agent.core_v2.integration import create_v2_agent
from derisk.agent.tools_v2 import BashTool, tool_registry
from derisk.agent.resource import BaseTool, ResourceType

logger = logging.getLogger(__name__)


async def convert_app_to_v2_agent(
    gpts_app,
    resources: List[Any] = None,
) -> Dict[str, Any]:
    """
    将 GptsApp 转换为 Core_v2 Agent
    
    Args:
        gpts_app: 原有的 GptsApp 对象
        resources: App 关联的资源列表
    
    Returns:
        Dict: 包含 agent, agent_info, tools 等信息
    """
    # 1. 解析 Agent 模式
    team_mode = getattr(gpts_app, "team_mode", "single_agent")
    mode_map = {
        "single_agent": AgentMode.PRIMARY,
        "auto_plan": AgentMode.PLANNER,
    }
    agent_mode = mode_map.get(team_mode, AgentMode.PRIMARY)
    
    # 2. 构建权限规则
    permission = _build_permission_from_app(gpts_app)
    
    # 3. 转换资源为工具
    tools = await _convert_resources_to_tools(resources or [])
    
    # 4. 创建 AgentInfo
    agent_info = AgentInfo(
        name=gpts_app.app_code or "v2_agent",
        mode=agent_mode,
        description=gpts_app.app_name,
        max_steps=20,
        permission=permission,
    )
    
    # 5. 创建 Agent
    agent = create_v2_agent(
        name=agent_info.name,
        mode=agent_info.mode.value,
        tools=tools,
        permission=_permission_to_dict(permission),
    )
    
    return {
        "agent": agent,
        "agent_info": agent_info,
        "tools": tools,
    }


def _build_permission_from_app(gpts_app) -> PermissionRuleset:
    """从 App 配置构建权限规则"""
    rules = {}
    
    # 根据 App 类型设置权限
    app_code = getattr(gpts_app, "app_code", "")
    
    if "read_only" in app_code.lower():
        # 只读模式
        rules["read"] = PermissionAction.ALLOW
        rules["glob"] = PermissionAction.ALLOW
        rules["grep"] = PermissionAction.ALLOW
        rules["write"] = PermissionAction.DENY
        rules["edit"] = PermissionAction.DENY
        rules["bash"] = PermissionAction.ASK
    else:
        # 默认权限
        rules["*"] = PermissionAction.ALLOW
        rules["*.env"] = PermissionAction.ASK
    
    return PermissionRuleset.from_dict({
        k: v.value for k, v in rules.items()
    })


async def _convert_resources_to_tools(resources: List[Any]) -> Dict[str, Any]:
    """将 App 资源转换为 Core_v2 工具"""
    tools = {}
    
    # 默认添加 Bash 工具
    tools["bash"] = BashTool()
    
    for resource in resources:
        resource_type = _get_resource_type(resource)
        
        if resource_type == ResourceType.Tool:
            tool_name = getattr(resource, "name", None)
            if tool_name:
                # 检查是否已在 tool_registry 中
                if tool_name in tool_registry._tools:
                    tools[tool_name] = tool_registry.get(tool_name)
                else:
                    # 包装为 V2 工具
                    tools[tool_name] = _wrap_v1_tool(resource)
        
        elif resource_type == ResourceType.Knowledge:
            # 知识库资源 -> 知识搜索工具
            tools["knowledge_search"] = _create_knowledge_tool(resource)
    
    return tools


def _get_resource_type(resource) -> Optional[ResourceType]:
    """获取资源类型"""
    if hasattr(resource, "type"):
        rtype = resource.type
        if isinstance(rtype, ResourceType):
            return rtype
        elif isinstance(rtype, str):
            try:
                return ResourceType(rtype)
            except:
                pass
    return None


def _wrap_v1_tool(v1_tool) -> Any:
    """将 V1 工具包装为 V2 工具"""
    from derisk.agent.tools_v2.tool_base import ToolBase, ToolInfo
    
    class V1ToolWrapper(ToolBase):
        def __init__(self):
            super().__init__(ToolInfo(
                name=getattr(v1_tool, "name", "unknown"),
                description=getattr(v1_tool, "description", ""),
            ))
            self._v1_tool = v1_tool
        
        async def execute(self, **kwargs):
            if hasattr(self._v1_tool, "execute"):
                result = self._v1_tool.execute(**kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            raise NotImplementedError(f"Tool {self.info.name} cannot execute")
    
    return V1ToolWrapper()


def _permission_to_dict(permission: PermissionRuleset) -> Dict[str, str]:
    """将 PermissionRuleset 转换为字典"""
    return {k: v.value for k, v in permission.rules.items()}


import asyncio
```

### 4.2 在现有 App 管理中集成

修改 `app_agent_manage.py`:

```python
from derisk_serve.agent.app_to_v2_converter import convert_app_to_v2_agent

class AppManager:
    # ... 现有代码 ...
    
    async def create_v2_agent_by_app(
        self,
        gpts_app: GptsApp,
        conv_uid: str = None,
    ):
        """
        从 App 创建 Core_v2 Agent
        
        这是一个新的方法，可以与原有的 create_agent_by_app_code 并存
        """
        # 1. 获取资源
        from derisk.agent.resource import get_resource_manager
        resources = []
        for detail in gpts_app.details:
            if detail.resources:
                res = await get_resource_manager().build_resource(detail.resources)
                resources.extend(res if isinstance(res, list) else [res])
        
        # 2. 转换为 Core_v2 Agent
        result = await convert_app_to_v2_agent(gpts_app, resources)
        
        # 3. 创建 Runtime Session
        from derisk_serve.agent.core_v2_adapter import get_core_v2
        core_v2 = get_core_v2()
        
        session = await core_v2.runtime.create_session(
            conv_id=conv_uid,
            agent_name=gpts_app.app_code,
        )
        
        # 4. 注册 Agent 到 Runtime
        core_v2.runtime.register_agent(gpts_app.app_code, result["agent"])
        
        return {
            "session_id": session.session_id,
            "conv_id": session.conv_id,
            "agent": result["agent"],
            "agent_info": result["agent_info"],
        }
```

## 五、完整使用示例

### 5.1 启动服务

```bash
# 启动现有服务
cd packages/derisk-serve
python -m derisk_serve

# 服务启动后，Core_v2 API 可用:
# POST /api/v2/session   - 创建会话
# POST /api/v2/chat      - 发送消息
# GET  /api/v2/status    - 查看状态
```

### 5.2 调用 API

```python
import httpx
import asyncio

async def test_core_v2():
    base_url = "http://localhost:8080/api/v2"
    
    async with httpx.AsyncClient() as client:
        # 1. 创建会话
        resp = await client.post(f"{base_url}/session", json={
            "agent_name": "simple_chat"
        })
        session = resp.json()
        session_id = session["session_id"]
        print(f"Session created: {session_id}")
        
        # 2. 发送消息 (流式)
        async with client.stream(
            "POST",
            f"{base_url}/chat",
            json={
                "message": "你好，请介绍一下你自己",
                "session_id": session_id
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    print(line[6:])
        
        # 3. 关闭会话
        await client.delete(f"{base_url}/session/{session_id}")

asyncio.run(test_core_v2())
```

### 5.3 从 Python 代码直接使用

```python
import asyncio
from derisk_serve.agent.core_v2_adapter import get_core_v2
from derisk.agent.tools_v2 import BashTool

async def main():
    # 获取 Core_v2 运行时
    core_v2 = get_core_v2()
    
    # 创建会话
    session = await core_v2.runtime.create_session(
        agent_name="tool_agent"
    )
    
    # 执行对话
    async for chunk in core_v2.dispatcher.dispatch_and_wait(
        message="执行 ls -la 命令",
        session_id=session.session_id,
    ):
        print(f"[{chunk.type}] {chunk.content}")
    
    # 关闭会话
    await core_v2.runtime.close_session(session.session_id)

asyncio.run(main())
```

### 5.4 与原有 GptsApp 集成

```python
import asyncio
from derisk_serve.agent.agents.app_agent_manage import get_app_manager
from derisk_serve.building.app.service.service import Service as AppService
from derisk._private.config import Config

CFG = Config()

async def use_v2_with_app():
    # 1. 获取 App 信息
    app_service = AppService.get_instance(CFG.SYSTEM_APP)
    gpts_app = await app_service.sync_app_detail("your_app_code")
    
    # 2. 创建 V2 Agent (使用新方法)
    app_manager = get_app_manager()
    result = await app_manager.create_v2_agent_by_app(gpts_app)
    
    # 3. 运行对话
    from derisk_serve.agent.core_v2_adapter import get_core_v2
    core_v2 = get_core_v2()
    
    async for chunk in core_v2.dispatcher.dispatch_and_wait(
        message="帮我分析这个项目",
        session_id=result["session_id"],
    ):
        print(chunk)

asyncio.run(use_v2_with_app())
```

## 六、配置文件

### 6.1 Core_v2 配置 (添加到现有配置)

```yaml
# derisk_config.yaml
core_v2:
  runtime:
    max_concurrent_sessions: 100
    session_timeout: 3600
    enable_streaming: true
    enable_progress: true
    default_max_steps: 20
    cleanup_interval: 300
  
  dispatcher:
    max_workers: 10
  
  api:
    host: "0.0.0.0"
    port: 8080
    cors_origins: ["*"]
```

## 七、调试和日志

```python
import logging

# 启用 Core_v2 调试日志
logging.getLogger("derisk.agent.core_v2").setLevel(logging.DEBUG)
logging.getLogger("derisk.agent.visualization").setLevel(logging.DEBUG)
```

## 八、文件位置总结

```
packages/derisk-core/src/derisk/agent/
├── core_v2/                    # Core_v2 核心
│   ├── agent_info.py
│   ├── agent_base.py
│   ├── permission.py
│   └── integration/            # 集成层
│       ├── adapter.py
│       ├── runtime.py
│       ├── dispatcher.py
│       ├── builder.py
│       ├── agent_impl.py
│       └── api.py

packages/derisk-serve/src/derisk_serve/agent/
├── core_v2_adapter.py          # 服务组件适配器
├── core_v2_api.py              # API 路由
├── app_to_v2_converter.py      # App -> V2 转换器
└── agents/
    └── app_agent_manage.py     # 修改: 添加 create_v2_agent_by_app
```