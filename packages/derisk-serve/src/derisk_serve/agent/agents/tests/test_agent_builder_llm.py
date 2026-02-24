import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Mock derisk_app.config BEFORE any derisk imports to avoid ImportError
# We need to mock any module that might trigger the ImportError of SandboxConfigParameters
mock_app_config = MagicMock()
sys.modules["derisk_app.config"] = mock_app_config
mock_app_config.SandboxConfigParameters = MagicMock()

# Mock derisk_ext.agent.agents.awel.awel_runner_agent to avoid ImportError
mock_awel = MagicMock()
sys.modules["derisk_ext.agent.agents.awel.awel_runner_agent"] = mock_awel
mock_awel.AwelRunnerAgent = MagicMock()

import pytest
import logging

try:
    from derisk.agent.core.llm_config import AgentLLMConfig
except ImportError:
    pass

from derisk.agent import AgentContext
from derisk_serve.agent.agents.controller_new import AgentBuilder
from derisk_serve.agent.agents.controller_new import TeamMode
from derisk.agent.util.llm.llm import LLMStrategyType

# Mock the dependencies
@pytest.fixture
def mock_system_app():
    app = MagicMock()
    app.config = MagicMock()
    app.config.get = MagicMock(return_value=None)  # Default: config not found
    app.get_component = MagicMock()
    return app

@pytest.fixture
def agent_builder(mock_system_app):
    with patch("derisk_serve.agent.agents.controller_new.WorkerManagerFactory"):
        builder = AgentBuilder(mock_system_app)
        
        # FIX: Ensure llm_provider is an AsyncMock that also mocks the necessary methods
        # and passes the Pydantic type check if possible.
        # Since LLMConfig validates that llm_client is an instance of LLMClient,
        # we have a few options. The easiest is often to make sure the mocked object
        # has the right class spec or we can try to bypass the validation if we were mocking LLMConfig.
        # But we are testing integration with LLMConfig, so we must provide a valid LLMClient mock.
        
        # Option: Mock DefaultLLMClient itself
        from derisk.model.cluster.client import DefaultLLMClient
        mock_client = MagicMock(spec=DefaultLLMClient)
        # AsyncMock for async methods if needed, but spec helps with isinstance checks in some testing frameworks
        # However, Pydantic's isinstance check on a Mock object often fails unless configured carefully.
        
        # Better Option for Pydantic: Create a dummy subclass or use a real object with mocked internals.
        # Or simpler: just let it be an AsyncMock but patch isinstance? No, that's messy.
        
        # Let's try to mock the class that LLMConfig expects.
        builder.llm_provider = mock_client
        return builder

@pytest.fixture
def mock_agent_context():
    return AgentContext(
        conv_id="test_conv",
        conv_session_id="test_session", # Required by dataclass
        gpts_app_code="test_app"
    )

@pytest.fixture
def mock_agent_memory():
    return MagicMock()

@pytest.fixture
def mock_resource_manager():
    return MagicMock()

@pytest.fixture
def mock_gpts_app():
    app = MagicMock()
    app.team_mode = TeamMode.AUTO_PLAN.value
    app.team_context = MagicMock()
    app.team_context.teamleader = "some_leader_agent"
    app.llm_config = MagicMock()
    app.llm_config.llm_strategy = LLMStrategyType.Default
    app.llm_config.agent_llm_config = None # Default no app-specific override
    app.all_resources = []
    app.details = []
    return app

