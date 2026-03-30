"""测试文件上传修复的完整链路"""

import asyncio
import sys
import os

sys.path.insert(0, "packages/derisk-core/src")
sys.path.insert(0, "packages/derisk-serve/src")
sys.path.insert(0, "packages/derisk-app/src")
sys.path.insert(0, "packages/derisk-ext/src")

from unittest.mock import Mock, AsyncMock, MagicMock
import json

print("=" * 80)
print("测试文件上传修复的完整链路")
print("=" * 80)

# 测试 1: 验证 GptsMemory 有 name 属性
print("\n【测试 1】验证 GptsMemory 有 name 属性")
try:
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

    assert hasattr(GptsMemory, "name"), "GptsMemory 缺少 name 属性"
    assert GptsMemory.name == "derisk_gpts_memory", (
        f"GptsMemory.name 应为 'derisk_gpts_memory'，实际为 '{GptsMemory.name}'"
    )
    print("✅ GptsMemory.name = 'derisk_gpts_memory'")
except Exception as e:
    print(f"❌ 测试失败: {e}")

# 测试 2: 验证 SimpleDistributedStorage 有 get_public_url 方法
print("\n【测试 2】验证 SimpleDistributedStorage 有 get_public_url 方法")
try:
    from derisk.core.interface.file import SimpleDistributedStorage

    assert hasattr(SimpleDistributedStorage, "get_public_url"), (
        "SimpleDistributedStorage 缺少 get_public_url 方法"
    )
    print("✅ SimpleDistributedStorage 有 get_public_url 方法")

    # 测试方法实现
    storage = SimpleDistributedStorage(
        node_address="localhost:8080", local_storage_path="/tmp/test_storage"
    )

    # 创建模拟的 FileMetadata
    from derisk.core.interface.file import FileMetadata
    from datetime import datetime

    metadata = FileMetadata(
        file_id="test-file-id",
        bucket="derisk_app_file",
        file_name="skill_analysis_report.md",
        file_size=1024,
        storage_type="distributed",
        storage_path="distributed://localhost:8080/derisk_app_file/test-file-id",
        uri="derisk-fs://distributed/derisk_app_file/test-file-id",
        custom_metadata={"user_name": "001", "conv_uid": "test-conv-id"},
        file_hash="test-hash",
    )

    url = storage.get_public_url(metadata)
    print(f"生成的 URL: {url}")
    assert url.startswith("http://"), f"URL 应以 'http://' 开头，实际为 '{url}'"
    assert "localhost:8080" in url, f"URL 应包含 node_address，实际为 '{url}'"
    assert "test-file-id" in url, f"URL 应包含 file_id，实际为 '{url}'"
    print("✅ get_public_url 方法正确生成 HTTP URL")
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback

    traceback.print_exc()

# 测试 3: 验证 file_dispatch 支持 OpenAI file_url 格式
print("\n【测试 3】验证 file_dispatch 支持 OpenAI file_url 格式")
try:
    from derisk_serve.agent.utils.file_dispatch import process_uploaded_files
    from derisk.core.interface.file import (
        FileMetadata,
        FileStorageClient,
        FileStorageSystem,
        SimpleDistributedStorage,
    )

    # 创建模拟的 FileStorageClient
    storage = SimpleDistributedStorage(
        node_address="localhost:8080", local_storage_path="/tmp/test_storage"
    )
    storage_system = FileStorageSystem({"distributed": storage})

    # 手动添加 metadata 到 storage_system
    from derisk.core.interface.file import FileMetadataIdentifier

    test_metadata = FileMetadata(
        file_id="d3be97ae-fbad-458e-a1f3-e097e06c3e10",
        bucket="derisk_app_file",
        file_name="skill_analysis_report.md",
        file_size=1024,
        storage_type="distributed",
        storage_path="distributed://localhost:8080/derisk_app_file/d3be97ae-fbad-458e-a1f3-e097e06c3e10",
        uri="derisk-fs://distributed/derisk_app_file/d3be97ae-fbad-458e-a1f3-e097e06c3e10",
        custom_metadata={"user_name": "001", "conv_uid": "test-conv-id"},
        file_hash="test-hash",
    )
    storage_system.metadata_storage.save(test_metadata)

    file_storage_client = FileStorageClient(
        storage_system=storage_system, default_storage_type="distributed"
    )

    # 创建模拟的 sandbox_client
    sandbox_client = Mock()
    sandbox_client.work_dir = "/home/ubuntu"
    sandbox_client.file = AsyncMock()
    sandbox_client.file.create = AsyncMock()

    # 创建模拟的 system_app
    from derisk.component import SystemApp

    system_app = SystemApp()

    # 创建并注册 GptsMemory
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
    from derisk_serve.agent.agents.derisks_memory import (
        MetaDerisksPlansMemory,
        MetaDerisksMessageMemory,
        MetaDerisksFileMetadataStorage,
        MetaDerisksWorkLogStorage,
        MetaDerisksKanbanStorage,
        MetaDerisksTodoStorage,
    )

    gpts_memory = GptsMemory(
        plans_memory=MetaDerisksPlansMemory(),
        message_memory=MetaDerisksMessageMemory(),
        file_metadata_db_storage=MetaDerisksFileMetadataStorage(),
        work_log_db_storage=MetaDerisksWorkLogStorage(),
        kanban_db_storage=MetaDerisksKanbanStorage(),
        todo_db_storage=MetaDerisksTodoStorage(),
    )
    system_app.register_instance(gpts_memory)
    print("✅ GptsMemory 已注册到 system_app")

    # 测试 OpenAI file_url 格式
    file_resources = [
        {
            "type": "file_url",
            "file_url": {
                "url": "derisk-fs://distributed/derisk_app_file/d3be97ae-fbad-458e-a1f3-e097e06c3e10?user_name=001&conv_uid=test-conv-id",
                "preview_url": "derisk-fs://distributed/derisk_app_file/d3be97ae-fbad-458e-a1f3-e097e06c3e10?user_name=001&conv_uid=test-conv-id",
                "file_name": "skill_analysis_report.md",
            },
        }
    ]

    print(f"输入文件资源格式: {json.dumps(file_resources[0], indent=2)}")

    media_contents, file_infos = asyncio.run(
        process_uploaded_files(
            file_resources=file_resources,
            conv_id="test-conv-id",
            sandbox_client=sandbox_client,
            system_app=system_app,
            file_storage_client=file_storage_client,
        )
    )

    print(f"处理结果:")
    print(f"  - media_contents 数量: {len(media_contents)}")
    print(f"  - file_infos 数量: {len(file_infos)}")

    if file_infos:
        file_info = file_infos[0]
        print(f"  - 文件名: {file_info.file_name}")
        print(f"  - 文件路径: {file_info.file_path}")
        print(f"  - sandbox_path: {file_info.sandbox_path}")
        print(f"  - dispatch_type: {file_info.dispatch_type}")

        assert file_info.file_name == "skill_analysis_report.md", (
            f"文件名应为 skill_analysis_report.md，实际为 {file_info.file_name}"
        )
        assert file_info.file_path.startswith("derisk-fs://"), (
            f"file_path 应为 derisk-fs:// URI"
        )

        if sandbox_client.file.create.called:
            print(f"  - sandbox_client.file.create 被调用")
            call_args = sandbox_client.file.create.call_args
            print(
                f"    参数: sandbox_path={call_args[0][0]}, content 长度={len(call_args[0][1]) if call_args[0][1] else 0}"
            )

        if media_contents:
            print(f"  - media_contents 内容:")
            for i, content in enumerate(media_contents):
                if hasattr(content, "text") and hasattr(content, "type"):
                    print(
                        f"    [{i}] type={content.type}, text 前 200 字符={content.text[:200] if content.text else 'None'}"
                    )
                else:
                    print(f"    [{i}] {content}")

        print("✅ OpenAI file_url 格式正确解析和处理")
    else:
        print("❌ 没有生成 file_infos")

