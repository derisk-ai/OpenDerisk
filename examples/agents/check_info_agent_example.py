# -*- coding:utf-8 -*-
"""
--------------------------------------
@Author: luosongshan.lss
@File: check_info_agent.py
@Time: 2025/6/12 21:37
@Desc: 
--------------------------------------
"""
import asyncio
from derisk.agent import AgentMemory, AgentContext, UserProxyAgent, LLMConfig
from derisk.agent.expand.resources.search_tool import baidu_search
from derisk.agent.resource import ToolPack
from derisk_ext.agent.agents.smartTestUI.check_info_agent import SmartTestUICheckInfoAgent
from derisk_ext.agent.agents.smartTestUI.tool.chek_info_tools import _wushu_simple_calculator, wushu_count_directory_files
from derisk_ext.vis.gptvis.gpt_vis_converter import GptVisConverter
from derisk.agent.expand.actions.react_action import Terminate


async def main():
    from derisk.model import AutoLLMClient

    # llm_client = AutoLLMClient(
    #     # provider=os.getenv("LLM_PROVIDER", "proxy/deepseek"),
    #     # name=os.getenv("LLM_MODEL_NAME", "deepseek-chat"),
    #     provider=os.getenv("LLM_PROVIDER", "proxy/siliconflow"),
    #     name=os.getenv("LLM_MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct"),
    # )


    agent_memory = AgentMemory()
    agent_memory.gpts_memory.init(conv_id="test456", vis_converter=GptVisConverter())

    # It is important to set the temperature to a low value to get a better result
    context: AgentContext = AgentContext(
        conv_id="test456", gpts_app_name="ReAct", temperature=0.01,
        conv_session_id="123321"
    )

    tools = ToolPack([_wushu_simple_calculator, wushu_count_directory_files, Terminate(), baidu_search])  # 模拟页面上绑定工具

    user_proxy = await UserProxyAgent().bind(agent_memory).bind(context).build()

    tool_engineer = (
        await SmartTestUICheckInfoAgent()
        .bind(context)
        .bind(LLMConfig(llm_client=llm_client))
        .bind(agent_memory)
        .bind(tools)
        .build()
    )

    await user_proxy.initiate_chat(
        recipient=tool_engineer,
        reviewer=user_proxy,
        # message="Calculate the product of 10 and 99, then count the number of files in /Users/wushu/Desktop/code/derisk",
        # message="Calculate the product of 10 and 99",
        message="How will the weather be in Changsha tomorrow",
        # message="Count the number of files in /Users/wushu/Desktop/code/derisk",
    )

    # derisk-vis message infos
    print("*" * 150)
    print(await agent_memory.gpts_memory.vis_messages("test456"))


if __name__ == "__main__":
    asyncio.run(main())
