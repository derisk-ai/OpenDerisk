"""Run your code assistant agent in a sandbox environment.

This example demonstrates how to use the refactored CodeAssistantAgent
for code generation and execution in sandbox environments.

Features:
1. Multiple language support (Python, JavaScript, Shell)
2. Sandbox integration for safe code execution
3. AgentFileSystem for code file management
4. Iterative code refinement

Examples:

    Execute the following command in the terminal:
    
    .. code-block:: shell
        export SILICONFLOW_API_KEY=sk-xx
        export SILICONFLOW_API_BASE=URL_ADDRESS:80/v1
        uv run examples/agents/sandbox_code_agent_example.py
"""

import asyncio
import logging
import os
import sys
from typing import Optional, Tuple
from unittest.mock import MagicMock

sys.modules["oss2"] = MagicMock()

from derisk.agent import (
    AgentContext,
    AgentMemory,
    AgentMessage,
    HybridMemory,
    LLMConfig,
    ProfileConfig,
    UserProxyAgent,
)
from derisk.agent.core.sandbox_manager import SandboxManager
from derisk.sandbox.sandbox_client import AutoSandbox
from derisk.agent.expand.code_assistant_agent import CodeAssistantAgent

logger = logging.getLogger(__name__)


async def create_sandbox_manager() -> Optional[SandboxManager]:
    sandbox = await AutoSandbox.create(
        user_id="test_user",
        agent="code_assistant",
        type="local",
        work_dir="./workspace_example",
    )
    
    sandbox_manager = SandboxManager(sandbox_client=sandbox)
    await sandbox_manager.initialize(sandbox, prepare_knowledge_repo=False)
    return sandbox_manager


async def main():
    from derisk.model.proxy.llms.siliconflow import SiliconFlowLLMClient

    llm_client = SiliconFlowLLMClient(
        model_alias=os.getenv(
            "SILICONFLOW_MODEL_VERSION", "Qwen/Qwen2.5-Coder-32B-Instruct"
        ),
    )

    context: AgentContext = AgentContext(conv_id="code_test_001")

    from derisk.rag.embedding import OpenAPIEmbeddings
    from derisk.agent.core.memory.agent_memory import AgentMemoryFragment

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
    agent_memory.gpts_memory.init("code_test_001")

    print("Creating sandbox manager...")
    sandbox_manager = await create_sandbox_manager()

    print("Building CodeAssistantAgent...")
    coder_agent = CodeAssistantAgent(
        default_language="python",
        execution_timeout=300,
        auto_save_code=True,
    )
    coder_agent = await (
        coder_agent
        .bind(context)
        .bind(LLMConfig(llm_client=llm_client))
        .bind(agent_memory)
        .bind(sandbox_manager)
        .build()
    )

    user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()

    print("\n" + "="*60)
    print("Test 1: Simple Python calculation")
    print("="*60)
    await user_proxy.initiate_chat(
        recipient=coder_agent,
        reviewer=user_proxy,
        message="计算下 321 * 123 等于多少，使用 Python 代码",
    )

    print("\n" + "="*60)
    print("Test 2: JavaScript calculation")
    print("="*60)
    await user_proxy.initiate_chat(
        recipient=coder_agent,
        reviewer=user_proxy,
        message="Calculate 100 * 99 using JavaScript code block",
    )

    print("\n" + "="*60)
    print("Test 3: File operations")
    print("="*60)
    await user_proxy.initiate_chat(
        recipient=coder_agent,
        reviewer=user_proxy,
        message="Create a Python script that generates a list of squares from 1 to 10 and saves to a file named squares.txt",
    )

    print("\n" + "="*60)
    print("Execution Summary:")
    print("="*60)
    summary = coder_agent.get_execution_summary()
    print(f"Total executions: {summary.get('total_executions', 0)}")
    print(f"Successful: {summary.get('successful', 0)}")
    print(f"Failed: {summary.get('failed', 0)}")
    print(f"Languages used: {summary.get('languages_used', [])}")

    print("\n" + "="*60)
    print("Code Files:")
    print("="*60)
    code_files = await coder_agent.list_code_files()
    for f in code_files[:5]:
        print(f"  - {f['file_name']} ({f['file_size']} bytes)")


if __name__ == "__main__":
    asyncio.run(main())