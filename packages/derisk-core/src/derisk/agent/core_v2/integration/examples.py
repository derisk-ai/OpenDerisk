"""
Core_v2 Integration 完整使用示例

展示如何使用 Integration 层构建可运行的 Agent 产品
"""

import asyncio
from typing import AsyncIterator, Dict, Any


async def example_1_simple_agent():
    """示例1: 创建简单的 Agent"""
    from derisk.agent.core_v2 import AgentInfo, AgentMode, PermissionRuleset
    from derisk.agent.core_v2.integration import create_v2_agent

    agent = create_v2_agent(
        name="simple",
        mode="primary",
    )

    print("[示例1] 简单 Agent 对话")
    async for chunk in agent.run("你好，请介绍一下你自己"):
        print(chunk, end="")


async def example_2_agent_with_tools():
    """示例2: 创建带工具的 Agent"""
    from derisk.agent.tools import BashTool
    from derisk.agent.core_v2.integration import create_v2_agent

    tools = {
        "bash": BashTool(),
    }

    agent = create_v2_agent(
        name="tool_agent",
        mode="primary",
        tools=tools,
        permission={
            "bash": "allow",
        },
    )

    print("[示例2] 带工具的 Agent")
    async for chunk in agent.run("执行 ls 命令查看目录"):
        print(chunk, end="")


async def example_3_use_runtime():
    """示例3: 使用 Runtime 管理会话"""
    from derisk.agent.core_v2.integration import V2AgentRuntime, RuntimeConfig
    from derisk.agent.tools import BashTool
    from derisk.agent.core_v2.integration import create_v2_agent

    config = RuntimeConfig(
        max_concurrent_sessions=100,
        session_timeout=3600,
        enable_streaming=True,
    )

    runtime = V2AgentRuntime(config=config)

    runtime.register_agent_factory(
        "primary",
        lambda context, **kwargs: create_v2_agent(
            name="primary",
            mode="primary",
            tools={"bash": BashTool()},
        ),
    )

    await runtime.start()

    session = await runtime.create_session(
        user_id="user001",
        agent_name="primary",
    )

    print(f"[示例3] Session ID: {session.session_id}")

    async for chunk in runtime.execute(session.session_id, "帮我查看当前目录"):
        print(f"[{chunk.type}] {chunk.content}")

    await runtime.close_session(session.session_id)
    await runtime.stop()


async def example_4_use_dispatcher():
    """示例4: 使用 Dispatcher 调度"""
    from derisk.agent.core_v2.integration import (
        V2AgentDispatcher,
        V2AgentRuntime,
        RuntimeConfig,
    )
    from derisk.agent.tools import BashTool
    from derisk.agent.core_v2.integration import create_v2_agent

    runtime = V2AgentRuntime()

    runtime.register_agent_factory(
        "pdca",
        lambda context, **kwargs: create_v2_agent(
            name="pdca_agent",
            mode="planner",
            tools={"bash": BashTool()},
        ),
    )

    dispatcher = V2AgentDispatcher(runtime=runtime, max_workers=5)

    await dispatcher.start()

    def on_chunk(task, chunk):
        print(f"[流式] {chunk.type}: {chunk.content[:50]}...")

    dispatcher.on_stream_chunk(on_chunk)

    print("[示例4] Dispatch 任务...")

    async for chunk in dispatcher.dispatch_and_wait(
        message="帮我分析项目结构",
        agent_name="pdca",
    ):
        print(f"[响应] {chunk.type}: {chunk.content}")

    await dispatcher.stop()


async def example_5_integrate_gpts_memory():
    """示例5: 集成 GptsMemory"""
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
    from derisk.agent.core_v2.integration import (
        V2AgentRuntime,
        RuntimeConfig,
        V2Adapter,
    )

    try:
        from derisk._private.config import Config

        CFG = Config()
        gpts_memory = CFG.SYSTEM_APP.get_component("gpts_memory", GptsMemory)
    except Exception:
        print("[示例5] GptsMemory 未配置，跳过集成示例")
        return

    adapter = V2Adapter()
    runtime = V2AgentRuntime(
        gpts_memory=gpts_memory,
        adapter=adapter,
    )

    await runtime.start()

    session = await runtime.create_session(
        user_id="user001",
        agent_name="primary",
    )

    queue_iter = await runtime.get_queue_iterator(session.session_id)

    async def consume_queue():
        if queue_iter:
            async for msg in queue_iter:
                print(f"[GptsMemory 消息] {msg}")

    asyncio.create_task(consume_queue())

    async for chunk in runtime.execute(session.session_id, "你好"):
        pass

    await runtime.stop()


