"""
测试 BAIZE Agent 的变量注入机制
验证 now、now_time、conv_start_time 等时间变量是否正确注入
验证分层组装：身份层 + 资源层 + 控制层
"""
import asyncio
import sys
sys.path.insert(0, "/Users/yanghongjun/code/OpenDerisk/packages/derisk-core/src")

from datetime import datetime
from derisk.agent.core.variable import VariableManager
from derisk.agent.shared.prompt_assembly import (
    PromptAssembler,
    PromptAssemblyConfig,
    ResourceContext,
    ResourceInjector,
)


async def test_prompt_assembler_layers():
    """测试 PromptAssembler 分层组装 - 各层注入验证"""
    print("\n" + "=" * 60)
    print("测试: PromptAssembler 分层组装（身份层 + 资源层 + 控制层）")
    print("=" * 60)

    assembler = PromptAssembler()

    # Layer 1: 用户身份模板（不含时间/资源变量）
    user_identity = """
## 核心身份与使命

你是 `BAIZE`，名为 **主调度Agent**。

你是一名**技术问题解决专家**，擅长通过系统化分析、工具调用和资源调度，解决各类复杂技术问题。
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

    # 不传入 resource_context，测试时间变量注入
    system_prompt = await assembler.assemble_system_prompt(
        user_system_prompt=user_identity,
        resource_context=None,  # 无资源层
        **render_vars,
    )

    print("\n生成的 System Prompt 结构:")
    print("-" * 40)
    # 打印结构摘要
    sections = system_prompt.split("\n\n---\n\n")
    for i, section in enumerate(sections):
        # 显示每个 section 的前 100 字符
        preview = section[:100].replace("\n", " ") + "..."
        print(f"Layer {i+1}: {preview}")
    print("-" * 40)

    # 检查时间变量是否注入到控制层（workflow 模板）
    print("\n时间变量注入检查（控制层 workflow 模板）:")

    # 直接检查 system_prompt 中是否包含时间变量值
    if "当前系统时间：2026-04-15 07:30:00" in system_prompt:
        print("  ✓ now_time 已注入到 workflow 模板")
    else:
        print("  ✗ now_time 未注入")
        # 打印实际内容帮助调试
        if "当前系统时间" in system_prompt:
            # 找到时间行的位置
            idx = system_prompt.find("当前系统时间")
            print(f"    实际内容: {system_prompt[idx:idx+50]}")

    if "对话开始时间：2026-04-15 07:00:00" in system_prompt:
        print("  ✓ conv_start_time 已注入到 workflow 模板")
    else:
        print("  ✗ conv_start_time 未注入")
        if "对话开始时间" in system_prompt:
            idx = system_prompt.find("对话开始时间")
            print(f"    实际内容: {system_prompt[idx:idx+50]}")

    # 检查身份层
    print("\n身份层检查:")
    identity_section = sections[0] if sections else ""

    if "BAIZE" in identity_section and "主调度Agent" in identity_section:
        print("  ✓ 用户身份内容已作为身份层")
    else:
        print("  ✗ 用户身份内容未正确使用")


async def test_resource_injector():
    """测试资源层注入"""
    print("\n" + "=" * 60)
    print("测试: ResourceInjector 资源层注入")
    print("=" * 60)

    # 创建模拟的 ResourceContext（无实际 Agent）
    ctx = ResourceContext(
        agent=None,
        resource_map={},
        sandbox_manager=None,
    )

    injector = ResourceInjector()

    # 测试各资源注入方法
    print("\n资源注入测试:")

    # Sandbox
    sandbox = await injector.inject_sandbox(ctx)
    if sandbox:
        print(f"  ✓ Sandbox: 注入成功（长度={len(sandbox)}）")
    else:
        print("  - Sandbox: 无（sandbox_manager 未配置）")

    # Agents
    agents = await injector.inject_agents(ctx)
    if agents:
        print(f"  ✓ Agents: 注入成功（长度={len(agents)}）")
    else:
        print("  - Agents: 无（无子 Agent）")

    # Knowledge
    knowledge = await injector.inject_knowledge(ctx)
    if knowledge:
        print(f"  ✓ Knowledge: 注入成功（长度={len(knowledge)}）")
    else:
        print("  - Knowledge: 无（无知识库）")

    # Skills
    skills = await injector.inject_skills(ctx)
    if skills:
        print(f"  ✓ Skills: 注入成功（长度={len(skills)}）")
    else:
        print("  - Skills: 无（无技能）")

    # Database
    database = await injector.inject_database(ctx)
    if database:
        print(f"  ✓ Database: 注入成功（长度={len(database)}）")
    else:
        print("  - Database: 无（无数据库）")


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

    system_prompt = await assembler.assemble_system_prompt(
        user_system_prompt="你是 AI 助手。",
        resource_context=None,
        **render_vars,
    )

    # 检查时间变量是否自动生成
    print("\n自动生成时间变量检查:")

    # 当前时间的格式
    today_date = datetime.now().strftime("%Y-%m-%d")
    if today_date in system_prompt:  # 检查日期部分
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
    await test_resource_injector()
    await test_time_variable_fallback()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n总结:")
    print("  1. 用户配置的 system_prompt_template 作为身份层（Layer 1）")
    print("  2. 资源层由 ResourceInjector 动态注入（sandbox/agents/knowledge/skills/database）")
    print("  3. 控制层由系统模板构建（workflow/exceptions/delivery），时间变量在此注入")
    print("  4. 时间变量可由 kwargs 传入或自动生成")


if __name__ == "__main__":
    asyncio.run(main())