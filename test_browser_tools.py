#!/usr/bin/env python3
"""
测试 local 模式沙箱上的浏览器工具使用

这个测试模拟 agent 使用浏览器工具的实际场景
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "packages" / "derisk-core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "derisk-ext" / "src"))


async def test_browser_tool_usage():
    """测试浏览器工具的实际使用"""
    from derisk.sandbox.sandbox_client import AutoSandbox
    from derisk.agent.core.sandbox.tools.browser_tool import (
        browser_navigate,
        browser_page_content,
        browser_screenshot,
    )

    print("=" * 60)
    print("测试浏览器工具实际使用")
    print("=" * 60)
    print()

    # 创建沙箱
    print("1. 创建沙箱...")
    sandbox = await AutoSandbox.create(
        user_id="test_user",
        agent="test_agent",
        type="local",
        enable_browser=True,
    )
    print(f"✓ 沙箱创建成功: {sandbox.sandbox_id}\n")

    # 测试 browser_navigate 工具
    print("2. 测试 browser_navigate 工具...")
    try:
        result = await browser_navigate(
            client=sandbox,
            url="https://example.com",
            need_screenshot=True,
            analyze_screenshot=False,
        )
        print(f"✓ browser_navigate 成功")
        print(f"  - success: {result.success}")
        print(f"  - url: {result.url}")
        print(f"  - title: {result.title}")
        print(f"  - screenshot 长度: {len(result.screenshot)} bytes")
        if result.error:
            print(f"  - error: {result.error}")
        print()
    except Exception as e:
        print(f"✗ browser_navigate 失败: {e}")
        print()

    # 测试 browser_page_content 工具
    print("3. 测试 browser_page_content 工具...")
    try:
        result = await browser_page_content(
            client=sandbox, need_screenshot=False, analyze_screenshot=False
        )
        print(f"✓ browser_page_content 成功")
        print(f"  - success: {result.success}")
        print(f"  - url: {result.url}")
        print(f"  - title: {result.title}")
        if result.elements:
            elements_preview = (
                result.elements[:200] if len(result.elements) > 200 else result.elements
            )
            print(f"  - elements (预览): {elements_preview}")
        if result.error:
            print(f"  - error: {result.error}")
        print()
    except Exception as e:
        print(f"✗ browser_page_content 失败: {e}")
        print()

    # 测试 browser_screenshot 工具
    print("4. 测试 browser_screenshot 工具...")
    try:
        result = await browser_screenshot(
            client=sandbox, need_screenshot=True, analyze=False
        )
        print(f"✓ browser_screenshot 成功")
        print(f"  - success: {result.success}")
        print(f"  - screenshot 长度: {len(result.screenshot)} bytes")
        if result.error:
            print(f"  - error: {result.error}")
        print()
    except Exception as e:
        print(f"✗ browser_screenshot 失败: {e}")
        print()

    # 测试导航到另一个页面
    print("5. 测试导航到测试页面...")
    try:
        result = await browser_navigate(
            client=sandbox,
            url="https://httpbin.org/get",
            need_screenshot=True,
            analyze_screenshot=False,
        )
        print(f"✓ 导航到 httpbin 成功")
        print(f"  - success: {result.success}")
        print(f"  - url: {result.url}")
        print(f"  - title: {result.title}")
        print(f"  - screenshot 长度: {len(result.screenshot)} bytes")
        if result.error:
            print(f"  - error: {result.error}")
    except Exception as e:
        print(f"✗ 导航到 httpbin 失败: {e}")

    print()
    print("清理沙箱资源...")
    await sandbox.kill()
    print("✓ 沙箱清理完成")

    print()
    print("=" * 60)
    print("✓ 浏览器工具测试完成")
    print("=" * 60)


async def test_browser_interaction_tools():
    """测试浏览器交互工具（点击、输入等）"""
    from derisk.sandbox.sandbox_client import AutoSandbox
    from derisk.agent.core.sandbox.tools.browser_tool import (
        browser_navigate,
        browser_mouse_wheel,
        browser_get_dropdown_options,
        browser_select_dropdown_option,
    )

    print()
    print("=" * 60)
    print("测试浏览器交互工具")
    print("=" * 60)
    print()

    # 创建沙箱
    print("1. 创建沙箱...")
    sandbox = await AutoSandbox.create(
        user_id="test_user",
        agent="test_agent",
        type="local",
        enable_browser=True,
    )
    print(f"✓ 沙箱创建成功: {sandbox.sandbox_id}\n")

    # 先导航到一个有交互元素的页面
    print("2. 导航到交互测试页面...")
    try:
        result = await browser_navigate(
            client=sandbox,
            url="https://example.com",
            need_screenshot=True,
            analyze_screenshot=False,
        )
        print(f"✓ 导航成功: {result.url}\n")
    except Exception as e:
        print(f"✗ 导航失败: {e}")
        await sandbox.kill()
        return

    # 测试滚动
    print("3. 测试页面滚动...")
    try:
        result = await browser_mouse_wheel(
            client=sandbox, y=500, analyze_screenshot=False
        )
        print(f"✓ 滚动成功")
        print(f"  - success: {result.success}")
        if result.error:
            print(f"  - error: {result.error}")
    except Exception as e:
        print(f"⚠ 滚动失败 (可能没有内容滚动): {e}")

    print()
    print("清理沙箱资源...")
    await sandbox.kill()
    print("✓ 沙箱清理完成")

    print()
    print("=" * 60)
    print("✓ 浏览器交互工具测试完成")
    print("=" * 60)


async def main():
    """主测试流程"""
    print("开始 Local 模式沙箱浏览器工具验证\n")

    try:
        # 测试 1: 基本浏览器工具使用
        await test_browser_tool_usage()

        # 测试 2: 浏览器交互工具
        await test_browser_interaction_tools()

    except Exception as e:
        print(f"测试过程中出现错误: {e}", exc_info=True)

    print("\n✓ 所有测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
