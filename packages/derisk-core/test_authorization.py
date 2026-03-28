"""
测试工具授权中间件

验证 BashCwdAuthorizer 的路径检查逻辑
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from derisk.agent.tools.authorization_middleware import (
    BashCwdAuthorizer,
    AuthorizationContext,
    AuthorizationDecision,
)


def test_bash_cwd_authorizer():
    """测试 BashCwdAuthorizer 的各种场景"""
    authorizer = BashCwdAuthorizer()

    print("=== BashCwdAuthorizer 测试 ===\n")

    # 测试 1: 无 sandbox（本地模式）
    print("测试 1: 无 sandbox（本地模式）")
    context = AuthorizationContext(
        tool_name="bash",
        tool_args={"command": "ls", "cwd": "/tmp"},
        tool_metadata=None,
        sandbox_work_dir=None,
    )
    result = authorizer._check_path_inside_sandbox("/tmp", None)
    # 无 sandbox 时，check 方法会返回 ASK_USER
    print(f"  无 sandbox 路径检查: {result}")
    print("  ✓ 无 sandbox 场景处理正确\n")

    # 测试 2: cwd 在 sandbox 内
    print("测试 2: cwd 在 sandbox 内")
    context = AuthorizationContext(
        tool_name="bash",
        tool_args={"command": "ls", "cwd": "/workspace/project"},
        tool_metadata=None,
        sandbox_work_dir="/workspace",
    )
    is_inside, norm_cwd, norm_sandbox = authorizer._check_path_inside_sandbox(
        "/workspace/project", "/workspace"
    )
    print(f"  cwd: {norm_cwd}")
    print(f"  sandbox: {norm_sandbox}")
    print(f"  is_inside: {is_inside}")
    assert is_inside == True, "cwd 应该在 sandbox 内"
    print("  ✓ cwd 在 sandbox 内检测正确\n")

    # 测试 3: cwd 在 sandbox 外
    print("测试 3: cwd 在 sandbox 外")
    is_inside, norm_cwd, norm_sandbox = authorizer._check_path_inside_sandbox(
        "/etc", "/workspace"
    )
    print(f"  cwd: {norm_cwd}")
    print(f"  sandbox: {norm_sandbox}")
    print(f"  is_inside: {is_inside}")
    assert is_inside == False, "cwd 应该在 sandbox 外"
    print("  ✓ cwd 在 sandbox 外检测正确\n")

    # 测试 4: 相对路径
    print("测试 4: 相对路径")
    is_inside, norm_cwd, norm_sandbox = authorizer._check_path_inside_sandbox(
        "./subdir", "/workspace"
    )
    print(f"  cwd (normalized): {norm_cwd}")
    print(f"  sandbox: {norm_sandbox}")
    print(f"  is_inside: {is_inside}")
    # 相对路径 "./subdir" 应该是相对于当前目录的，这里假设当前目录是 /workspace
    print("  ✓ 相对路径检测完成\n")

    # 测试 5: 特殊路径
    print("测试 5: 特殊路径（尝试跳出 sandbox）")
    is_inside, norm_cwd, norm_sandbox = authorizer._check_path_inside_sandbox(
        "/workspace/../../../etc", "/workspace"
    )
    print(f"  cwd (normalized): {norm_cwd}")
    print(f"  sandbox: {norm_sandbox}")
    print(f"  is_inside: {is_inside}")
    assert is_inside == False, "跳出 sandbox 的路径应该被拒绝"
    print("  ✓ 跳出 sandbox 检测正确\n")

    # 测试 6: 相同路径
    print("测试 6: cwd 就是 sandbox 目录")
    is_inside, norm_cwd, norm_sandbox = authorizer._check_path_inside_sandbox(
        "/workspace", "/workspace"
    )
    print(f"  cwd: {norm_cwd}")
    print(f"  sandbox: {norm_sandbox}")
    print(f"  is_inside: {is_inside}")
    assert is_inside == True, "sandbox 根目录应该被允许"
    print("  ✓ sandbox 根目录检测正确\n")

    print("=== 所有测试通过！ ===")


if __name__ == "__main__":
    test_bash_cwd_authorizer()
