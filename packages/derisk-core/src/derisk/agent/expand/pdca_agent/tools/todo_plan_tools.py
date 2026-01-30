"""
优化后的系统工具定义
核心改进：简化为3个核心工具，清晰的职责划分
"""
import json
import logging
from typing import List, Dict, Any

from derisk.agent.core.system_tool_registry import system_tool
from derisk.agent.expand.pdca_agent.plan_manager import AsyncKanbanManager, create_kanban_manager

logger = logging.getLogger(__name__)


# ==================== 工具1：创建看板 ====================

@system_tool(
    name="create_kanban",
    concurrency="exclusive",
    description="""
    创建看板并规划所有阶段。

    **调用时机**：任务开始时，看板为空。

    **核心要求**：
    1. 从最终交付倒推，设计2-4个高层级阶段
    2. 每个阶段必须有明确的deliverable_type和deliverable_schema
    3. 使用JSON Schema标准格式定义schema
    4. 第一个阶段会自动进入working状态

    **规划原则**：
    - 第一阶段：信息收集、现状调研、需求分析
    - 中间阶段：数据处理、方案设计、原型开发
    - 最后阶段：整合报告、最终交付、验证测试
    """,
    input_schema={
        "type": "object",
        "properties": {
            "mission": {
                "type": "string",
                "description": "用户的原始任务描述，清晰说明要解决的问题或达成的目标"
            },
            "stages": {
                "type": "array",
                "description": "阶段列表，每个阶段代表一个高层级的工作单元",
                "items": {
                    "type": "object",
                    "properties": {
                        "stage_id": {
                            "type": "string",
                            "description": "阶段的唯一标识符，建议格式：s1_xxx, s2_xxx（如 s1_research, s2_analysis）"
                        },
                        "description": {
                            "type": "string",
                            "description": "阶段的详细描述，说明该阶段的目标和范围"
                        },
                        "deliverable_type": {
                            "type": "string",
                            "description": "交付物类型，如：market_data, analysis_report, design_doc, code_package, final_report等"
                        },
                        "deliverable_schema": {
                            "type": "object",
                            "description": "交付物的JSON Schema定义，必须包含type、properties、required字段"
                        },
                        "depends_on": {
                            "type": "array",
                            "description": "依赖的前置阶段ID列表（可选）",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["stage_id", "description", "deliverable_type", "deliverable_schema"]
                }
            }
        },
        "required": ["mission", "stages"]
    }
)
async def create_kanban(pm: AsyncKanbanManager, mission: str, stages: List[Dict]) -> str:
    """
    创建看板

    Args:
        pm: KanbanManager实例（由框架注入）
        mission: 任务描述
        stages: 阶段规格列表

    Returns:
        JSON格式的操作结果
    """
    logger.info(f"create_kanban: mission={mission}, stages_count={len(stages)}")

    result = await pm.create_kanban(mission, stages)

    # 返回JSON字符串
    import json
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================== 工具2：提交交付物 ====================

@system_tool(
    name="submit_deliverable",
    concurrency="exclusive",
    description="""
    提交当前阶段的交付物，并推进到下一阶段。

    **调用时机**：当前阶段的工作完成，已收集到足够信息来构造完整的交付物。

    **提交要求**：
    1. deliverable必须严格符合预定义的deliverable_schema
    2. 包含所有required字段
    3. 数据类型正确（string、array、object等）
    4. 内容完整、自包含，后续阶段能够独立使用

    **reflection要求**：
    - 说明完成了哪些工作（如"收集了5个来源的数据"）
    - 评估交付物的质量（如"覆盖了3个主要竞争对手"）
    - 指出可能的局限性（如"缺少欧洲市场的详细数据"）

    **注意**：
    - 提交后会自动推进到下一阶段
    - 如果是最后一个阶段，提交后应调用terminate工具
    """,
    input_schema={
        "type": "object",
        "properties": {
            "stage_id": {
                "type": "string",
                "description": "当前阶段的ID（必须是正在working的阶段）"
            },
            "deliverable": {
                "type": "object",
                "description": "交付物数据，必须符合该阶段预定义的deliverable_schema"
            },
            "reflection": {
                "type": "string",
                "description": "对本阶段工作的自我评估，包括完成情况、质量评价、局限性说明"
            }
        },
        "required": ["stage_id", "deliverable", "reflection"]
    }
)
async def submit_deliverable(
    pm: AsyncKanbanManager,
    stage_id: str,
    deliverable: Dict[str, Any],
    reflection: str
) -> str:
    """
    提交交付物

    Args:
        pm: KanbanManager实例（由框架注入）
        stage_id: 阶段ID
        deliverable: 交付物数据
        reflection: 自我评估

    Returns:
        JSON格式的操作结果
    """
    logger.info(f"submit_deliverable: stage_id={stage_id}")

    result = await pm.submit_deliverable(stage_id, deliverable, reflection)

    # 记录工作日志
    if result["status"] == "success":
        await pm.record_work("submit_deliverable", f"Completed stage {stage_id}")

    # 返回JSON字符串
    import json
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================== 工具3：读取交付物 ====================

@system_tool(
    name="read_deliverable",
    description="""
    读取指定阶段的交付物内容。

    **调用时机**：当前阶段需要使用前置阶段的成果时。

    **使用场景**：
    - 在分析阶段读取信息收集阶段的数据
    - 在报告生成阶段读取所有前置阶段的交付物
    - 验证前置阶段的输出是否满足当前需求

    **注意**：
    - 只能读取已完成（completed）阶段的交付物
    - 返回完整的交付物内容（JSON格式）
    - 包含元数据（完成时间、文件路径、reflection等）
    """,
    input_schema={
        "type": "object",
        "properties": {
            "stage_id": {
                "type": "string",
                "description": "要读取的阶段ID（必须是已完成的阶段）"
            }
        },
        "required": ["stage_id"]
    }
)
async def read_deliverable(pm: AsyncKanbanManager, stage_id: str) -> str:
    """
    读取交付物

    Args:
        pm: KanbanManager实例（由框架注入）
        stage_id: 阶段ID

    Returns:
        JSON格式的交付物内容
    """
    logger.info(f"read_deliverable: stage_id={stage_id}")

    result = await pm.read_deliverable(stage_id)

    # 记录工作日志
    if result["status"] == "success":
        await pm.record_work("read_deliverable", f"Read deliverable from {stage_id}")

    return json.dumps(result, indent=2, ensure_ascii=False)





# ==================== 工具注册表 ====================

PDCA_SYSTEM_TOOLS = {
    "create_kanban": create_kanban,
    "submit_deliverable": submit_deliverable,
    "read_deliverable": read_deliverable,
}


def get_tool_schemas() -> List[Dict]:
    """
    获取所有工具的Schema定义
    用于生成Prompt中的工具列表
    """
    schemas = []
    for tool_func in PDCA_SYSTEM_TOOLS.values():
        if hasattr(tool_func, '_tool_schema'):
            schemas.append({
                "name": tool_func._tool_name,
                "description": tool_func._tool_description,
                "input_schema": tool_func._tool_schema
            })
    return schemas


def format_tools_for_prompt() -> str:
    """
    格式化工具列表为XML格式（用于Prompt注入）
    """
    schemas = get_tool_schemas()
    lines = []

    for schema in schemas:
        lines.append(f"<tool name=\"{schema['name']}\">")
        lines.append(f"  <description>{schema['description']}</description>")
        lines.append(f"  <input_schema>")

        import json
        schema_json = json.dumps(schema['input_schema'], indent=4)
        for line in schema_json.split('\n'):
            lines.append(f"    {line}")

        lines.append(f"  </input_schema>")
        lines.append(f"</tool>")
        lines.append("")

    return "\n".join(lines)


# ==================== 使用示例 ====================

async def example_usage():
    """
    工具使用示例
    """
    # 1. 创建KanbanManager

    km = await create_kanban_manager("agent_001", "session_001")

    # 2. 创建看板
    result = await create_kanban(
        km=km,
        mission="分析2024年AI芯片市场竞争格局",
        stages=[
            {
                "stage_id": "s1_research",
                "description": "收集AI芯片市场的关键数据",
                "deliverable_type": "market_data",
                "deliverable_schema": {
                    "type": "object",
                    "properties": {
                        "market_size": {"type": "object"},
                        "key_players": {"type": "array"},
                        "sources": {"type": "array"}
                    },
                    "required": ["market_size", "key_players", "sources"]
                }
            },
            {
                "stage_id": "s2_report",
                "description": "生成最终分析报告",
                "deliverable_type": "final_report",
                "deliverable_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "analysis": {"type": "string"}
                    },
                    "required": ["summary", "analysis"]
                },
                "depends_on": ["s1_research"]
            }
        ]
    )
    print("Create Kanban Result:", result)

    # 3. 提交第一个阶段的交付物
    result = await submit_deliverable(
        km=km,
        stage_id="s1_research",
        deliverable={
            "market_size": {"global_2024": "65B USD"},
            "key_players": [
                {"name": "NVIDIA", "share": "80%"},
                {"name": "AMD", "share": "10%"}
            ],
            "sources": ["https://example.com/report"]
        },
        reflection="已完成2个主要厂商的数据收集"
    )
    print("Submit Deliverable Result:", result)

    # 4. 读取前置交付物
    result = await read_deliverable(km=km, stage_id="s1_research")
    print("Read Deliverable Result:", result)

    # 5. 提交最后阶段并终止
    result = await submit_deliverable(
        km=km,
        stage_id="s2_report",
        deliverable={
            "summary": "AI芯片市场由NVIDIA主导...",
            "analysis": "详细分析..."
        },
        reflection="已完成最终报告"
    )
    print("Final Submit Result:", result)

    # 6. 终止任务
    # result = await terminate(
    #     km=km,
    #     output="## AI芯片市场分析\n\n核心发现：...\n\n详细报告见：/workspace/deliverables/s2_report.json"
    # )
    # print("Terminate Result:", result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
