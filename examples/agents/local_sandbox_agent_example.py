"""Run your code assistant agent in a local sandbox environment.

This example demonstrates how to use the LocalSandbox provider to execute code
in a locally isolated environment. This is useful for development and testing
when you don't have access to a remote sandbox service.

WARNING: LocalSandbox provides process-level isolation but is not as secure
as a containerized or VM-based sandbox. Use with caution when executing untrusted code.

Examples:

    Execute the following command in the terminal:
    Set env params.
    .. code-block:: shell
        export SILICONFLOW_API_KEY=sk-xx
        export SILICONFLOW_API_BASE=URL_ADDRESS:80/v1
    run example.
    ..code-black:: shell
        uv run examples/agents/local_sandbox_agent_example.py

"""

import sys
from unittest.mock import MagicMock
sys.modules["oss2"] = MagicMock()
import asyncio
import logging
import os
from typing import Optional, Tuple

from derisk.agent import (
    Action,
    ActionOutput,
    AgentContext,
    AgentMemory,
    AgentMemoryFragment,
    AgentMessage,
    AgentResource,
    ConversableAgent,
    HybridMemory,
    LLMConfig,
    ProfileConfig,
    UserProxyAgent,
)
from derisk.agent.expand.code_assistant_agent import CHECK_RESULT_SYSTEM_MESSAGE
from derisk.core import ModelMessageRoleType
from derisk.util.code_utils import UNKNOWN, extract_code, infer_lang
from derisk.util.string_utils import str_to_bool
from derisk.util.logger import colored
from derisk.vis import Vis
from derisk_ext.vis.common.tags.vis_code import VisCode
from derisk_ext.sandbox.local import LocalSandbox

logger = logging.getLogger(__name__)


