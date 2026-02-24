import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock

# Add the package directories to sys.path
sys.path.append(os.path.abspath("packages/derisk-core/src"))
sys.path.append(os.path.abspath("packages/derisk-serve/src"))
sys.path.append(os.path.abspath("packages/derisk-app/src"))
sys.path.append(os.path.abspath("packages/derisk-ext/src"))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_react")


async def test_sandbox_injection():
    try:
        # Import ReActAgent
        logger.info("Importing ReActAgent...")
        # Patch SandboxConfigParameters import if needed
        import sys

        try:
            from derisk_app.config import SandboxConfigParameters
        except ImportError:
            # If standard import fails, try to mock it or fix path
            sys.path.append("packages/derisk-app/src")
            from derisk_app.config import SandboxConfigParameters

        from derisk.agent.expand.react_agent.react_agent import ReActAgent

        # Instantiate agent
        agent = ReActAgent()

        # Manually call register_variables to register the sandbox variable
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
        logger.info("Tools content length: %d", len(result.get("tools", "")))
        logger.info("Tools content preview: %s", result.get("tools", "")[:200])

    except Exception as e:
        logger.exception("Error during test")


if __name__ == "__main__":
    asyncio.run(test_sandbox_injection())
