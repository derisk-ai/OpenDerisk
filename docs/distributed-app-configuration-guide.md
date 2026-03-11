"""
分布式执行应用配置教程

本文档说明如何在应用编辑页面配置使用分布式执行机制：
1. Worker进程池
2. 监控仪表盘
3. 数据库存储
4. 交互式子Agent
"""

# =============================================================================
# 一、应用配置结构
# =============================================================================

"""
GptsApp 关键字段:
- agent_version: "v1" (经典) 或 "v2" (Core_v2)
- ext_config: 扩展配置字典
- resource_agent: 子Agent资源配置
"""

# =============================================================================
# 二、配置方式
# =============================================================================

# 方式1: 通过 ext_config 配置分布式执行

APP_CONFIG_EXAMPLE = {
    "app_code": "distributed-analysis-app",
    "app_name": "分布式分析应用",
    "app_describe": "支持大规模并行分析的智能应用",
    "agent_version": "v2",  # 使用 Core_v2
    
    # 扩展配置 - 分布式执行设置
    "ext_config": {
        # 存储配置
        "storage": {
            "backend": "redis",  # memory, file, redis, database
            "redis_url": "redis://localhost:6379/0",
            # 或数据库
            # "backend": "database",
            # "database_url": "postgresql://user:pass@localhost/agent_db",
        },
        
        # Worker池配置
        "worker_pool": {
            "enabled": True,
            "min_workers": 2,
            "max_workers": 10,
            "max_tasks_per_worker": 10,
            "auto_scale": True,
            "load_balance": "least_loaded",  # round_robin, least_loaded, random, weighted
        },
        
        # 监控配置
        "monitoring": {
            "enabled": True,
            "websocket_enabled": True,
            "max_history_events": 1000,
        },
        
        # 子Agent配置
        "subagents": [
            {
                "name": "data_collector",
                "description": "数据采集Agent - 从多个数据源收集数据",
                "max_instances": 20,
                "timeout": 300,
                "retry_count": 3,
            },
            {
                "name": "analyzer",
                "description": "数据分析Agent - 对数据进行深度分析",
                "max_instances": 10,
                "interactive": True,  # 支持交互式
            },
            {
                "name": "reporter",
                "description": "报告生成Agent - 生成分析报告",
                "max_instances": 5,
            },
        ],
    },
}


# =============================================================================
# 三、后端集成代码
# =============================================================================

async def create_distributed_app(config: dict):
    """创建分布式执行应用"""
    from derisk.agent.core_v2 import (
        AgentApplication,
        AgentApplicationRunner,
        StateStorageFactory,
        create_worker_pool,
        get_dashboard,
    )
    
    ext_config = config.get("ext_config", {})
    
    # 1. 配置存储
    storage_config = ext_config.get("storage", {})
    if storage_config.get("backend") == "redis":
        storage = StateStorageFactory.create_redis(
            storage_config["redis_url"]
        )
    elif storage_config.get("backend") == "database":
        storage = StateStorageFactory.create_database(
            storage_config["database_url"]
        )
    else:
        storage = StateStorageFactory.create_default()
    
    # 2. 创建应用
    from derisk.agent.expand.react_master_agent import ReActMasterAgent
    
    app = AgentApplication(
        app_id=config["app_code"],
        name=config["app_name"],
        main_agent_class=ReActMasterAgent,
        storage_backend=storage_config.get("backend", "memory"),
        storage_config=storage_config,
    )
    
    # 3. 绑定子Agent
    for subagent_config in ext_config.get("subagents", []):
        # 这里需要实际的Agent类
        subagent_class = get_subagent_class(subagent_config["name"])
        
        app.bind_subagent(
            name=subagent_config["name"],
            agent_class=subagent_class,
            description=subagent_config["description"],
            max_instances=subagent_config.get("max_instances", 5),
        )
    
    # 4. 创建运行器
    runner = AgentApplicationRunner(app)
    await runner.initialize()
    
    # 5. 启动Worker池 (如果配置)
    worker_pool = None
    if ext_config.get("worker_pool", {}).get("enabled"):
        wp_config = ext_config["worker_pool"]
        worker_pool = create_worker_pool(
            min_workers=wp_config.get("min_workers", 2),
            max_workers=wp_config.get("max_workers", 10),
        )
        await worker_pool.start()
    
    # 6. 启动监控仪表盘 (如果配置)
    dashboard = None
    if ext_config.get("monitoring", {}).get("enabled"):
        dashboard = get_dashboard()
    
    return {
        "app": app,
        "runner": runner,
        "worker_pool": worker_pool,
        "dashboard": dashboard,
    }


