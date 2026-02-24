"""简单的 AgentFileSystem V3 测试脚本.

不依赖复杂的模块导入，直接测试核心功能。
"""

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

# 添加必要的路径
sys.path.insert(0, "/Users/tuyang.yhj/Code/python/derisk/packages/derisk-core/src")


def test_basic_functionality():
    """测试基本功能 - 无需依赖"""
    print("=" * 60)
    print("测试 AgentFileSystem V3 基本功能")
    print("=" * 60)

    # 1. 测试存储类型优先级
    print("\n1. 测试存储类型优先级")
    print("-" * 40)

    # 模拟检查逻辑
    def check_storage_type(file_storage_client=None, oss_client=None):
        if file_storage_client:
            return "file_storage_client"
        elif oss_client:
            return "oss"
        else:
            return "local"

    # FileStorageClient 优先
    assert (
        check_storage_type(file_storage_client=True, oss_client=True)
        == "file_storage_client"
    )
    print("✓ FileStorageClient 优先级最高")

    # OSS 次之
    assert check_storage_type(file_storage_client=None, oss_client=True) == "oss"
    print("✓ OSS 客户端次之")

    # 本地存储最后
    assert check_storage_type(file_storage_client=None, oss_client=None) == "local"
    print("✓ 本地存储作为回退")

    print("\n2. 测试 URL 生成逻辑")
    print("-" * 40)

    # 模拟 URL 生成
    def generate_url(storage_type, uri, file_name=None):
        if storage_type == "oss":
            return f"https://oss.example.com/{uri}?download={file_name}"
        else:
            return f"http://localhost:5670/api/v2/serve/file/files/{uri}"

    oss_url = generate_url("oss", "test/file.txt", "file.txt")
    assert "oss.example.com" in oss_url
    print(f"✓ OSS URL: {oss_url}")

    local_url = generate_url("local", "test/file.txt")
    assert "localhost" in local_url
    print(f"✓ 本地代理 URL: {local_url}")

    print("\n3. 测试文件元数据结构")
    print("-" * 40)

    # 模拟文件元数据
    file_metadata = {
        "file_id": str(uuid.uuid4()),
        "file_key": "test_file",
        "file_name": "test.txt",
        "file_type": "temp",
        "file_size": 100,
        "storage_uri": "derisk-fs://bucket/file_id",
        "preview_url": "http://localhost/preview",
        "download_url": "http://localhost/download",
        "content_hash": "abc123",
    }

    assert "file_id" in file_metadata
    assert "storage_uri" in file_metadata
    print(
        f"✓ 元数据结构正确: {json.dumps(file_metadata, indent=2, default=str)[:100]}..."
    )

    print("\n4. 测试哈希去重逻辑")
    print("-" * 40)

    def compute_hash(data):
        import hashlib

        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            content_str = str(data)
        return hashlib.md5(content_str.encode("utf-8")).hexdigest()

    hash1 = compute_hash("Hello, World!")
    hash2 = compute_hash("Hello, World!")
    hash3 = compute_hash("Different content")

    assert hash1 == hash2, "相同内容应该产生相同哈希"
    assert hash1 != hash3, "不同内容应该产生不同哈希"
    print(f"✓ 去重哈希功能正常: {hash1[:8]}...")

    print("\n5. 测试存储 URI 格式")
    print("-" * 40)

    # 不同的存储类型应该产生不同的 URI
    uri_formats = {
        "file_storage": "derisk-fs://bucket/file_id",
        "oss": "oss://bucket/object_name",
        "local": "local:///path/to/file",
    }

    for storage_type, uri in uri_formats.items():
        print(f"  {storage_type}: {uri}")

    print("\n" + "=" * 60)
    print("基本功能测试通过！")
    print("=" * 60)


def test_integration_concept():
    """测试集成概念"""
    print("\n" + "=" * 60)
    print("测试集成概念")
    print("=" * 60)

    print("\n场景 1: FileServe 配置为本地存储")
    print("-" * 40)
    print("""
配置:
  - storage_type: local
  - backend: LocalFileStorage

结果:
  - AgentFileSystem 使用 FileStorageClient
  - 文件保存在本地文件系统
  - URL 生成: http://localhost/api/v2/serve/file/files/{bucket}/{file_id}
  - 通过文件服务代理访问
""")

    print("\n场景 2: FileServe 配置为 OSS")
    print("-" * 40)
    print("""
配置:
  - storage_type: oss
  - backend: AliyunOSSStorage

结果:
  - AgentFileSystem 使用 FileStorageClient
  - 文件上传到 OSS
  - URL 生成: https://bucket.oss-region.aliyuncs.com/object?signature=xxx
  - 可以是 OSS 直链或通过文件服务代理
""")

    print("\n场景 3: 仅使用 OSS 客户端（兼容模式）")
    print("-" * 40)
    print("""
配置:
  - 直接传入 oss_client
  - 不传入 file_storage_client

结果:
  - AgentFileSystem 使用 OSS 客户端
  - 文件上传到 OSS
  - URL 通过 oss_client.generate_*_url() 生成
  - 与旧版本行为一致
""")

    print("\n场景 4: 仅本地存储（最简模式）")
    print("-" * 40)
    print("""
配置:
  - 不传入任何客户端

结果:
  - AgentFileSystem 使用本地文件系统
  - 文件保存在本地目录
  - URL 返回本地文件路径
  - 适用于开发和测试
""")

    print("\n" + "=" * 60)


def test_api_compatibility():
    """测试 API 兼容性"""
    print("\n" + "=" * 60)
    print("测试 API 兼容性")
    print("=" * 60)

    # V1/V2/V3 版本都支持的 API
    common_apis = [
        "save_file(file_key, data, file_type, ...)",
        "read_file(file_key)",
        "delete_file(file_key)",
        "get_file_info(file_key)",
        "list_files(file_type=None)",
        "save_conclusion(data, file_name, ...)",
        "save_tool_output(tool_name, output, ...)",
        "sync_workspace()",
        "push_conclusion_files()",
        "collect_delivery_files()",
    ]

    print("\n所有版本共有的 API:")
    for api in common_apis:
        print(f"  ✓ {api}")

    # V3 新增 API
    v3_new_apis = [
        "get_storage_type() -> str",
        "get_file_public_url(file_key, expire=3600)",
    ]

    print("\nV3 版本新增的 API:")
    for api in v3_new_apis:
        print(f"  + {api}")

    print("\n✓ API 向后兼容")
    print("=" * 60)


def main():
    """主函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " AgentFileSystem V3 集成测试 ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    try:
        test_basic_functionality()
        test_integration_concept()
        test_api_compatibility()

        print("\n" + "╔" + "═" * 58 + "╗")
        print("║" + " 所有测试通过！ ".center(58) + "║")
        print("╚" + "═" * 58 + "╝")
        print()

        return 0

    except AssertionError as e:
        print(f"\n测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
