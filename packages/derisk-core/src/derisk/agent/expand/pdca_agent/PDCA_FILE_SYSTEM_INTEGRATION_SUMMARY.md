# PDCA Agent 文件系统集成总结

## 概述

PDCA Agent 现在完全集成到统一的文件服务系统中了！我们有以下文件系统实现：

1. **AgentFileSystem** (V1) - 基础实现，直接操作 OSS
2. **AgentFileSystemV2** - 基于 FileMetadataStorage 接口
3. **AgentFileSystemV3** - 集成 FileStorageClient，支持多种存储后端
4. **FileSystem** (PDCA V1) - PDCA Agent 专用，直接操作 OSS
5. **FileSystemV3** (PDCA V3) - PDCA Agent 专用，使用 AgentFileSystemV3

## 集成架构

```
┌────────────────────────────────────────────────────────────────┐
│                        FileServe                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  FileStorageClient                                        │ │
│  │  ├── SimpleDistributedStorage (本地/分布式)              │ │
│  │  ├── AliyunOSSStorage (阿里云 OSS)                       │ │
│  │  └── 其他自定义 StorageBackend                           │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                    AgentFileSystemV3                           │
│  - 集成 FileStorageClient                                      │
│  - 支持多种存储后端                                            │
│  - URL 通过 FileStorageClient.get_public_url() 生成           │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                     FileSystemV3                               │
│  - PDCA Agent 专用                                             │
│  - 包装 AgentFileSystemV3                                      │
│  - 保持与 FileSystem V1 相同的 API                             │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                      PDCAAgent                                 │
│  - _create_file_system() 自动选择版本                          │
│  - FileStorageClient 可用 → FileSystemV3                      │
│  - 否则 → FileSystem V1                                       │
└────────────────────────────────────────────────────────────────┘
```

## 文件清单

### 新创建的文件

1. **`agent_file_system_v3.py`** (982 行)
   - 位置: `packages/derisk-core/src/derisk/agent/expand/pdca_agent/`
   - 功能: 核心 AgentFileSystem V3 实现
   - 特性:
     - 集成 FileStorageClient
     - 支持 FileStorageClient → OSS 客户端 → 本地存储优先级
     - 自动生成预览/下载 URL
     - 通过文件服务代理访问文件

2. **`file_system_v3.py`** (300+ 行)
   - 位置: `packages/derisk-core/src/derisk/agent/expand/pdca_agent/`
   - 功能: PDCA Agent 专用的 FileSystem V3
   - 特性:
     - 保持与 FileSystem V1 完全相同的 API
     - 内部使用 AgentFileSystemV3
     - 新增 get_storage_type(), get_file_url() 等方法

3. **`AGENT_FILE_SYSTEM_V3_INTEGRATION.md`**
   - 完整的集成文档和使用指南

4. **测试文件**
   - `test_agent_file_system_v3.py` - AgentFileSystem V3 完整测试
   - `test_pdca_file_system_v3.py` - PDCA FileSystem V3 测试
   - `test_simple.py` - 快速验证测试

### 修改的文件

1. **`pdca_agent.py`**
   - 导入 FileSystemV3
   - 添加 `_create_file_system()` 方法
   - 优先使用 V3 版本（如果 FileStorageClient 可用）

2. **`truncation.py`**
   - 支持 `file_storage_client` 参数
   - 优先创建 V3 版本的 AgentFileSystem

3. **`react_master_agent.py`**
   - 导入 AgentFileSystemV3
   - `_ensure_agent_file_system()` 优先使用 V3

## 使用方式

### PDCA Agent 自动选择

PDCA Agent 会自动检测并使用最佳的文件系统：

```python
# PDCA Agent 内部自动处理
class PDCAAgent:
    def _create_file_system(self, session_id, goal_id):
        # 1. 尝试获取 FileStorageClient
        file_storage_client = FileStorageClient.get_instance(...)
        
        # 2. 如果可用，使用 V3
        if file_storage_client:
            return FileSystemV3(..., file_storage_client=file_storage_client)
        
        # 3. 否则使用 V1（向后兼容）
        return FileSystem(..., sandbox=sandbox)
```

### 手动使用 FileSystemV3

```python
from derisk.agent.expand.pdca_agent.file_system_v3 import FileSystem as FileSystemV3
from derisk.core.interface.file import FileStorageClient

# 创建 FileSystemV3
file_storage_client = FileStorageClient.get_instance(system_app)
fs = FileSystemV3(
    session_id="session_001",
    goal_id="goal_001",
    file_storage_client=file_storage_client,
)

# 使用（与 V1 相同的 API）
await fs.save_file("my_file", "content")
content = await fs.read_file("my_file")
info = await fs.get_file_info("my_file")

# V3 特有功能
storage_type = fs.get_storage_type()  # "file_storage_client"
url = await fs.get_file_url("my_file", "download")
```

### AsyncKanbanManager 使用

```python
from derisk.agent.expand.pdca_agent.plan_manager import AsyncKanbanManager

# 创建 FileSystem（自动选择版本）
fs = self._create_file_system(session_id, goal_id)

# 传递给 AsyncKanbanManager
pm = AsyncKanbanManager(
    agent_id="agent_001",
    session_id=session_id,
    file_system=fs,  # 可以是 FileSystem 或 FileSystemV3
)
```