# =============================================================================
# 四、前端配置界面设计
# =============================================================================

"""
前端应用编辑页面需要新增的配置项：

1. 存储配置区块
   ┌─────────────────────────────────────┐
   │ 存储配置                             │
   ├─────────────────────────────────────┤
   │ 存储后端: [下拉选择]                 │
   │   - 内存存储 (默认)                  │
   │   - 文件存储                         │
   │   - Redis存储                        │
   │   - 数据库存储                       │
   │                                     │
   │ Redis URL: [输入框] (Redis时显示)   │
   │ 数据库URL: [输入框] (数据库时显示)  │
   └─────────────────────────────────────┘

2. Worker池配置区块
   ┌─────────────────────────────────────┐
   │ Worker进程池                         │
   ├─────────────────────────────────────┤
   │ [x] 启用Worker池                     │
   │ 最小Worker数: [2]                   │
   │ 最大Worker数: [10]                  │
   │ 每Worker最大任务: [10]              │
   │ [x] 自动扩缩容                       │
   │ 负载均衡策略: [下拉选择]             │
   └─────────────────────────────────────┘

3. 子Agent配置区块
   ┌─────────────────────────────────────┐
   │ 子Agent配置                          │
   ├─────────────────────────────────────┤
   │ [+ 添加子Agent]                      │
   │                                     │
   │ ┌─ data_collector ─────────────┐   │
   │ │ 描述: 数据采集Agent           │   │
   │ │ 最大实例数: [20]              │   │
   │ │ 超时时间: [300]秒             │   │
   │ │ [x] 支持交互式                │   │
   │ │ [删除]                        │   │
   │ └───────────────────────────────┘   │
   │                                     │
   │ ┌─ analyzer ───────────────────┐   │
   │ │ 描述: 数据分析Agent           │   │
   │ │ 最大实例数: [10]              │   │
   │ │ [x] 支持交互式                │   │
   │ └───────────────────────────────┘   │
   └─────────────────────────────────────┘

4. 监控配置区块
   ┌─────────────────────────────────────┐
   │ 监控配置                             │
   ├─────────────────────────────────────┤
   │ [x] 启用监控仪表盘                   │
   │ [x] 启用WebSocket实时推送            │
   │ 历史事件保留: [1000]                │
   └─────────────────────────────────────┘
"""


# =============================================================================
# 五、使用示例
# =============================================================================