class LocalSandboxCodeAction(Action[None]):
    """Code Action Module using LocalSandbox."""

    def __init__(self, **kwargs):
        """Code action init."""
        super().__init__(**kwargs)
        self._render_protocol = VisCode()
        # Initialize LocalSandbox
        self.sandbox = LocalSandbox(
            user_id="example_user",
            work_dir="./workspace_example" # Specify a workspace directory
        )

    @property
    def render_protocol(self) -> Optional[Vis]:
        """Return the render protocol."""
        return self._render_protocol

    async def run(
        self,
        ai_message: str,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        try:
            code_blocks = extract_code(ai_message)
            if len(code_blocks) < 1:
                logger.info(
                    f"No executable code found in answer,{ai_message}",
                )
                return ActionOutput(
                    is_exe_success=False, content="No executable code found in answer."
                )
            elif len(code_blocks) > 1 and code_blocks[0][0] == UNKNOWN:
                logger.info(
                    f"Missing available code block type, unable to execute code,"
                    f"{ai_message}",
                )
                return ActionOutput(
                    is_exe_success=False,
                    content="Missing available code block type, "
                    "unable to execute code.",
                )
            
            # Execute code blocks using LocalSandbox
            exitcode, logs = await self.execute_code_blocks(code_blocks)
            exit_success = exitcode == 0

            content = (
                logs
                if exit_success
                else f"exitcode: {exitcode} (execution failed)\n {logs}"
            )

            param = {
                "exit_success": exit_success,
                "language": code_blocks[0][0],
                "code": code_blocks,
                "log": logs,
            }
            if not self.render_protocol:
                raise NotImplementedError("The render_protocol should be implemented.")
            view = await self.render_protocol.display(content=param)
            return ActionOutput(
                is_exe_success=exit_success,
                content=content,
                view=view,
                thoughts=ai_message,
                observations=content,
            )
        except Exception as e:
            logger.exception("Code Action Run Failed！")
            return ActionOutput(
                is_exe_success=False, content="Code execution exception，" + str(e)
            )

    async def execute_code_blocks(self, code_blocks):
        """Execute the code blocks and return the result."""
        logs_all = ""
        exitcode = -1
        
        for i, code_block in enumerate(code_blocks):
            lang, code = code_block
            if not lang:
                lang = infer_lang(code)
            
            print(
                colored(
                    f"\n>>>>>>>> EXECUTING CODE BLOCK {i} "
                    f"(inferred language is {lang})...",
                    "red",
                ),
                flush=True,
            )

            # Map languages to what LocalSandbox supports
            if lang in ["python", "Python"]:
                sandbox_lang = "python"
            elif lang in ["bash", "shell", "sh"]:
                sandbox_lang = "bash"
            else:
                return 1, f"Language {lang} is not supported by LocalSandbox (only python/bash)"

            try:
                # Use LocalSandbox to run code
                # Note: LocalSandbox returns string output, not (exitcode, logs) tuple directly
                # We need to parse or assume success if no exception/error prefix
                output = await self.sandbox.run_code(code, language=sandbox_lang)
                
                # Simple heuristic for exit code based on output content
                # In a real scenario, you might want LocalSandbox to return a structured result object
                if output.startswith("Error:") or output.startswith("System Error:"):
                    exitcode = 1
                else:
                    exitcode = 0
                
                logs = output
                
            except Exception as e:
                exitcode = 1
                logs = str(e)

            logs_all += "\n" + logs
            if exitcode != 0:
                return exitcode, logs_all
                
        return exitcode, logs_all


class LocalSandboxAgent(ConversableAgent):
    """Agent that uses LocalSandbox for code execution."""

    profile: ProfileConfig = ProfileConfig(
        name="LocalDev",
        role="Developer",
        goal=(
            "Write and execute code to solve tasks using the local environment.\n"
            "You can use Python or Bash scripts."
        ),
        constraints=[
            "Use 'python' or 'bash' code blocks.",
            "Only output the code block you want to execute.",
        ],
        desc="Can execute python and bash code locally."
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_actions([LocalSandboxCodeAction])


async def main():
    from derisk.model.proxy.llms.siliconflow import SiliconFlowLLMClient

    # Ensure API keys are set
    if not os.getenv("SILICONFLOW_API_KEY"):
        print("Please set SILICONFLOW_API_KEY environment variable.")
        return

    llm_client = SiliconFlowLLMClient(
        model_alias=os.getenv(
            "SILICONFLOW_MODEL_VERSION", "Qwen/Qwen2.5-Coder-32B-Instruct"
        ),
    )
    context: AgentContext = AgentContext(conv_id="local_sandbox_test")

    # Simple memory setup
    # TODO Embedding and Rerank model refactor
    from derisk.rag.embedding import OpenAPIEmbeddings

    silicon_embeddings = OpenAPIEmbeddings(
        api_url=os.getenv("SILICONFLOW_API_BASE") + "/embeddings",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        model_name="BAAI/bge-large-zh-v1.5",
    )
    agent_memory = AgentMemory(
        HybridMemory[AgentMemoryFragment].from_chroma(
            embeddings=silicon_embeddings,
        )
    )
    agent_memory.gpts_memory.init("local_sandbox_test")

    # Build the agent
    coder = (
        await LocalSandboxAgent()
        .bind(context)
        .bind(LLMConfig(llm_client=llm_client))
        .bind(agent_memory)
        .build()
    )

    user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()

    # Test Case 1: Python Math
    print("\n--- Test Case 1: Python Math ---")
    await user_proxy.initiate_chat(
        recipient=coder,
        reviewer=user_proxy,
        message="Calculate sum of numbers from 1 to 100 using python.",
    )

    # Test Case 2: System Info (Bash)
    print("\n--- Test Case 2: System Info (Bash) ---")
    await user_proxy.initiate_chat(
        recipient=coder,
        reviewer=user_proxy,
        message="Check current working directory and list files using bash.",
    )


if __name__ == "__main__":
    asyncio.run(main())
