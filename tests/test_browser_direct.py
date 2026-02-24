#!/usr/bin/env python3
"""
测试 local 模式沙箱上的浏览器直接调用

这个测试直接调用浏览器客户端的方法，不涉及 agent 工具系统
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "packages" / "derisk-core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "derisk-ext" / "src"))


async def test_browser_direct_usage():
    """直接测试浏览器客户端方法"""
    from derisk.sandbox.sandbox_client import AutoSandbox

    print("=" * 60)
    print("测试浏览器客户端直接调用")
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

    # 测试浏览器初始化
    print("2. 初始化浏览器...")
    try:
        init_result = await sandbox.browser.browser_init()
        print(f"✓ 浏览器初始化成功")
        print(f"  - 状态: {init_result.get('status')}")
        print(f"  - 消息: {init_result.get('message')}\n")
    except Exception as e:
        print(f"✗ 浏览器初始化失败: {e}\n")
        return

    # 测试导航
    test_url = "https://example.com"
    print(f"3. 导航到 {test_url}...")
    try:
        nav_result = await sandbox.browser.browser_navigate(
            url=test_url, need_screenshot=True
        )
        print(f"✓ 导航成功")
        print(f"  - 状态: {nav_result.get('status')}")
        print(f"  - URL: {nav_result.get('url')}")
        print(f"  - 截图长度: {len(nav_result.get('screenshot', ''))} bytes\n")
    except Exception as e:
        print(f"✗ 导航失败: {e}\n")

    # 测试获取页面内容
    print("4. 获取页面内容...")
    try:
        content_result = await sandbox.browser.page_content(need_screenshot=False)
        print(f"✓ 获取页面内容成功")
        print(f"  - 状态: {content_result.get('status')}")
        print(f"  - URL: {content_result.get('url')}")
        print(f"  - 标题: {content_result.get('title')}")
        content_preview = content_result.get("content", "")[:100]
        print(f"  - 内容预览: {content_preview}...\n")
    except Exception as e:
        print(f"✗ 获取页面内容失败: {e}\n")

    # 测试截图
    print("5. 获取页面截图...")
    try:
        screenshot_result = await sandbox.browser.browser_screenshot(
            need_screenshot=True
        )
        print(f"✓ 截图成功")
        print(f"  - 状态: {screenshot_result.get('status')}")
        print(f"  - 截图长度: {len(screenshot_result.get('screenshot', ''))} bytes\n")
    except Exception as e:
        print(f"✗ 截图失败: {e}\n")

    # 测试获取元素树
    print("6. 获取页面元素树...")
    try:
        tree_result = await sandbox.browser.browser_element_tree(need_screenshot=False)
        print(f"✓ 获取元素树成功")
        print(f"  - 状态: {tree_result.get('status')}")
        tree_data = tree_result.get("tree", {})
        highlight_index = tree_result.get("highlight_index", {})
        print(f"  - 树元素数: {len(tree_data)}")
        print(f"  - 高亮索引数: {len(highlight_index)}\n")
    except Exception as e:
        print(f"✗ 获取元素树失败: {e}\n")

    print("清理沙箱资源...")
    await sandbox.kill()
    print("✓ 沙箱清理完成")

    print()
    print("=" * 60)
    print("✓ 浏览器直接调用测试完成")
    print("=" * 60)


async def test_browser_interactions():
    """测试浏览器交互功能"""
    from derisk.sandbox.sandbox_client import AutoSandbox

    print()
    print("=" * 60)
    print("测试浏览器交互功能")
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

    # 初始化浏览器并导航
    print("2. 初始化浏览器并导航...")
    try:
        await sandbox.browser.browser_init()
        await sandbox.browser.browser_navigate(
            url="https://example.com", need_screenshot=False
        )
        print(f"✓ 浏览器就绪\n")
    except Exception as e:
        print(f"✗ 浏览器初始化失败: {e}\n")
        return

    # 测试滚动
    print("3. 测试页面滚动...")
    try:
        for i, y in enumerate([200, 400, -100]):
            result = await sandbox.browser.browser_mouse_wheel(y=y)
            print(f"  {i + 1}. 滚动 {y}px: {result.get('status')}")
            await asyncio.sleep(0.5)
        print("✓ 滚动测试通过\n")
    except Exception as e:
        print(f"✗ 滚动测试失败: {e}\n")

    # 测试打开新标签页
    print("4. 测试打开新标签页...")
    try:
        new_tab_result = await sandbox.browser.open_tab(
            url="https://httpbin.org/html", need_screenshot=False
        )
        print(f"✓ 新标签页打开成功")
        print(f"  - 状态: {new_tab_result.get('status')}")
        print(f"  - URL: {new_tab_result.get('url')}\n")
    except Exception as e:
        print(f"✗ 开新标签失败: {e}\n")

    print("清理沙箱资源...")
    await sandbox.kill()
    print("✓ 沙箱清理完成")

    print()
    print("=" * 60)
    print("✓ 浏览器交互测试完成")
    print("=" * 60)


async def main():
    """主测试流程"""
    print("开始 Local 模式沙箱浏览器功能验证\n")

    try:
        # 测试 1: 基本浏览器功能
        await test_browser_direct_usage()

        # 测试 2: 浏览器交互功能
        await test_browser_interactions()

    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()

    print("\n✓ 所有测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