async def example_usage():
    """完整使用示例"""
    from derisk.agent.core_v2 import (
        AgentApplication,
        AgentApplicationRunner,
        get_dashboard,
        get_interactive_manager,
        create_worker_pool,
    )
    
    # ========== 1. 创建应用 ==========
    
    # 定义主Agent
    class AnalysisMasterAgent:
        def __init__(self):
            self.call_subagent = None
            self.get_subagent_progress = None
        
        async def run(self, goal: str):
            # 调用数据采集子Agent (100个并行任务)
            result = await self.call_subagent(
                "data_collector",
                f"采集数据: {goal}",
                count=100,
                max_concurrent=20,
            )
            
            # 查看进度
            progress = self.get_subagent_progress()
            print(f"采集进度: {progress}")
            
            # 调用分析子Agent
            analysis_result = await self.call_subagent(
                "analyzer",
                f"分析数据: {result['summary']}",
                count=10,
            )
            
            return {
                "success": True,
                "analysis": analysis_result,
            }
    
    # 定义子Agent
    class DataCollectorAgent:
        async def run(self, task: str, context: dict = None):
            # 模拟数据采集
            import asyncio
            await asyncio.sleep(1)
            return f"采集完成: {task}"
    
    class AnalyzerAgent:
        async def run(self, task: str, context: dict = None):
            # 模拟分析
            import asyncio
            await asyncio.sleep(2)
            return f"分析完成: {task}"
    
    # 创建应用配置
    app = AgentApplication(
        app_id="analysis-app",
        name="数据分析应用",
        main_agent_class=AnalysisMasterAgent,
        storage_backend="redis",
        storage_config={"redis_url": "redis://localhost:6379/0"},
    )
    
    # 绑定子Agent
    app.bind_subagent(
        name="data_collector",
        agent_class=DataCollectorAgent,
        description="数据采集Agent",
        max_instances=20,
    )
    
    app.bind_subagent(
        name="analyzer",
        agent_class=AnalyzerAgent,
        description="数据分析Agent",
        max_instances=10,
    )
    
    # ========== 2. 运行应用 ==========
    
    runner = AgentApplicationRunner(app)
    await runner.initialize()
    
    # 运行任务
    result = await runner.run(goal="分析系统日志")
    print(f"结果: {result}")
    
    # ========== 3. 使用监控仪表盘 ==========
    
    dashboard = get_dashboard()
    
    # 查看统计
    stats = await dashboard.get_stats()
    print(f"统计: {stats}")
    
    # 获取仪表盘数据
    dashboard_data = await dashboard.get_dashboard_data()
    print(f"仪表盘数据: {dashboard_data}")
    
    # ========== 4. 使用Worker池 ==========
    
    worker_pool = create_worker_pool(min_workers=2, max_workers=5)
    await worker_pool.start()
    
    # 提交任务
    task_id = await worker_pool.submit_task(
        lambda x: x * 2,
        10,
    )
    
    # 获取结果
    result = await worker_pool.get_result(task_id)
    print(f"Worker结果: {result}")
    
    await worker_pool.stop()
    
    # ========== 5. 使用交互式子Agent ==========
    
    interactive_manager = get_interactive_manager()
    
    # 创建交互式会话
    session = await interactive_manager.create_session(
        subagent_name="analyzer",
        task="深度分析日志",
    )
    
    # 主Agent监听并响应
    async for msg in session.listen():
        if msg.message_type.name == "QUESTION":
            # 子Agent请求帮助
            await session.send_input("请关注ERROR级别")
        elif msg.message_type.name == "RESULT":
            print(f"最终结果: {msg.content}")
            break


# =============================================================================
# 六、API端点集成
# =============================================================================

def setup_api_routes(app):
    """设置API路由"""
    from derisk.agent.core_v2 import create_dashboard_routes
    
    # 添加监控仪表盘路由
    app.include_router(create_dashboard_routes(), prefix="/api/v1")
    
    # 仪表盘端点:
    # GET  /api/v1/monitoring/stats         - 获取统计
    # GET  /api/v1/monitoring/dashboard     - 获取仪表盘数据
    # GET  /api/v1/monitoring/tasks         - 获取任务列表
    # GET  /api/v1/monitoring/workers       - 获取Worker列表
    # GET  /api/v1/monitoring/alerts        - 获取告警
    # WS   /api/v1/monitoring/ws            - WebSocket实时事件


# =============================================================================
# 七、前端调用示例
# =============================================================================

"""
// JavaScript/TypeScript 前端调用

// 获取仪表盘数据
const response = await fetch('/api/v1/monitoring/dashboard');
const data = await response.json();

// WebSocket实时监听
const ws = new WebSocket('ws://localhost:8000/api/v1/monitoring/ws');
ws.onmessage = (event) => {
    const eventData = JSON.parse(event.data);
    console.log('Event:', eventData);
    
    // 更新UI
    updateDashboard(eventData);
};

// 更新任务进度
async function updateTaskProgress(taskId, progress) {
    const response = await fetch(`/api/v1/monitoring/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ progress }),
    });
    return response.json();
}
"""


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())