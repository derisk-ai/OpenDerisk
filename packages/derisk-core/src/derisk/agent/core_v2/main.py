"""
DeRisk Agent V2 - 完整启动入口

提供开箱即用的Agent产品启动方案

启动方式:
    # 方式1: 直接运行
    python -m derisk.agent.core_v2.main
    
    # 方式2: 指定端口
    python -m derisk.agent.core_v2.main --port 8080 --host 0.0.0.0
    
    # 方式3: 环境变量配置
    export OPENAI_API_KEY="sk-xxx"
    export AGENT_PORT=8080
    python -m derisk.agent.core_v2.main

API端点:
    POST /api/v2/session     - 创建会话
    POST /api/v2/chat        - 发送消息
    GET  /api/v2/status      - 获取状态
    WebSocket /ws/{session_id} - 流式消息
"""

import asyncio
import logging
import os
import sys
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentApp:
    """
    Agent应用主类
    
    完整的Agent产品启动方案，包含：
    - 后端服务启动
    - API服务启动 (FastAPI + Uvicorn)
    - 存储初始化
    - 配置加载
    - ProductionAgent集成
    
    示例:
        app = AgentApp()
        await app.start()
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        env_prefix: str = "AGENT_"
    ):
        self.config = self._load_config(config_path, env_prefix)
        self._api_server = None
        self._uvicorn_server = None
        self._running = False
    
    def _load_config(self, config_path: Optional[str], env_prefix: str) -> Dict[str, Any]:
        """加载配置"""
        config = {
            "host": os.getenv(f"{env_prefix}HOST", "0.0.0.0"),
            "port": int(os.getenv(f"{env_prefix}PORT", "8080")),
            "log_level": os.getenv(f"{env_prefix}LOG_LEVEL", "INFO"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4"),
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "max_steps": int(os.getenv(f"{env_prefix}MAX_STEPS", "100")),
            "storage_backend": os.getenv(f"{env_prefix}STORAGE_BACKEND", "memory"),
            "storage_path": os.getenv(f"{env_prefix}STORAGE_PATH", ".agent_state"),
        }
        
        if config_path and Path(config_path).exists():
            try:
                import tomli
                with open(config_path, "rb") as f:
                    file_config = tomli.load(f)
                    config.update(file_config.get("agent", {}))
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}")
        
        return config
    
    def _create_production_agent(self):
        """创建生产可用的Agent"""
        from .production_agent import ProductionAgent, AgentBuilder
        from .tools_v2 import register_builtin_tools, ToolRegistry
        from .visualization.progress import ProgressBroadcaster
        
        api_key = self.config.get("api_key")
        model = self.config.get("model", "gpt-4")
        max_steps = self.config.get("max_steps", 100)
        
        if not api_key:
            logger.warning("[AgentApp] 未设置 OPENAI_API_KEY，Agent将使用模拟模式")
            return self._create_mock_agent()
        
        try:
            tool_registry = ToolRegistry()
            register_builtin_tools(tool_registry)
            
            progress = ProgressBroadcaster()
            
            agent = (
                AgentBuilder()
                .with_name("production-agent")
                .with_model(model)
                .with_api_key(api_key)
                .with_max_steps(max_steps)
                .build()
            )
            
            agent.tools = tool_registry
            agent.progress = progress
            
            logger.info(f"[AgentApp] ProductionAgent已创建: model={model}, tools={tool_registry.list_names()}")
            return agent
            
        except Exception as e:
            logger.error(f"[AgentApp] 创建ProductionAgent失败: {e}")
            return self._create_mock_agent()
    
    def _create_mock_agent(self):
        """创建模拟Agent（无LLM时使用）"""
        from .agent_base import AgentBase, AgentInfo
        
        class MockAgent(AgentBase):
            def __init__(self, info: AgentInfo):
                super().__init__(info)
                self._step = 0
            
            async def think(self, message: str, **kwargs):
                self._step += 1
                yield f"[Step {self._step}] 思考: {message[:50]}..."
            
            async def decide(self, message: str, **kwargs):
                return {
                    "type": "response",
                    "content": f"[Mock] 我收到了您的消息: {message}\n\n请设置 OPENAI_API_KEY 环境变量以启用真正的LLM功能。"
                }
            
            async def act(self, tool_name: str, tool_args: dict, **kwargs):
                return f"Mock执行: {tool_name}"
        
        return MockAgent(AgentInfo(name="mock-agent", max_steps=10))

    async def start(self):
        """启动应用"""
        self._running = True

        # Use derisk's unified logging system instead of logging.basicConfig
        # This prevents duplicate log output
        log_level = self.config.get("log_level", "INFO")
        from derisk.util.logger import setup_logging, LoggingParameters
        setup_logging("derisk", LoggingParameters(level=log_level))
        
        logger.info("=" * 60)
        logger.info("[AgentApp] DeRisk Agent V2 正在启动...")
        logger.info("=" * 60)
        
        agent = self._create_production_agent()
        
        from .api_routes import init_executor, create_app
        
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "gpt-4")
        
        if api_key:
            init_executor(api_key, model)
        
        app = create_app()
        
        import uvicorn
        from uvicorn import Config, Server
        
        host = self.config.get("host", "0.0.0.0")
        port = self.config.get("port", 8080)
        
        config = Config(
            app=app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=False
        )
        
        self._uvicorn_server = Server(config)
        
        logger.info(f"[AgentApp] 服务启动于: http://{host}:{port}")
        logger.info(f"[AgentApp] API文档: http://{host}:{port}/docs")
        logger.info(f"[AgentApp] 模型: {model}")
        logger.info(f"[AgentApp] API Key: {'***' + api_key[-4:] if api_key and len(api_key) > 4 else '未设置'}")
        logger.info("=" * 60)
        
        await self._uvicorn_server.serve()
    
    async def stop(self):
        """停止应用"""
        self._running = False
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        logger.info("[AgentApp] 已停止")


def run_server():
    """直接运行服务器（用于CLI入口）"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeRisk Agent V2")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--port", "-p", type=int, default=8080, help="服务端口")
    parser.add_argument("--host", default="0.0.0.0", help="服务地址")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    
    args = parser.parse_args()
    
    if args.port:
        os.environ["AGENT_PORT"] = str(args.port)
    if args.host:
        os.environ["AGENT_HOST"] = args.host
    if args.log_level:
        os.environ["AGENT_LOG_LEVEL"] = args.log_level
    
    app = AgentApp(config_path=args.config)
    
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("\n[AgentApp] 收到中断信号，正在关闭...")


async def main():
    """异步主入口"""
    app = AgentApp()
    try:
        await app.start()
    except KeyboardInterrupt:
        await app.stop()


if __name__ == "__main__":
    run_server()