except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback

    traceback.print_exc()

# 测试 4: 验证 chat_in_params_to_resource 过滤 FILE_RESOURCES
print("\n【测试 4】验证 chat_in_params_to_resource 过滤 FILE_RESOURCES")
try:
    from derisk_serve.agent.agents.chat.agent_chat import AgentChat
    from derisk.agent.resource.base import FILE_RESOURCES, AgentResource
    from derisk.core.interface.message import ChatInParamValue

    # 创建模拟的 system_app
    system_app = SystemApp()

    # 创建 AgentChat 实例
    agent_chat = AgentChat(system_app)

    # 创建包含 common_file 的 chat_in_params
    chat_in_params = [
        ChatInParamValue(
            param_type="resource",
            sub_type="common_file",
            param_value=json.dumps(
                {
                    "type": "file_url",
                    "file_url": {"url": "derisk-fs://test-uri", "file_name": "test.md"},
                }
            ),
        ),
        ChatInParamValue(
            param_type="resource",
            sub_type="database",
            param_value=json.dumps({"name": "test_db"}),
        ),
    ]

    print(f"输入 chat_in_params: {len(chat_in_params)} 个")
    print(f"  - common_file (应被过滤)")
    print(f"  - database (应保留)")

    # 调用 chat_in_params_to_resource
    dynamic_resources = asyncio.run(
        agent_chat.chat_in_params_to_resource(chat_in_params)
    )

    print(
        f"输出 dynamic_resources: {len(dynamic_resources) if dynamic_resources else 0} 个"
    )

    if dynamic_resources:
        for res in dynamic_resources:
            print(f"  - type={res.type}, name={res.name}")

    # 验证 common_file 被过滤
    assert dynamic_resources is not None, "dynamic_resources 应不为 None"
    assert len(dynamic_resources) == 1, (
        f"应只有 1 个资源（database），实际有 {len(dynamic_resources)} 个"
    )
    assert dynamic_resources[0].type == "database", (
        f"资源类型应为 database，实际为 {dynamic_resources[0].type}"
    )

    print("✅ chat_in_params_to_resource 正确过滤 FILE_RESOURCES")

except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback

    traceback.print_exc()

# 测试 5: 验证 GptsMemory 可通过 system_app.get_component 获取
print("\n【测试 5】验证 GptsMemory 可通过 system_app.get_component 获取")
try:
    from derisk.component import ComponentType

    # 使用之前创建的 system_app
    retrieved_memory = system_app.get_component(ComponentType.GPTS_MEMORY, GptsMemory)

    assert retrieved_memory is not None, "无法获取 GptsMemory"
    assert isinstance(retrieved_memory, GptsMemory), (
        f"获取的类型应为 GptsMemory，实际为 {type(retrieved_memory)}"
    )
    print("✅ GptsMemory 可通过 system_app.get_component 获取")

except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
