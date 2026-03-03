"""
Core V2 VIS 使用示例

演示如何在 ProductionAgent 中使用 vis_window3 布局能力
"""

import asyncio
from derisk.agent.core_v2.production_agent import ProductionAgent
from derisk.agent.core_v2.vis_protocol import VisWindow3Data


async def basic_usage():
    """基本使用示例"""
    
    # 1. 创建 Agent（启用 VIS）
    agent = ProductionAgent.create(
        name="data-analyst",
        model="gpt-4",
        api_key="sk-xxx",
        enable_vis=True,  # 启用 VIS 能力
    )
    
    # 2. 初始化交互
    agent.init_interaction(session_id="demo-session")
    
    # 3. 运行 Agent
    async for chunk in agent.run("帮我分析销售数据"):
        print(chunk, end="")
    
    # 4. 生成 VIS 输出
    vis_output = await agent.generate_vis_output()
    print("\n\nVIS Output:")
    print(vis_output)


async def manual_step_control():
    """手动控制步骤示例"""
    
    agent = ProductionAgent.create(
        name="manual-agent",
        enable_vis=True,
    )
    
    agent.init_interaction()
    
    # 手动添加步骤
    agent.add_vis_step("step1", "数据收集", status="completed", result_summary="已收集100条数据")
    agent.add_vis_step("step2", "数据分析", status="running")
    agent.add_vis_step("step3", "生成报告", status="pending")
    
    # 设置当前步骤
    agent.get_vis_adapter().set_current_step("step2")
    
    # 添加思考内容
    agent.get_vis_adapter().set_thinking("正在分析数据趋势...")
    
    # 添加产物
    agent.add_vis_artifact(
        artifact_id="chart1",
        artifact_type="image",
        content="![销售趋势图](chart.png)",
        title="销售趋势分析",
    )
    
    # 生成 VIS 输出
    vis_output = await agent.generate_vis_output()
    print(vis_output)


async def structured_output():
    """结构化输出示例"""
    
    agent = ProductionAgent.create(enable_vis=True)
    agent.init_interaction()
    
    # 手动构建步骤
    adapter = agent.get_vis_adapter()
    
    # 添加多个步骤
    steps = [
        ("1", "需求分析", "completed", "已完成需求调研"),
        ("2", "方案设计", "completed", "技术方案已确定"),
        ("3", "代码实现", "running", None),
        ("4", "测试验证", "pending", None),
        ("5", "部署上线", "pending", None),
    ]
    
    for step_id, title, status, result in steps:
        adapter.add_step(step_id, title, status, result_summary=result)
    
    adapter.set_current_step("3")
    adapter.set_thinking("正在编写核心模块...")
    adapter.set_content("```python\ndef main():\n    pass\n```")
    
    adapter.add_artifact(
        artifact_id="code_main",
        artifact_type="code",
        content="# Main module\npass",
        title="main.py",
    )
    
    # 生成并解析输出
    vis_output = await agent.generate_vis_output(use_gpts_format=False)
    
    # 解析为结构化数据
    vis_data = VisWindow3Data.from_dict(vis_output)
    
    print("=== Planning Window ===")
    for step in vis_data.planning_window.steps:
        print(f"  {step.step_id}. {step.title} [{step.status}]")
    
    print("\n=== Running Window ===")
    if vis_data.running_window.current_step:
        print(f"  Current: {vis_data.running_window.current_step.title}")
    print(f"  Thinking: {vis_data.running_window.thinking[:50]}...")
    print(f"  Artifacts: {len(vis_data.running_window.artifacts)}")


async def with_progress_broadcaster():
    """结合 ProgressBroadcaster 使用"""
    
    from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster
    
    # 创建进度广播器
    progress = ProgressBroadcaster(session_id="demo")
    
    # 创建 Agent
    agent = ProductionAgent.create(
        enable_vis=True,
        progress_broadcaster=progress,
    )
    
    agent.init_interaction()
    
    # 订阅进度事件
    async def on_progress(event):
        print(f"[{event.type.value}] {event.content}")
    
    progress.subscribe(on_progress)
    
    # 运行
    async for chunk in agent.run("查询数据库"):
        pass
    
    # 获取 VIS 输出
    vis_output = await agent.generate_vis_output()
    print(vis_output)


async def integration_with_api():
    """API 集成示例（FastAPI）"""
    
    from fastapi import FastAPI, WebSocket
    from fastapi.responses import JSONResponse
    
    app = FastAPI()
    
    @app.post("/api/agent/run")
    async def run_agent(task: str):
        agent = ProductionAgent.create(enable_vis=True)
        agent.init_interaction()
        
        # 运行
        result = []
        async for chunk in agent.run(task):
            result.append(chunk)
        
        # 生成 VIS 数据
        vis_data = await agent.generate_vis_output()
        
        return {
            "result": "".join(result),
            "vis": vis_data,
        }
    
    @app.websocket("/ws/agent/{session_id}")
    async def websocket_agent(websocket: WebSocket, session_id: str):
        await websocket.accept()
        
        from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster
        
        progress = ProgressBroadcaster(session_id=session_id)
        progress.add_websocket(websocket)
        
        agent = ProductionAgent.create(
            enable_vis=True,
            progress_broadcaster=progress,
        )
        
        agent.init_interaction(session_id=session_id)
        
        try:
            task = await websocket.receive_text()
            
            async for chunk in agent.run(task):
                # 发送流式输出
                await websocket.send_json({
                    "type": "chunk",
                    "content": chunk,
                })
            
            # 发送 VIS 数据
            vis_output = await agent.generate_vis_output()
            await websocket.send_json({
                "type": "vis",
                "data": vis_output,
            })
            
            await websocket.send_json({"type": "complete"})
        
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })


if __name__ == "__main__":
    print("=== Basic Usage ===")
    asyncio.run(basic_usage())
    
    print("\n=== Manual Step Control ===")
    asyncio.run(manual_step_control())
    
    print("\n=== Structured Output ===")
    asyncio.run(structured_output())