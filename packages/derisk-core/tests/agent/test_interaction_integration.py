"""
交互系统集成测试

测试 ReActMasterAgent 和 ProductionAgent 的交互能力
"""

import asyncio
import pytest
from typing import Dict, Any

from derisk.agent.interaction import (
    InteractionGateway,
    InteractionRequest,
    InteractionResponse,
    InteractionType,
    InteractionStatus,
    get_interaction_gateway,
    set_interaction_gateway,
)
from derisk.agent.interaction import (
    RecoveryCoordinator,
    get_recovery_coordinator,
)


class MockWebSocketManager:
    """Mock WebSocket 管理器"""
    
    def __init__(self):
        self._connections: Dict[str, bool] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
    
    def add_connection(self, session_id: str):
        self._connections[session_id] = True
    
    async def has_connection(self, session_id: str) -> bool:
        return self._connections.get(session_id, False)
    
    async def send_to_session(self, session_id: str, message: Dict[str, Any]) -> bool:
        if session_id in self._connections:
            return True
        return False
    
    def set_response(self, request_id: str, response: InteractionResponse):
        if request_id in self._pending_responses:
            future = self._pending_responses.pop(request_id)
            if not future.done():
                future.set_result(response)


class TestInteractionIntegration:
    """交互集成测试"""
    
    @pytest.fixture
    def setup_gateway(self):
        """设置测试网关"""
        ws_manager = MockWebSocketManager()
        gateway = InteractionGateway(ws_manager=ws_manager)
        set_interaction_gateway(gateway)
        return gateway, ws_manager
    
    @pytest.mark.asyncio
    async def test_interaction_request_flow(self, setup_gateway):
        """测试交互请求流程"""
        gateway, ws_manager = setup_gateway
        ws_manager.add_connection("test_session")
        
        request = InteractionRequest(
            interaction_type=InteractionType.ASK,
            title="测试提问",
            message="这是一个测试问题",
            session_id="test_session",
        )
        
        response = InteractionResponse(
            request_id=request.request_id,
            input_value="测试回答",
            status=InteractionStatus.RESPONSED,
        )
        
        gateway._pending_requests[request.request_id] = asyncio.Future()
        
        await gateway.deliver_response(response)
        
        assert request.request_id not in gateway._pending_requests
    
    @pytest.mark.asyncio
    async def test_recovery_coordinator(self):
        """测试恢复协调器"""
        recovery = get_recovery_coordinator()
        
        todo_id = await recovery.create_todo(
            session_id="test_session",
            content="测试任务",
            priority=1,
        )
        
        assert todo_id is not None
        
        todos = recovery.get_todos("test_session")
        assert len(todos) == 1
        assert todos[0].content == "测试任务"
        
        await recovery.update_todo(
            session_id="test_session",
            todo_id=todo_id,
            status="completed",
            result="完成",
        )
        
        completed, total = recovery.get_progress("test_session")
        assert completed == 1
        assert total == 1
    
    @pytest.mark.asyncio
    async def test_production_agent_interaction(self):
        """测试 ProductionAgent 交互能力"""
        from derisk.agent.core_v2.production_agent import ProductionAgent
        from derisk.agent.core_v2.llm_adapter import LLMConfig, LLMFactory
        
        gateway = get_interaction_gateway()
        gateway.ws_manager.add_connection("agent_test_session")
        
        info = type('AgentInfo', (), {'name': 'test-agent', 'max_steps': 5})()
        llm_adapter = type('LLMAdapter', (), {
            'generate': asyncio.coroutine(lambda self, **kwargs: type('Response', (), {'content': 'ok', 'tool_calls': None})())
        })()
        
        agent = ProductionAgent(info=info, llm_adapter=llm_adapter)
        agent.init_interaction(session_id="agent_test_session")
        
        assert agent._enhanced_interaction is not None
        assert agent._session_id == "agent_test_session"


class TestReActMasterInteraction:
    """ReActMasterAgent 交互测试"""
    
    @pytest.mark.asyncio
    async def test_interaction_extension(self):
        """测试交互扩展"""
        from derisk.agent.expand.react_master_agent.interaction_extension import (
            ReActMasterInteractionExtension,
        )
        
        mock_agent = type('MockAgent', (), {
            'agent_context': type('Context', (), {'conv_session_id': 'test'})(),
            'name': 'mock-agent',
        })()
        
        extension = ReActMasterInteractionExtension(mock_agent)
        
        assert extension.session_id == 'test'
        
        todo_id = await extension.create_todo("测试任务")
        assert todo_id is not None
        
        todos = extension.get_todos()
        assert len(todos) >= 1


def run_tests():
    """运行测试"""
    import sys
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()