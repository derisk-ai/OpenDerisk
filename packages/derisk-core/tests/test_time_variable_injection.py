"""
测试 BAIZE Agent 的变量注入机制
验证 now、now_time、conv_start_time 等时间变量是否正确注入
验证分层组装：身份层 + 控制层

注:资源层(layers 资源/skill/db/knowledge)已迁移到 ResourceFacade,不再由
PromptAssembler.assemble_system_prompt 注入(该方法已移除)。本测试仅覆盖身份层+
控制层渲染与时间变量注入。
"""
import asyncio
import sys
sys.path.insert(0, "/Users/yanghongjun/code/OpenDerisk/packages/derisk-core/src")

from datetime import datetime
from derisk.agent.core.variable import VariableManager
from derisk.agent.shared.prompt_assembly import (
    PromptAssembler,
    PromptAssemblyConfig,
)


# PromptAssembler 已无 assemble_system_prompt;身份层+控制层单独组装拼回等价结构。
SECTION_SEP = "\n\n---\n\n"


async def _assemble_identity_plus_control(assembler, user_identity, **render_vars):
    """组装身份层 + 控制层(对齐旧 assemble_system_prompt 无资源层的结构)。"""
    sections = []
    sections.append(await assembler._assemble_identity(user_identity, **render_vars))
    sections.append(await assembler._assemble_control_flow(**render_vars))
    return SECTION_SEP.join(sections)


async def test_prompt_assembler_layers():
    """测试 PromptAssembler 分层组装 - 身份层 + 控制层注入验证"""
    print("\n" + "=" * 60)
    print("测试: PromptAssembler 分层组装（身份层 + 控制层）")
    print("=" * 60)

    assembler = PromptAssembler()

    # Layer 1: 用户身份模板（不含时间变量）
    user_identity = """
## 核心身份与使命

你是 `BAIZE`，名为 **主调度Agent**。

你是一名**技术问题解决专家**，擅长通过系统化分析、工具调用和资源调度，解决各类技术问题。
"""

    # 模拟 render_vars（包含时间变量，由 generate_bind_variables 提供）
    render_vars = {
        "now": "2026-04-15",
        "now_time": "2026-04-15 07:30:00",
        "conv_start_time": "2026-04-15 07:00:00",
        "user_name": "test_user",
        "user_id": "001",
        "language": "zh",
    }

    system_prompt = await _assemble_identity_plus_control(
        assembler, user_identity, **render_vars
    )

    print("\n生成的 System Prompt 结构:")
    print("-" * 40)
    sections = system_prompt.split(SECTION_SEP)
    for i, section in enumerate(sections):
        preview = section[:100].replace("\n", " ") + "..."
        print(f"Layer {i+1}: {preview}")
    print("-" * 40)

    # 检查时间变量是否注入到控制层（workflow 模板）
    print("\n时间变量注入检查（控制层 workflow 模板）:")
    if "2026-04-15 07:30:00" in system_prompt:
        print("  ✓ now_time 已注入到 workflow 模板")
    else:
        print("  ✗ now_time 未注入")

    if "2026-04-15 07:00:00" in system_prompt:
        print("  ✓ conv_start_time 已注入到 workflow 模板")
    else:
        print("  ✗ conv_start_time 未注入")

    # 检查身份层
    print("\n身份层检查:")
    identity_section = sections[0] if sections else ""
    if "BAIZE" in identity_section and "主调度Agent" in identity_section:
        print("  ✓ 用户身份内容已作为身份层")
    else:
        print("  ✗ 用户身份内容未正确使用")


async def test_time_variable_fallback():
    """测试时间变量自动生成（fallback）"""
    print("\n" + "=" * 60)
    print("测试: 时间变量自动生成（kwargs 中未传入时）")
    print("=" * 60)

    assembler = PromptAssembler()

    # 不传入时间变量
    render_vars = {
        "user_name": "test_user",
        "language": "zh",
    }

    system_prompt = await _assemble_identity_plus_control(
        assembler, "你是 AI 助手。", **render_vars
    )

    # 检查时间变量是否自动生成
    print("\n自动生成时间变量检查:")
    today_date = datetime.now().strftime("%Y-%m-%d")
    if today_date in system_prompt:
        print("  ✓ now_time 自动生成并注入")
    else:
        print("  ✗ now_time 未自动生成")


async def test_variable_manager():
    """测试 VariableManager 变量注册"""
    print("\n" + "=" * 60)
    print("测试: VariableManager 变量注册")
    print("=" * 60)

    vm = VariableManager()

    @vm.register("now", "当前日期")
    def var_now(instance):
        return datetime.now().strftime("%Y-%m-%d")

    @vm.register("now_time", "当前时间")
    def var_now_time(instance):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @vm.register("conv_start_time", "对话开始时间")
    def var_conv_start_time(instance, agent_context=None):
        if agent_context:
            return agent_context.get("conv_start_time", None)
        return None

    all_vars = vm.get_all_variables()
    print(f"\n已注册变量: {list(all_vars.keys())}")

    time_vars = ["now", "now_time", "conv_start_time"]
    for var_name in time_vars:
        if var_name in all_vars:
            print(f"  ✓ {var_name}: 已注册")
        else:
            print(f"  ✗ {var_name}: 未注册")


async def main():
    print("\n" + "=" * 60)
    print("BAIZE Agent 分层组装与时间变量注入测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    await test_variable_manager()
    await test_prompt_assembler_layers()
    await test_time_variable_fallback()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n总结:")
    print("  1. 用户配置的 system_prompt_template 作为身份层（Layer 1）")
    print("  2. 控制层由系统模板构建（workflow/exceptions/delivery），时间变量在此注入")
    print("  3. 时间变量可由 kwargs 传入或自动生成")
    print("  4. 资源层已迁移至 ResourceFacade(RFC-005),不在本测试范围")


if __name__ == "__main__":
    asyncio.run(main())