async def example_6_build_from_app():
    """示例6: 从 App 构建Agent"""
    from derisk.agent.core_v2.integration import V2ApplicationBuilder
    from derisk.agent.resource.app import AppResource
    from derisk.agent.resource.tool import BaseTool

    class MyTool(BaseTool):
        @classmethod
        def type(cls):
            return "tool"

        @property
        def name(self) -> str:
            return "my_tool"

        async def get_prompt(self, **kwargs):
            return "我的自定义工具", None

        async def execute(self, *args, **kwargs):
            return "工具执行结果"

    class MyApp:
        name = "my_app"
        description = "我的应用"
        max_steps = 20
        resources = [MyTool()]

    builder = V2ApplicationBuilder()
    result = await builder.build_from_app(MyApp())

    print(f"[示例6] 构建成功:")
    print(f"  Agent: {result.agent_info.name}")
    print(f"  Tools: {list(result.tools.keys())}")
    print(f"  Resources: {list(result.resources.keys())}")


async def example_7_full_application():
    """示例7: 完整应用 - CLI 交互 Agent"""
    from derisk.agent.core_v2.integration import (
        V2AgentRuntime,
        RuntimeConfig,
        V2AgentDispatcher,
        V2Adapter,
    )
    from derisk.agent.tools import BashTool
    from derisk.agent.core_v2.integration import create_v2_agent

    print("=" * 50)
    print("[示例7] 完整 CLI Agent 应用")
    print("=" * 50)

    runtime = V2AgentRuntime(
        config=RuntimeConfig(enable_streaming=True, enable_progress=True),
    )

    runtime.register_agent_factory(
        "assistant",
        lambda context, **kwargs: create_v2_agent(
            name="CLI Assistant",
            mode="planner",
            tools={"bash": BashTool()},
            permission={
                "*": "allow",
            },
        ),
    )

    await runtime.start()

    session = await runtime.create_session(
        user_id="cli_user",
        agent_name="assistant",
    )

    print(f"\n会话已创建: {session.session_id[:8]}")
    print("输入 'quit' 或 'exit' 退出\n")

    while True:
        try:
            user_input = input("\n你: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit"]:
                break

            print("\n助理: ", end="")

            async for chunk in runtime.execute(session.session_id, user_input):
                if chunk.type == "response":
                    print(chunk.content, end="", flush=True)
                elif chunk.type == "thinking":
                    print(f"\n[思考] {chunk.content}", end="")
                elif chunk.type == "tool_call":
                    print(
                        f"\n[工具] {chunk.metadata.get('tool_name')}: {chunk.content}",
                        end="",
                    )

            print()

        except KeyboardInterrupt:
            break

    await runtime.close_session(session.session_id)
    await runtime.stop()

    print("\n[示例7] 应用已退出")


async def main():
    """运行所有示例"""
    print("Core_v2 Integration 使用示例")
    print("=" * 60)

    print("\n--- 示例1: 简单 Agent ---")
    await example_1_simple_agent()

    print("\n\n--- 示例2: 带工具的 Agent ---")
    await example_2_agent_with_tools()

    print("\n\n--- 示例3: Runtime 会话管理 ---")
    await example_3_use_runtime()

    print("\n\n--- 示例4: Dispatcher 调度 ---")
    await example_4_use_dispatcher()

    print("\n\n--- 示例5: GptsMemory 集成 ---")
    await example_5_integrate_gpts_memory()

    print("\n\n--- 示例6: 从 App 构建 ---")
    await example_6_build_from_app()

    print("\n\n--- 示例7: 完整应用 ---")
    await example_7_full_application()


if __name__ == "__main__":
    asyncio.run(main())
