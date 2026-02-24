import sys
import os
import logging

# Add the package directories to sys.path so imports work
sys.path.append(os.path.abspath("packages/derisk-core/src"))
sys.path.append(os.path.abspath("packages/derisk-serve/src"))
sys.path.append(os.path.abspath("packages/derisk-app/src"))
sys.path.append(os.path.abspath("packages/derisk-ext/src"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_sandbox_registry():
    logger.info("Starting registry check...")

    # Import the registry first to see if it's empty initially
    from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool_dict

    logger.info(f"Initial sandbox_tool_dict keys: {list(sandbox_tool_dict.keys())}")

    # Now import the core module which SHOULD import the tools and trigger decorators
    logger.info("Importing derisk.agent.core...")
    import derisk.agent.core

    # Check the registry again
    logger.info(f"Post-import sandbox_tool_dict keys: {list(sandbox_tool_dict.keys())}")

    expected_tools = [
        "execute_create_file",
        "execute_edit_file",
        "shell_exec",
        "execute_view",
        "browser_navigate",
        "execute_download_file",
    ]

    missing_tools = [t for t in expected_tools if t not in sandbox_tool_dict]

    if missing_tools:
        logger.error(f"FAIL: Missing tools in registry: {missing_tools}")
    else:
        logger.info("SUCCESS: All expected tools found in registry.")


if __name__ == "__main__":
    check_sandbox_registry()