## 存储后端支持

### 1. FileStorageClient（推荐）

**配置方式:**
```yaml
# FileServe 配置
derisk:
  serve:
    file:
      backends:
        - type: oss  # 或 local
          ...
```

**特性:**
- 统一配置管理
- 支持多种后端
- 自动 URL 生成
- 通过文件服务代理访问

**URL 格式:**
- OSS: `https://bucket.oss-region.aliyuncs.com/object?signature=xxx`
- 本地: `http://localhost:7777/api/v2/serve/file/files/{bucket}/{file_id}`

### 2. OSS 客户端（兼容模式）

**配置方式:**
```python
oss_client = OSSClient(...)
fs = FileSystem(..., sandbox=sandbox_with_oss)
```

**特性:**
- 直接使用 OSS 客户端
- 与旧版本行为一致
- OSS 直链访问

**URL 格式:**
- `https://bucket.oss-region.aliyuncs.com/object?signature=xxx`

### 3. 本地存储（回退）

**配置方式:**
```python
fs = FileSystem(session_id="xxx", goal_id="xxx")
```

**特性:**
- 无需外部服务
- 适用于开发和测试

**URL 格式:**
- `local:///path/to/file`

## 向后兼容性

### API 兼容

所有 FileSystem V1 的 API 在 V3 中完全兼容：

| API | V1 | V3 | 兼容 |
|-----|-----|-----|------|
| `save_file()` | ✓ | ✓ | ✓ |
| `read_file()` | ✓ | ✓ | ✓ |
| `get_file_info()` | ✓ | ✓ | ✓ |
| `sync_workspace()` | ✓ | ✓ | ✓ |
| `preload_file()` | ✓ | ✓ | ✓ |
| `delete_file()` | - | ✓ | 新增 |
| `list_files()` | - | ✓ | 新增 |
| `get_storage_type()` | - | ✓ | 新增 |
| `get_file_url()` | - | ✓ | 新增 |

### 自动回退

如果 FileStorageClient 不可用，PDCA Agent 会自动回退到 FileSystem V1：

```python
# 场景 1: FileStorageClient 可用
fs = _create_file_system(...)  # 返回 FileSystemV3

# 场景 2: FileStorageClient 不可用
fs = _create_file_system(...)  # 返回 FileSystem V1

# 场景 3: 两者都不可用（理论上不会发生）
fs = _create_file_system(...)  # 返回 FileSystem V1（本地模式）
```

## 测试覆盖

所有测试均已通过：

✅ **AgentFileSystem V3 测试**
- 存储类型优先级
- URL 生成逻辑
- 文件元数据结构
- 哈希去重功能

✅ **PDCA FileSystem V3 测试**
- 存储类型选择逻辑
- API 兼容性
- V3 特有功能
- 集成流程
- URL 生成对比
- 向后兼容性

## 优势总结

1. **配置集中**: 所有存储配置集中在 FileServe，无需在 PDCA Agent 中单独配置
2. **动态切换**: 根据 FileServe 配置自动选择存储后端
3. **统一代理**: 支持通过文件服务统一代理文件访问
4. **向后兼容**: 自动回退机制，确保旧代码正常运行
5. **更好的抽象**: FileStorageClient 提供更好的存储后端抽象

## 迁移建议

### 新代码

直接使用 FileStorageClient：
```python
from derisk.agent.expand.pdca_agent.file_system_v3 import FileSystem
from derisk.core.interface.file import FileStorageClient

file_storage_client = FileStorageClient.get_instance(system_app)
fs = FileSystem(..., file_storage_client=file_storage_client)
```

### 旧代码

无需修改，自动兼容：
```python
# 旧代码继续工作
from derisk.agent.expand.pdca_agent.file_system import FileSystem

fs = FileSystem(...)
# 如果 FileStorageClient 可用，PDCA Agent 会自动使用 V3
```

## 故障排除

### 问题：FileSystemV3 未被使用

**检查点:**
1. FileServe 是否正确配置并启动？
2. FileStorageClient 是否正确注册到 SystemApp？
3. PDCA Agent 的 `agent_context.system_app` 是否正确设置？

**调试:**
```python
# 检查日志
logger.info(f"[PDCA] Using FileSystemV3 with FileStorageClient...")
logger.info(f"[PDCA] Using legacy FileSystem...")
```

### 问题：URL 生成失败

**检查点:**
1. 存储后端是否支持公开 URL？
2. OSS 配置是否正确？
3. 文件服务是否可访问？

**调试:**
```python
storage_type = fs.get_storage_type()
url = await fs.get_file_url("file_key")
print(f"Storage: {storage_type}, URL: {url}")
```

## 结论

PDCA Agent 现在完全集成到统一的文件服务系统中，通过 FileStorageClient 支持多种存储后端，同时保持与旧版本的完全兼容。

所有组件（ReactMasterAgent、PDCAAgent、Truncator）都已更新以支持 FileStorageClient，实现了统一的文件存储管理。