@pytest.mark.asyncio
async def test_build_auto_plan_agent_system_config(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that _build_auto_plan_agent correctly picks up LLM config from system config
    when not provided in the App definition.
    """
    
    # 1. Setup System Config (Mocking global config injection)
    system_llm_config = {
        "model": "gpt-4-turbo",
        "provider": "openai",
        "api_key": "sk-test-key",
        "temperature": 0.7
    }
    
    # Mock system_app.config.get to return our config when "agent.llm" is requested
    def config_get_side_effect(key):
        if key == "agent.llm":
            return system_llm_config
        return None
        
    agent_builder.system_app.config.get.side_effect = config_get_side_effect

    # Mock get_agent_manager to return a Mock Agent class
    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        
        # Setup method chaining mocks for bind().bind().build()
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance)
        
        # Important: The 'bind' call that passes LLMConfig is what we want to inspect.
        # However, bind is called multiple times. We need to capture the args.
        
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        # 2. Execute
        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        # 3. Verify
        # Find the call to bind(llm_config)
        # We iterate through all calls to bind
        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                # This is likely the LLMConfig object
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None, "AgentLLMConfig was not bound to the agent"
        assert found_config.model == "gpt-4-turbo"
        assert found_config.provider == "openai"
        assert found_config.api_key == "sk-test-key"
        assert found_config.temperature == 0.7

@pytest.mark.asyncio
async def test_build_auto_plan_agent_system_config_nested(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that _build_auto_plan_agent correctly picks up LLM config from system config
    when it is nested: agent: { llm: { ... } }
    """
    
    system_llm_config = {
        "model": "claude-3-opus",
        "provider": "claude"
    }
    
    # Mock behavior: "agent.llm" -> None, "agent" -> {"llm": ...}
    def config_get_side_effect(key):
        if key == "agent.llm":
            return None
        if key == "agent":
            return {"llm": system_llm_config}
        return None
        
    agent_builder.system_app.config.get.side_effect = config_get_side_effect

    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance) 
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None
        assert found_config.model == "claude-3-opus"
        assert found_config.provider == "claude"

@pytest.mark.asyncio
async def test_build_auto_plan_agent_strategy_override(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that strategy value (e.g. user selected model in UI) overrides the system config model.
    """
    
    # System default
    system_llm_config = {
        "model": "gpt-3.5-turbo",
        "provider": "openai",
        "api_key": "sk-system"
    }
    
    agent_builder.system_app.config.get.side_effect = lambda k: system_llm_config if k == "agent.llm" else None
    
    # User override via Strategy
    mock_gpts_app.llm_config.llm_strategy_value = "gpt-4o"
    
    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance) 
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None
        # Should retain provider/key from system config
        assert found_config.provider == "openai"
        assert found_config.api_key == "sk-system"
        # But model should be overridden
        assert found_config.model == "gpt-4o"

@pytest.mark.asyncio
async def test_build_auto_plan_agent_system_config_model_list(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that system config can define a list of models sharing common config.
    Structure:
    agent.llm = {
        "provider": "openai",
        "api_key": "sk-common",
        "models": [
            {"model": "specific-model-v1", "temperature": 0.1},
            {"model": "specific-model-v2", "temperature": 0.9}
        ]
    }
    """
    
    system_llm_config = {
        "provider": "openai",
        "api_key": "sk-common",
        "temperature": 0.5, # Default temp
        "models": [
            {
                "model": "specific-model-v1",
                "temperature": 0.1
            },
            {
                "model": "specific-model-v2",
                # inherits temperature 0.5
            }
        ]
    }
    
    agent_builder.system_app.config.get.side_effect = lambda k: system_llm_config if k == "agent.llm" else None
    
    # CASE 1: Request specific-model-v1
    mock_gpts_app.llm_config.llm_strategy_value = "specific-model-v1"
    
    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance) 
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None
        assert found_config.model == "specific-model-v1"
        assert found_config.provider == "openai" # Inherited
        assert found_config.api_key == "sk-common" # Inherited
        assert found_config.temperature == 0.1 # Overridden

        # CASE 2: Request specific-model-v2 (inherits default temp)
        mock_gpts_app.llm_config.llm_strategy_value = "specific-model-v2"
        # Reset mocks
        mock_agent_instance.bind.reset_mock()
        
        await agent_builder._build_auto_plan_agent(
                mock_agent_context, 
                mock_agent_memory, 
                mock_gpts_app, 
                mock_resource_manager
            )
        
        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
                
        assert found_config is not None
        assert found_config.model == "specific-model-v2"
        assert found_config.temperature == 0.5 # Inherited default

