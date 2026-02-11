# AgentFileSystem V3 - FileStorageClient 集成文档

## 概述

AgentFileSystem V3 版本集成了 FileStorageClient（通过 FileServe），实现了统一的文件存储接口。支持多种存储后端（本地、OSS、分布式），并根据 FileServe 配置自动选择合适的存储方式。

## 核心特性

1. **统一存储接口**: 通过 FileStorageClient 统一接入各种存储后端
2. **自动存储切换**: 根据 FileServe 配置自动选择存储方式
3. **URL 代理**: 支持通过文件服务代理访问文件
4. **向后兼容**: 保留 OSS 客户端支持（兼容模式）
5. **优先级策略**: FileStorageClient > OSS 客户端 > 本地存储

## 存储优先级

AgentFileSystem V3 按照以下优先级选择存储方式：

1. **FileStorageClient**（推荐）
   - 如果配置了 FileStorageClient，优先使用
   - 支持所有 FileServe 配置的存储后端
   - URL 通过文件服务代理或直链访问

2. **OSS 客户端**（兼容模式）
   - 如果提供了 OSS 客户端但未提供 FileStorageClient
   - 使用原有的 OSS 上传/下载逻辑
   - 与 V1/V2 版本行为一致

3. **本地存储**（回退）
   - 如果未提供任何客户端
   - 文件保存在本地文件系统
   - 适用于开发和测试

## 使用方式

### 方式 1: 使用 FileStorageClient（推荐）

```python
from derisk.core.interface.file import FileStorageClient
from derisk.agent.expand.pdca_agent.agent_file_system_v3 import AgentFileSystem

# 获取 FileStorageClient 实例
file_storage_client = FileStorageClient.get_instance(system_app)

# 创建 AgentFileSystem
afs = AgentFileSystem(
    conv_id="session_001",
    session_id="session_001",
    file_storage_client=file_storage_client,  # 传入 FileStorageClient
    bucket="agent_files",  # 可选，默认为 "agent_files"
)

# 保存文件
metadata = await afs.save_file(
    file_key="my_file",
    data="文件内容",
    file_type=FileType.TEMP,
    extension="txt",
)

# metadata.preview_url 和 metadata.download_url 会自动生成
print(f"Preview URL: {metadata.preview_url}")
print(f"Download URL: {metadata.download_url}")
```

### 方式 2: 使用 OSS 客户端（兼容模式）

```python
from derisk.agent.expand.pdca_agent.agent_file_system_v3 import AgentFileSystem

# 创建 OSS 客户端
oss_client = YourOSSClient(...)

# 创建 AgentFileSystem
afs = AgentFileSystem(
    conv_id="session_001",
    session_id="session_001",
    oss_client=oss_client,  # 传入 OSS 客户端
)

# 使用方式与之前相同
metadata = await afs.save_file(
    file_key="my_file",
    data="文件内容",
    file_type=FileType.TEMP,
)
```

### 方式 3: 仅本地存储（最简模式）

```python
from derisk.agent.expand.pdca_agent.agent_file_system_v3 import AgentFileSystem

# 创建 AgentFileSystem（不传入任何客户端）
afs = AgentFileSystem(
    conv_id="session_001",
    session_id="session_001",
)

# 文件将保存在本地文件系统
metadata = await afs.save_file(
    file_key="my_file",
    data="文件内容",
    file_type=FileType.TEMP,
)
```

## 与 FileServe 集成

### FileServe 配置为本地存储

```yaml
# 配置示例
derisk:
  serve:
    file:
      backends: []
      # 未配置后端时，使用默认的 SimpleDistributedStorage（本地）
```

**结果：**
- AgentFileSystem 通过 FileStorageClient 保存文件到本地
- URL 生成格式：`http://{host}:{port}/api/v2/serve/file/files/{bucket}/{file_id}`
- 通过文件服务代理访问文件

### FileServe 配置为 OSS

```yaml
# 配置示例
derisk:
  serve:
    file:
      backends:
        - type: oss
          endpoint: "https://oss-cn-hangzhou.aliyuncs.com"
          region: "cn-hangzhou"
          access_key_id: "your-access-key"
          access_key_secret: "your-secret"
          fixed_bucket: "my-bucket"
```

**结果：**
- AgentFileSystem 通过 FileStorageClient 上传文件到 OSS
- URL 生成：
  - 如果存储后端支持公开 URL：返回 OSS 直链
  - 否则：通过文件服务代理访问

## 在 ReactMasterAgent 中使用

ReactMasterAgent 已自动支持 AgentFileSystem V3：

```python
# ReactMasterAgent 会自动检测并使用 FileStorageClient
agent = ReActMasterAgent(...)

# Agent 内部会自动初始化 AgentFileSystem
# 优先使用 V3（如果 FileStorageClient 可用）
# 否则回退到 V1
```

ReactMasterAgent 的 `_ensure_agent_file_system` 方法会自动：
1. 尝试从 `system_app` 获取 `FileStorageClient`
2. 优先初始化 V3 版本的 AgentFileSystem
3. 如果失败，回退到 V1 版本

