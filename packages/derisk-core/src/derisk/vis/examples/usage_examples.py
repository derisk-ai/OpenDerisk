"""
统一VIS框架使用示例

展示如何使用新的Part系统和响应式状态管理
"""

import asyncio
from derisk.vis import Signal, Effect, batch
from derisk.vis.parts import TextPart, CodePart, ToolUsePart, ThinkingPart, PlanPart
from derisk.vis.unified_converter import UnifiedVisConverter, UnifiedVisManager
from derisk.vis.decorators import vis_component, streaming_part, auto_vis_output


# ═══════════════════════════════════════════════════════════════
# 示例1: 基础Part使用
# ═══════════════════════════════════════════════════════════════

def example_basic_part():
    """基础Part使用示例"""
    
    # 创建文本Part
    text_part = TextPart.create(
        content="Hello, World!",
        format="markdown"
    )
    print(f"Text Part: {text_part.to_vis_dict()}")
    
    # 创建代码Part
    code_part = CodePart.create(
        code="def hello():\n    print('hello')",
        language="python",
        filename="hello.py"
    )
    print(f"Code Part: {code_part.to_vis_dict()}")
    
    # 创建工具使用Part
    tool_part = ToolUsePart.create(
        tool_name="bash",
        tool_args={"command": "ls -la"},
        streaming=False
    ).set_result("file1.txt\nfile2.txt", execution_time=0.5)
    print(f"Tool Part: {tool_part.to_vis_dict()}")


# ═══════════════════════════════════════════════════════════════
# 示例2: 流式Part处理
# ═══════════════════════════════════════════════════════════════

async def example_streaming_part():
    """流式Part处理示例"""
    
    # 创建流式文本Part
    part = TextPart.create(content="", streaming=True)
    
    # 模拟流式输出
    chunks = ["Hello", ", ", "World", "!"]
    for chunk in chunks:
        part = part.append(chunk)
        print(f"Current content: {part.content}")
    
    # 完成
    part = part.complete()
    print(f"Final content: {part.content}")


# ═══════════════════════════════════════════════════════════════
# 示例3: 响应式状态管理
# ═══════════════════════════════════════════════════════════════

def example_reactive():
    """响应式状态管理示例"""
    
    # 创建Signal
    count = Signal(0)
    
    # 创建Effect(自动追踪依赖)
    effect = Effect(lambda: print(f"Count changed to: {count.value}"))
    # 输出: Count changed to: 0
    
    # 更新Signal
    count.value = 1
    # 自动输出: Count changed to: 1
    
    count.value = 2
    # 自动输出: Count changed to: 2
    
    # 批量更新
    with batch():
        count.value = 10
        count.value = 20
        # 不会立即触发
    
    # 退出批量后才触发
    # 输出: Count changed to: 20


# ═══════════════════════════════════════════════════════════════
# 示例4: 使用装饰器
# ═══════════════════════════════════════════════════════════════

@vis_component("d-custom-card")
class CustomCardVis:
    """自定义VIS组件"""
    
    def sync_generate_param(self, **kwargs):
        content = kwargs["content"]
        return {
            "title": content.get("title", ""),
            "body": content.get("body", ""),
            "footer": content.get("footer", "")
        }


@auto_vis_output()
def generate_report(data: str) -> str:
    """自动将输出转为Part"""
    return f"# Report\n\n{data}"


# ═══════════════════════════════════════════════════════════════
# 示例5: 统一VIS转换器
# ═══════════════════════════════════════════════════════════════

async def example_unified_converter():
    """统一VIS转换器示例"""
    
    # 获取转换器实例
    converter = UnifiedVisManager.get_converter()
    
    # 手动添加Part
    text_part = TextPart.create(content="欢迎来到Derisk!")
    converter.add_part_manually(text_part)
    
    code_part = CodePart.create(
        code="print('Hello, Derisk!')",
        language="python"
    )
    converter.add_part_manually(code_part)
    
    # 获取统计信息
    stats = converter.get_statistics()
    print(f"Statistics: {stats}")
    
    # 清空
    converter.clear_parts()


# ═══════════════════════════════════════════════════════════════
# 示例6: 集成Core Agent
# ═══════════════════════════════════════════════════════════════

async def example_core_integration():
    """集成Core Agent示例"""
    
    # 注意: 需要实际的Agent实例
    # from derisk.agent.core.base_agent import ConversableAgent
    # agent = ConversableAgent(...)
    
    # converter = UnifiedVisConverter()
    # converter.register_core_agent(agent)
    
    # Action执行后自动转换为Part
    # await converter._core_bridge.process_action(action, output)
    
    print("Core Agent集成示例 - 需要实际Agent实例")


# ═══════════════════════════════════════════════════════════════
# 示例7: 集成Core_V2 Broadcaster
# ═══════════════════════════════════════════════════════════════

async def example_core_v2_integration():
    """集成Core_V2 Broadcaster示例"""
    
    # 注意: 需要实际的Broadcaster实例
    # from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster
    # broadcaster = ProgressBroadcaster()
    
    # converter = UnifiedVisConverter()
    # converter.register_core_v2_broadcaster(broadcaster)
    
    # 自动订阅事件并转换为Part
    # await broadcaster.thinking("正在思考...")
    # await broadcaster.tool_started("bash", {"command": "ls"})
    
    print("Core_V2 Broadcaster集成示例 - 需要实际Broadcaster实例")


# ═══════════════════════════════════════════════════════════════
# 运行所有示例
# ═══════════════════════════════════════════════════════════════

async def main():
    """运行所有示例"""
    
    print("=" * 60)
    print("示例1: 基础Part使用")
    print("=" * 60)
    example_basic_part()
    
    print("\n" + "=" * 60)
    print("示例2: 流式Part处理")
    print("=" * 60)
    await example_streaming_part()
    
    print("\n" + "=" * 60)
    print("示例3: 响应式状态管理")
    print("=" * 60)
    example_reactive()
    
    print("\n" + "=" * 60)
    print("示例5: 统一VIS转换器")
    print("=" * 60)
    await example_unified_converter()
    
    print("\n" + "=" * 60)
    print("示例6: Core Agent集成")
    print("=" * 60)
    await example_core_integration()
    
    print("\n" + "=" * 60)
    print("示例7: Core_V2 Broadcaster集成")
    print("=" * 60)
    await example_core_v2_integration()


if __name__ == "__main__":
    asyncio.run(main())