# Sandbox 统一使用 FileStorageClient 实现说明

## 背景

之前 Sandbox 和文件服务各自配置 OSS，存在配置重复的问题：
- `[[serves.backends]]` 配置文件服务 OSS
- `[sandbox]` 也配置独立的 OSS

## 解决方案

统一 Sandbox 使用 FileStorageClient，不再单独配置 OSS。参考了内源 derisk 项目的实现。

## 主要修改

### 1. 配置文件修改

**packages/derisk-app/src/derisk_app/config.py**
- 将 SandboxConfigParameters 中的 OSS 配置字段标记为 "Deprecated"
- 添加说明：建议使用 FileStorageClient

**configs/*.toml**
- 注释掉 `[sandbox]` 中的 OSS 配置
- 添加说明：使用统一的 FileStorageClient from serves.backends

### 2. FileClient 基类修改

**packages/derisk-core/src/derisk/sandbox/client/file/client.py**

主要变化：
```python
class FileClient(BaseClient):
    def __init__(
        self,
        sandbox_id: str,
        work_dir: str,
        file_storage_client: Optional["FileStorageClient"] = None,  # 新增
        **kwargs,
    ):
        self._file_storage_client = file_storage_client  # 新增
        self._legacy_oss: Optional[OSSUtils] = None  # 重命名，保留向后兼容
```

关键功能：
- 优先使用 `FileStorageClient` 进行文件操作
- `write_chat_file` 方法优先使用 `FileStorageClient.save_file()`
- 保留 `_legacy_oss` 作为向后兼容

### 3. LocalFileClient 修改

**packages/derisk-ext/src/derisk_ext/sandbox/local/file_client.py**

主要变化：
```python
class LocalFileClient(FileClient):
    def __init__(
        self, 
        sandbox_id: str, 
        work_dir: str, 
        runtime, 
        skill_dir: str = None,
        file_storage_client=None,  # 新增
        **kwargs
    ):
        super().__init__(
            sandbox_id, 
            work_dir, 
            connection_config=None,
            file_storage_client=file_storage_client,  # 传递给父类
            **kwargs
        )
```

`upload_to_oss` 方法：
- 优先使用 `FileStorageClient.save_file()`
- 失败时回退到 legacy OSS

### 4. ImprovedLocalSandbox 修改

**packages/derisk-ext/src/derisk_ext/sandbox/local/improved_provider.py**

主要变化：
```python
class ImprovedLocalSandbox(SandboxBase):
    def __init__(self, **kwargs):
        self._file_storage_client = kwargs.get("file_storage_client")  # 新增
        # ...

    async def _init_clients(self) -> None:
        self._file = LocalFileClient(
            sandbox_id=self.sandbox_id,
            work_dir=work_dir,
            runtime=self._runtime,
            skill_dir=skill_dir,
            file_storage_client=self._file_storage_client,  # 传递
        )
```

### 5. SandboxManager 修改

**packages/derisk-core/src/derisk/agent/core/sandbox_manager.py**

新增方法：
```python
def _get_file_storage_client(self):
    """从系统应用获取文件存储客户端"""
    try:
        from derisk.core.interface.file import FileStorageClient
        system_app = CFG.SYSTEM_APP
        if not system_app:
            return None
        return FileStorageClient.get_instance(system_app)
    except Exception:
        return None
```

修改 `_create_client` 方法：
```python
async def _create_client(self) -> SandboxBase:
    file_storage_client = self._get_file_storage_client()
    return await AutoSandbox.create(
        # ...
        file_storage_client=file_storage_client,  # 传递
        # 保留 OSS 配置作为向后兼容
        oss_ak=sandbox_config.oss_ak,
        # ...
    )
```

### 6. AgentChat 和 CoreV2Adapter 修改

**packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py**
**packages/derisk-serve/src/derisk_serve/agent/core_v2_adapter.py**

添加获取 FileStorageClient 的逻辑：
```python
file_storage_client = None
try:
    from derisk.core.interface.file import FileStorageClient
    file_storage_client = FileStorageClient.get_instance(self.system_app)
    if file_storage_client:
        logger.info("FileStorageClient retrieved for sandbox creation")
except Exception as e:
    logger.warning(f"Failed to get FileStorageClient: {e}")

sandbox_client = await AutoSandbox.create(
    # ...
    file_storage_client=file_storage_client,
    # ...
)
```

## 优先级和向后兼容

### 文件操作优先级

1. **FileStorageClient** (推荐)
   - 统一的文件存储接口
   - 支持多种后端（OSS、S3、本地等）
   - 更好的扩展性

2. **Legacy OSS** (向后兼容)
   - 当 FileStorageClient 不可用时使用
   - 通过 sandbox 配置的 oss_ak、oss_sk 等

3. **Local Only**
   - 当两者都不可用时，文件仅保存在本地 sandbox

### 配置优先级

1. 如果 FileStorageClient 可用（通过 `FileStorageClient.get_instance()`）
   - 优先使用 FileStorageClient
   - OSS 配置作为备用

2. 如果 FileStorageClient 不可用
   - 使用 sandbox 配置的 OSS
   - 如果 OSS 也不可用，仅本地存储

## 使用建议

### 新部署

1. 只需配置 `[[serves.backends]]` 的 OSS
2. 不需要配置 `[sandbox]` 的 OSS
3. 系统会自动使用 FileStorageClient

### 现有部署

两种方式：

**方式 1：完全迁移（推荐）**
```toml
# 移除 [sandbox] 的 OSS 配置
[sandbox]
type="local"
# oss_ak=...  # 删除或注释
# oss_sk=...  # 删除或注释
# ...
```

**方式 2：渐进式迁移**
```toml
# 保留 [sandbox] 的 OSS 配置作为备用
[sandbox]
type="local"
oss_ak="${env:OSS_ACCESS_KEY_ID:-xxx}"
# ...
```
系统会优先使用 FileStorageClient，失败时回退到 sandbox 的 OSS 配置。

## 优势

✅ **消除配置重复**：只配置一次 OSS  
✅ **统一文件管理**：所有文件操作使用同一套接口  
✅ **简化维护**：减少配置项，降低维护成本  
✅ **更好的扩展性**：支持多种存储后端（OSS、S3、本地等）  
✅ **向后兼容**：保留 legacy OSS 配置，不影响现有部署  

## 测试验证

运行基础测试验证：
```bash
# 语法检查
python -m py_compile packages/derisk-core/src/derisk/sandbox/client/file/client.py
python -m py_compile packages/derisk-ext/src/derisk_ext/sandbox/local/file_client.py
python -m py_compile packages/derisk-ext/src/derisk_ext/sandbox/local/improved_provider.py
python -m py_compile packages/derisk-core/src/derisk/agent/core/sandbox_manager.py
```

所有检查通过 ✓

## 参考

参考了内源 derisk 项目的实现：
- `/Users/tuyang/Code/derisk_develop/repos/backend/derisk`
- 主要参考文件：
  - `packages/derisk-core/src/derisk/sandbox/client/file/client.py`
  - `packages/derisk-ext/src/derisk_ext/sandbox/local/file_client.py`
  - `packages/derisk-core/src/derisk/agent/core/sandbox_manager.py`