## 在截断器中使用

```python
from derisk.agent.expand.react_master_agent.truncation import create_truncator_with_fs

# 使用 FileStorageClient
truncator = await create_truncator_with_fs(
    conv_id="session_001",
    file_storage_client=file_storage_client,  # 新增参数
)

# 或使用 OSS 客户端（兼容）
truncator = await create_truncator_with_fs(
    conv_id="session_001",
    oss_client=oss_client,
)
```

## API 参考

### 新增 API

#### `get_storage_type() -> str`

获取当前使用的存储类型。

**返回:**
- `"file_storage_client"` - 使用 FileStorageClient
- `"oss"` - 使用 OSS 客户端
- `"local"` - 使用本地存储

```python
storage_type = afs.get_storage_type()
print(f"Current storage: {storage_type}")
```

#### `get_file_public_url(file_key: str, expire: int = 3600) -> Optional[str]`

获取文件的公开 URL。

**参数:**
- `file_key`: 文件 key
- `expire`: URL 有效期（秒）

**返回:**
- 公开 URL，如果不支持则返回 None

```python
url = await afs.get_file_public_url("my_file", expire=7200)
```

### 向后兼容的 API

所有 V1/V2 版本的 API 在 V3 中保持不变：

- `save_file(...)` - 保存文件
- `read_file(file_key)` - 读取文件
- `delete_file(file_key)` - 删除文件
- `get_file_info(file_key)` - 获取文件信息
- `list_files(...)` - 列出文件
- `save_conclusion(...)` - 保存结论文件
- `save_tool_output(...)` - 保存工具输出
- `sync_workspace()` - 同步工作区
- `push_conclusion_files()` - 推送结论文件
- `collect_delivery_files()` - 收集交付文件

## 迁移指南

### 从 V1/V2 迁移到 V3

**原有代码（V1）:**
```python
from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

afs = AgentFileSystem(
    conv_id="session_001",
    gpts_memory=gpts_memory,
    oss_client=oss_client,  # 可选
)
```

**迁移到 V3（使用 FileStorageClient）:**
```python
from derisk.agent.expand.pdca_agent.agent_file_system_v3 import AgentFileSystem
from derisk.core.interface.file import FileStorageClient

file_storage_client = FileStorageClient.get_instance(system_app)

afs = AgentFileSystem(
    conv_id="session_001",
    metadata_storage=gpts_memory,  # 参数名改变
    file_storage_client=file_storage_client,  # 使用 FileStorageClient
)
```

**或者（保持 OSS 兼容）:**
```python
from derisk.agent.expand.pdca_agent.agent_file_system_v3 import AgentFileSystem

afs = AgentFileSystem(
    conv_id="session_001",
    metadata_storage=gpts_memory,
    oss_client=oss_client,  # 继续使用 OSS 客户端
)
```

## 配置示例

### 完整配置

```python
# 方式 1: 完整配置（FileStorageClient + GptsMemory）
afs = AgentFileSystem(
    conv_id="session_001",
    session_id="session_001",
    goal_id="goal_001",
    base_working_dir="/path/to/storage",
    sandbox=sandbox_instance,  # 可选
    metadata_storage=gpts_memory,  # FileMetadataStorage 接口
    file_storage_client=file_storage_client,  # FileStorageClient
    bucket="agent_files",  # bucket 名称
)

# 方式 2: 最小配置（仅本地存储）
afs = AgentFileSystem(
    conv_id="session_001",
)
```

## 故障排除

### 问题：FileStorageClient 不可用

**症状:** 日志显示 `Failed to initialize AgentFileSystem V3，trying V1`

**解决方案:**
1. 确保 FileServe 已正确注册到 SystemApp
2. 检查配置是否正确
3. 查看 FileStorageClient 初始化日志

### 问题：URL 生成失败

**症状:** `preview_url` 或 `download_url` 为 None

**解决方案:**
1. 检查存储后端是否支持公开 URL
2. 对于本地存储，确保文件服务正在运行
3. 检查日志中的详细错误信息

### 问题：文件保存成功但无法读取

**症状:** `read_file` 返回 None

**解决方案:**
1. 检查文件 URI 是否正确
2. 确认存储后端可访问
3. 检查文件是否被其他进程删除

## 性能优化建议

1. **使用 FileStorageClient**: 相比直接使用 OSS 客户端，FileStorageClient 提供了更好的缓存和连接池管理
2. **合理设置 bucket**: 根据业务需求划分不同的 bucket
3. **使用本地缓存**: V3 版本会自动在本地缓存文件元数据，减少重复查询

## 总结

AgentFileSystem V3 通过集成 FileStorageClient，实现了与 FileServe 的完全对接。优势包括：

1. **配置集中**: 文件存储配置集中在 FileServe
2. **统一接口**: 一套代码支持多种存储后端
3. **自动切换**: 根据配置自动选择最佳存储方式
4. **URL 代理**: 支持通过文件服务统一代理文件访问
5. **向后兼容**: 保留旧版 API，迁移成本低