@pytest.mark.asyncio
async def test_build_auto_plan_agent_system_config_multi_provider(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that system config can define a list of models with DIFFERENT providers.
    This validates the multi-provider scenario in a single list.
    """
    
    system_llm_config = {
        # Global defaults
        "temperature": 0.5,
        "models": [
            {
                "model": "gpt-4",
                "provider": "openai",
                "api_key": "sk-openai-key"
            },
            {
                "model": "claude-3-opus",
                "provider": "anthropic",
                "api_key": "sk-anthropic-key"
            }
        ]
    }
    
    agent_builder.system_app.config.get.side_effect = lambda k: system_llm_config if k == "agent.llm" else None
    
    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance) 
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        # CASE 1: Request OpenAI model
        mock_gpts_app.llm_config.llm_strategy_value = "gpt-4"

        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None
        assert found_config.model == "gpt-4"
        assert found_config.provider == "openai"
        assert found_config.api_key == "sk-openai-key"

        # CASE 2: Request Anthropic model
        mock_gpts_app.llm_config.llm_strategy_value = "claude-3-opus"
        # Reset mock
        mock_agent_instance.bind.reset_mock()
        
        await agent_builder._build_auto_plan_agent(
                mock_agent_context, 
                mock_agent_memory, 
                mock_gpts_app, 
                mock_resource_manager
            )
        
        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
                
        assert found_config is not None
        assert found_config.model == "claude-3-opus"
        assert found_config.provider == "anthropic"
@pytest.mark.asyncio
async def test_build_auto_plan_agent_system_config_nested_provider_list(
    agent_builder, 
    mock_agent_context, 
    mock_agent_memory, 
    mock_gpts_app, 
    mock_resource_manager
):
    """
    Test that system config can define a list of providers, each with its own models list.
    Structure:
    agent.llm = {
        "provider": [
            {
                "provider": "openai",
                "api_base": "https://api.openai.com/v1",
                "api_key": "sk-openai",
                "model": [
                    {"model": "gpt-4", "temperature": 0.5},
                    {"model": "gpt-3.5", "temperature": 0.7}
                ]
            },
            {
                "provider": "claude",
                "api_base": "https://api.anthropic.com",
                "api_key": "sk-claude",
                "model": [
                    {"model": "claude-3-opus", "temperature": 0.1}
                ]
            }
        ]
    }
    """
    
    system_llm_config = {
        "provider": [
            {
                "provider": "openai",
                "api_base": "https://api.openai.com/v1",
                "api_key": "sk-openai",
                "model": [
                    {"model": "gpt-4", "temperature": 0.5},
                    {"model": "gpt-3.5", "temperature": 0.7}
                ]
            },
            {
                "provider": "claude",
                "api_base": "https://api.anthropic.com",
                "api_key": "sk-claude",
                "model": [
                    {"model": "claude-3-opus", "temperature": 0.1}
                ]
            }
        ]
    }
    
    agent_builder.system_app.config.get.side_effect = lambda k: system_llm_config if k == "agent.llm" else None
    
    with patch("derisk_serve.agent.agents.controller_new.get_agent_manager") as mock_get_manager:
        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_cls.return_value = mock_agent_instance
        mock_agent_instance.bind.return_value = mock_agent_instance
        mock_agent_instance.build = AsyncMock(return_value=mock_agent_instance) 
        mock_get_manager.return_value.get_by_name.return_value = mock_agent_cls

        # CASE 1: Request OpenAI gpt-4
        mock_gpts_app.llm_config.llm_strategy_value = "gpt-4"

        await agent_builder._build_auto_plan_agent(
            mock_agent_context, 
            mock_agent_memory, 
            mock_gpts_app, 
            mock_resource_manager
        )

        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
        
        assert found_config is not None
        assert found_config.model == "gpt-4"
        assert found_config.provider == "openai"
        assert found_config.api_key == "sk-openai"
        assert found_config.base_url == "https://api.openai.com/v1" # Mapped from api_base
        assert found_config.temperature == 0.5

        # CASE 2: Request Claude model
        mock_gpts_app.llm_config.llm_strategy_value = "claude-3-opus"
        # Reset mock
        mock_agent_instance.bind.reset_mock()
        
        await agent_builder._build_auto_plan_agent(
                mock_agent_context, 
                mock_agent_memory, 
                mock_gpts_app, 
                mock_resource_manager
            )
        
        found_config = None
        for call in mock_agent_instance.bind.call_args_list:
            args, _ = call
            if args and hasattr(args[0], 'agent_llm_config'):
                found_config = args[0].agent_llm_config
                break
                
        assert found_config is not None
        assert found_config.model == "claude-3-opus"
        assert found_config.provider == "claude"
        assert found_config.api_key == "sk-claude"
        assert found_config.temperature == 0.1


