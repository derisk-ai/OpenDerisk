#!/usr/bin/env python
"""
Core_v2 Agent 启动脚本

使用方式:
    python start_v2_agent.py              # 启动 CLI 交互
    python start_v2_agent.py --api         # 启动 API 服务
    python start_v2_agent.py --demo        # 运行演示
"""
import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))


def run_cli():
    """运行 CLI 交互"""
    from derisk_serve.agent.quickstart_v2 import quickstart
    asyncio.run(quickstart())


def run_api():
    """运行 API 服务"""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from derisk_serve.agent.core_v2_api import router as core_v2_router
    from derisk_serve.agent.core_v2_adapter import get_core_v2
    
    app = FastAPI(title="Core_v2 Agent API", version="1.0.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(core_v2_router)
    
    @app.on_event("startup")
    async def startup():
        core_v2 = get_core_v2()
        await core_v2.start()
    
    @app.on_event("shutdown")
    async def shutdown():
        core_v2 = get_core_v2()
        await core_v2.stop()
    
    print("\n" + "=" * 50)
    print("Core_v2 Agent API 服务")
    print("=" * 50)
    print("\nAPI 端点:")
    print("  POST /api/v2/session   - 创建会话")
    print("  POST /api/v2/chat      - 发送消息 (SSE)")
    print("  GET  /api/v2/status    - 查看状态")
    print("\n启动服务...\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8080)


def run_demo():
    """运行演示"""
    async def demo():
        from derisk.agent.core_v2.integration import create_v2_agent
        from derisk.agent.tools_v2 import BashTool
        
        print("\n" + "=" * 50)
        print("Core_v2 Agent 演示")
        print("=" * 50)
        
        agent = create_v2_agent(
            name="demo",
            mode="planner",
            tools={"bash": BashTool()},
        )
        
        print("\n执行: '执行 pwd 命令'\n")
        async for chunk in agent.run("执行 pwd 命令"):
            print(chunk)
        
        print("\n演示完成!")
    
    asyncio.run(demo())


def main():
    parser = argparse.ArgumentParser(description="Core_v2 Agent 启动")
    parser.add_argument("--api", action="store_true", help="启动 API 服务")
    parser.add_argument("--demo", action="store_true", help="运行演示")
    args = parser.parse_args()
    
    if args.api:
        run_api()
    elif args.demo:
        run_demo()
    else:
        run_cli()


if __name__ == "__main__":
    main()
