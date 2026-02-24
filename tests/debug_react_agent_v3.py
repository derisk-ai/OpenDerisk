import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock

# Add the package directories to sys.path
# CRITICAL: Add derisk-app source to path so we use the local version with SandboxConfigParameters
sys.path.append(os.path.abspath("packages/derisk-core/src"))
sys.path.append(os.path.abspath("packages/derisk-serve/src"))
sys.path.append(os.path.abspath("packages/derisk-app/src"))
sys.path.append(os.path.abspath("packages/derisk-ext/src"))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_react")

# Mock sofapy which caused ModuleNotFoundError
mock_sofapy = MagicMock()
sys.modules["sofapy"] = mock_sofapy
sys.modules["sofapy.core"] = mock_sofapy
sys.modules["sofapy.core.mcp"] = mock_sofapy
sys.modules["sofapy.core.mcp.client"] = mock_sofapy
sys.modules["sofapy.core.mcp.client.client"] = mock_sofapy

# Mock sofapy.core which is apparently not a package in our previous mock
# We need to ensure sofapy.core is treated as a package
mock_sofapy_core = MagicMock()
sys.modules["sofapy.core"] = mock_sofapy_core
mock_sofapy_core_mcp = MagicMock()
sys.modules["sofapy.core.mcp"] = mock_sofapy_core_mcp
mock_sofapy_core_mcp.client = MagicMock()
mock_sofapy_core_mcp.client.client = mock_sofapy
mock_sofapy_core.app = MagicMock()
sys.modules["sofapy.core.app"] = mock_sofapy_core.app

# Mock sofapy.middlewares.rpc
mock_sofapy_middlewares = MagicMock()

sys.modules["sofapy.middlewares"] = mock_sofapy_middlewares
mock_sofapy_middlewares_rpc = MagicMock()
sys.modules["sofapy.middlewares.rpc"] = mock_sofapy_middlewares_rpc
mock_sofapy_middlewares.rpc = mock_sofapy_middlewares_rpc

# Mock derisk_app.knowledge hierarchy
mock_knowledge_pkg = MagicMock()
sys.modules["derisk_app.knowledge"] = mock_knowledge_pkg

mock_request_pkg = MagicMock()
sys.modules["derisk_app.knowledge.request"] = mock_request_pkg

mock_request_module = MagicMock()


class MockBusinessFieldType:
    pass


mock_request_module.BusinessFieldType = MockBusinessFieldType
sys.modules["derisk_app.knowledge.request.request"] = mock_request_module

# Mock derisk_app.knowledge.request.response
mock_response_module = MagicMock()


class MockDocumentResponse:
    pass


mock_response_module.DocumentResponse = MockDocumentResponse
sys.modules["derisk_app.knowledge.request.response"] = mock_response_module


# Mock mcp package which causes ImportError
mock_mcp = MagicMock()
sys.modules["mcp"] = mock_mcp
sys.modules["mcp.shared"] = mock_mcp
sys.modules["mcp.shared.session"] = mock_mcp
mock_mcp.ProgressFnT = MagicMock()

# Mock mcp.types
mock_mcp_types = MagicMock()
sys.modules["mcp.types"] = mock_mcp_types
mock_mcp.types = mock_mcp_types
# Add required classes to mcp.types
mock_mcp_types.CallToolResult = MagicMock()
mock_mcp_types.ImageContent = MagicMock()
mock_mcp_types.TextContent = MagicMock()

# Mock mcp.client
mock_mcp_client = MagicMock()
sys.modules["mcp.client"] = mock_mcp_client
mock_mcp.client = mock_mcp_client
mock_mcp_client_session = MagicMock()
sys.modules["mcp.client.session"] = mock_mcp_client_session
mock_mcp_client.session = mock_mcp_client_session
# Add ClientSession to the mock
mock_mcp_client_session.ClientSession = MagicMock()
# Add sse_client to the mock
mock_mcp_client_sse = MagicMock()
sys.modules["mcp.client.sse"] = mock_mcp_client_sse
mock_mcp_client.sse = mock_mcp_client_sse
mock_mcp_client_sse.sse_client = MagicMock()


async def test_sandbox_injection():
    try:
        # Import ReActAgent
        logger.info("Importing ReActAgent...")
        from derisk.agent.expand.react_agent.react_agent import ReActAgent

        # Instantiate agent
        # We might need to mock some args for init if it fails
        logger.info("Instantiating ReActAgent...")
        try:
            agent = ReActAgent()
        except Exception as e:
            logger.warning(f"Direct instantiation failed: {e}. Trying with mocks.")
            # If init fails, we might need to mock more things, but let's see.
            # ReActAgent init is:
            # super().__init__(**kwargs) -> ManagerAgent -> ConversableAgent
            # It creates some PrivateAttrs.
            agent = ReActAgent(llm_config=MagicMock())

        # Manually call register_variables to register the sandbox variable
        logger.info("Registering variables...")
        agent.register_variables()

        # Access the registered variable function
        # The variables are stored in agent._vm._registry
        # We need to find the one with name "sandbox"
        var_info = agent._vm._registry.get("sandbox")
        if not var_info:
            logger.error("Could not find 'sandbox' variable info")
            return

        var_func = var_info.get("func")

        if not var_func:
            logger.error("Could not find 'sandbox' variable function")
            return

        # Mock an instance that has a sandbox_manager
        mock_instance = MagicMock()
        mock_instance.sandbox_manager = MagicMock()
        mock_instance.sandbox_manager.initialized = True
        mock_instance.sandbox_manager.client = MagicMock()
        mock_instance.sandbox_manager.client.work_dir = "/tmp/sandbox"
        mock_instance.sandbox_manager.client.enable_skill = False
        mock_instance.sandbox_manager.client.skill_dir = ""
        mock_instance.agent_context = MagicMock()
        mock_instance.agent_context.language = "en"

        # Call the function
        logger.info("Calling var_sandbox...")
        result = await var_func(mock_instance)

        logger.info("Result keys: %s", result.keys())
        logger.info("Enable: %s", result.get("enable"))
        tools = result.get("tools", "")
        logger.info("Tools content length: %d", len(tools))

        if len(tools) > 0:
            logger.info("Tools content preview: %s", tools[:200])
        else:
            logger.warning("Tools content is EMPTY!")

            # Debug why it is empty
            from derisk.agent.core.sandbox.sandbox_tool_registry import (
                sandbox_tool_dict,
            )

            logger.info(
                f"Global sandbox_tool_dict keys: {list(sandbox_tool_dict.keys())}"
            )

    except Exception as e:
        logger.exception("Error during test")


if __name__ == "__main__":
    asyncio.run(test_sandbox_injection())
