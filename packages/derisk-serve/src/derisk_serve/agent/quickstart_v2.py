"""
Core_v2 快速启动示例

直接运行此文件即可体验 Core_v2 Agent
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))))


async def quickstart():
    """快速启动 Core_v2 Agent"""
    from derisk.agent.core_v2.integration import (
        V2AgentRuntime,
        RuntimeConfig,
        V2AgentDispatcher,
        create_v2_agent,
    )
    from derisk.agent.tools_v2 import BashTool
    
    print("=" * 60)
    print("Core_v2 Agent 快速启动")
    print("=" * 60)
    
    # 1. 创建运行时
    print("\n[1/4] 创建运行时...")
    runtime = V2AgentRuntime(
        config=RuntimeConfig(
            max_concurrent_sessions=10,
            enable_streaming=True,
        )
    )
    
    # 2. 注册 Agent
    print("[2/4] 注册 Agent...")
    runtime.register_agent_factory(
        "assistant",
        lambda context, **kw: create_v2_agent(
            name="assistant",
            mode="planner",
            tools={"bash": BashTool()},
            permission={"*": "allow"},
        )
    )
    
    # 3. 创建调度器并启动
    print("[3/4] 启动调度器...")
    dispatcher = V2AgentDispatcher(runtime=runtime, max_workers=5)
    await dispatcher.start()
    
    # 4. 创建会话并对话
    print("[4/4] 创建会话并开始对话...\n")
    session = await runtime.create_session(
        user_id="demo_user",
        agent_name="assistant",
    )
    
    print(f"会话ID: {session.session_id}")
    print("输入 'quit' 或 'exit' 退出\n")
    
    while True:
        try:
            user_input = input("你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["quit", "exit", "退出"]:
                break
            
            print("\n助理: ", end="", flush=True)
            async for chunk in dispatcher.dispatch_and_wait(
                message=user_input,
                session_id=session.session_id,
            ):
                if chunk.type == "response":
                    print(chunk.content, end="", flush=True)
                elif chunk.type == "thinking":
                    print(f"\n[思考] {chunk.content}", end="", flush=True)
                elif chunk.type == "tool_call":
                    tool_name = chunk.metadata.get("tool_name", "")
                    print(f"\n[工具] {tool_name}", end="", flush=True)
                elif chunk.type == "error":
                    print(f"\n[错误] {chunk.content}", end="", flush=True)
            print("\n")
            
        except KeyboardInterrupt:
            break
    
    # 清理
    await runtime.close_session(session.session_id)
    await dispatcher.stop()
    print("\n再见!")


def main():
    """主入口"""
    asyncio.run(quickstart())


if __name__ == "__main__":
    main()
