"""Agents: single agents about CodeAssistantAgent?

Examples:

    Execute the following command in the terminal:
    Set env params.
    .. code-block:: shell

        export OPENAI_API_KEY=sk-xx
        export OPENAI_API_BASE=https://xx:80/v1

    run example.
    ..code-block:: shell
        uv run examples/agents/sql_agent_dialogue_example.py
"""

import asyncio
import os

from derisk.agent import AgentContext, AgentMemory, LLMConfig, UserProxyAgent
from derisk.agent.expand.data_scientist_agent import DataScientistAgent
from derisk.agent.resource import SQLiteDBResource
from derisk.configs.model_config import ROOT_PATH
from derisk.util.tracer import initialize_tracer

test_plugin_dir = os.path.join(ROOT_PATH, "test_files")

initialize_tracer("/tmp/agent_trace.jsonl", create_system_app=True)


async def main():
    from derisk.model.proxy.llms.siliconflow import SiliconFlowLLMClient

    llm_client = SiliconFlowLLMClient(
        model_alias=os.getenv(
            "SILICONFLOW_MODEL_VERSION", "Qwen/Qwen2.5-Coder-32B-Instruct"
        ),
    )
    context: AgentContext = AgentContext(conv_id="test456")

    agent_memory = AgentMemory()
    agent_memory.gpts_memory.init(conv_id="test456")

    sqlite_resource = SQLiteDBResource(
        "SQLite Database", f"{test_plugin_dir}/derisk.db"
    )
    user_proxy = await UserProxyAgent().bind(agent_memory).bind(context).build()

    sql_boy = (
        await DataScientistAgent()
        .bind(context)
        .bind(LLMConfig(llm_client=llm_client))
        .bind(sqlite_resource)
        .bind(agent_memory)
        .build()
    )

    await user_proxy.initiate_chat(
        recipient=sql_boy,
        reviewer=user_proxy,
        message="当前库有那些表",
    )

    ## derisk-vis message infos
    print(await agent_memory.gpts_memory.vis_messages("test456"))


if __name__ == "__main__":
    asyncio.run(main())
