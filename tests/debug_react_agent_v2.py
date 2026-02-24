import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock

# Add the package directories to sys.path
sys.path.append(os.path.abspath("packages/derisk-core/src"))
sys.path.append(os.path.abspath("packages/derisk-serve/src"))
sys.path.append(os.path.abspath("packages/derisk-ext/src"))
# DO NOT add derisk-app since we uninstalled it or it is causing issues

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_react")

# Mock the missing dependencies that caused the crash
import sys
from unittest.mock import MagicMock

# Mock derisk_app.config
mock_derisk_app = MagicMock()
mock_config = MagicMock()
mock_config.SandboxConfigParameters = MagicMock
sys.modules["derisk_app"] = mock_derisk_app
sys.modules["derisk_app.config"] = mock_config

# Mock sofapy which caused ModuleNotFoundError
mock_sofapy = MagicMock()
sys.modules["sofapy"] = mock_sofapy
sys.modules["sofapy.core"] = mock_sofapy
sys.modules["sofapy.core.mcp"] = mock_sofapy
sys.modules["sofapy.core.mcp.client"] = mock_sofapy
sys.modules["sofapy.core.mcp.client.client"] = mock_sofapy


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
            agent = ReActAgent(llm_config=MagicMock())

        # Manually call register_variables to register the sandbox variable
        logger.info("Registering variables...")
        agent.register_variables()

        # Access the registered variable function
        # The variables are stored in agent._vm.variables
        # We need to find the one with name "sandbox"
        var_func = agent._vm.variables.get("sandbox").func

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
