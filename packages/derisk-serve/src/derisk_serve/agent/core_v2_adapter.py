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
    create_v2_agent,
)
from derisk.agent.tools_v2 import BashTool

logger = logging.getLogger(__name__)
CFG = Config()


class CoreV2Component(BaseComponent):
    """Core_v2 组件"""
    
    name = "core_v2_runtime"
    
    def __init__(self, system_app: SystemApp):
        super().__init__(system_app)
        self.runtime: Optional[V2AgentRuntime] = None
        self.dispatcher: Optional[V2AgentDispatcher] = None
        self._started = False
    
    def init_app(self, system_app: SystemApp):
        self.system_app = system_app
    
    async def start(self):
        """启动 Core_v2"""
        if self._started:
            return
        
        gpts_memory = None
        try:
            from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
            gpts_memory = self.system_app.get_component(
                ComponentType.GPTS_MEMORY, GptsMemory
            )
        except Exception:
            logger.warning("GptsMemory not found")
        
        self.runtime = V2AgentRuntime(
            config=RuntimeConfig(
                max_concurrent_sessions=100,
                session_timeout=3600,
                enable_streaming=True,
            ),
            gpts_memory=gpts_memory,
        )
        
        self._register_default_agents()
        
        self.dispatcher = V2AgentDispatcher(
            runtime=self.runtime,
            max_workers=10,
        )
        
        await self.dispatcher.start()
        self._started = True
        logger.info("Core_v2 component started")
    
    async def stop(self):
        """停止 Core_v2"""
        if self.dispatcher:
            await self.dispatcher.stop()
        self._started = False
        logger.info("Core_v2 component stopped")
    
    def _register_default_agents(self):
        """注册默认 Agent"""
        self.runtime.register_agent_factory(
            "simple_chat",
            lambda context, **kw: create_v2_agent(name="simple_chat", mode="primary")
        )
        
        self.runtime.register_agent_factory(
            "tool_agent",
            lambda context, **kw: create_v2_agent(
                name="tool_agent",
                mode="planner",
                tools={"bash": BashTool()},
                permission={"bash": "allow"},
            )
        )
        
        self.runtime.register_agent_factory(
            "pdca_agent",
            lambda context, **kw: create_v2_agent(
                name="pdca_agent",
                mode="planner",
                tools={"bash": BashTool()},
                permission={"*": "allow"},
            )
        )


_core_v2: Optional[CoreV2Component] = None


def get_core_v2() -> CoreV2Component:
    """获取 Core_v2 组件"""
    global _core_v2
    if _core_v2 is None:
        _core_v2 = CoreV2Component(CFG.SYSTEM_APP)
    return _core_v2
