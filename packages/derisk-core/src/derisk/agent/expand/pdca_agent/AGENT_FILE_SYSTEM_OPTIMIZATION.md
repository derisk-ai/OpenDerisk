# AgentFileSystem 架构优化建议

## 当前问题

当前实现中存在三层文件元数据缓存，导致架构复杂：

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: GptsMemory.ConversationCache                         │
│ self.files: Dict[str, AgentFileMetadata]      ← 会话内存缓存   │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: AgentFileSystem._catalog                            │
│ self._catalog: Dict[str, Dict]                ← 本地JSON缓存   │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: AgentFileMemory._storage                            │
│ Dict[conv_id, Dict[file_id, AgentFileMetadata]] ← 持久化存储   │
└──────────────────────────────────────────────────────────────┘
```

## 优化方案

### 方案A：GptsMemory 主导（推荐）

**核心思想**：
- GptsMemory 统一管理文件元数据（缓存 + 持久化）
- AgentFileSystem 只负责文件IO（本地文件读写 + OSS操作）
- 移除 AFS._catalog，从 GptsMemory 获取元数据

**架构变更**:

```python
class AgentFileSystem:
    def __init__(self, conv_id, gpts_memory, ...):
        self.gpts_memory = gpts_memory  # 依赖注入
        # 移除: self._catalog, self._loaded

    async def save_file(self, ...):
        # 1. 写入本地文件
        # 2. 上传OSS
        # 3. 创建元数据
        # 4. 保存到 GptsMemory（缓存+持久化）
        await self.gpts_memory.append_file(self.conv_id, file_metadata)

    async def read_file(self, file_key):
        # 1. 从 GptsMemory 获取元数据
        file_metadata = await self.gpts_memory.get_file_by_key(self.conv_id, file_key)
        # 2. 读取本地文件

    async def sync_workspace(self):
        # 1. 从 GptsMemory 加载所有文件元数据
        files = await self.gpts_memory.get_files(self.conv_id)
        # 2. 检查本地文件完整性
        # 3. 从OSS恢复缺失文件
```

**优点**:
- 单一数据源：GptsMemory 是唯一的元数据来源
- 简化架构：移除 AFS 内部缓存，避免维护两套数据
- 职责清晰：AFS 只负责文件IO，GptsMemory 负责元数据管理

**缺点**:
- AFS 依赖 GptsMemory，不能独立使用
- 每次操作都需要访问 GptsMemory

---

### 方案B：AgentFileSystem 主导

**核心思想**：
- AgentFileSystem 管理本地文件元数据（_catalog）
- GptsMemory 只提供持久化接口，不写缓存
- 启动时从 AFS 加载元数据到 GptsMemory

**架构变更**:

```python
class GptsMemory:
    def __init__(self, ...):
        # 移除: ConversationCache.files 和 file_key_index
        # 只保留: file_memory（持久化接口）

class AgentFileSystem:
    def __init__(self, conv_id, file_memory, ...):
        self.file_memory = file_memory  # 持久化接口
        self._catalog: Dict[str, AgentFileMetadata] = {}  # 本地缓存

    async def sync_workspace(self):
        # 1. 从持久化存储加载
        files = await self.file_memory.get_by_conv_id(self.conv_id)
        # 2. 重建本地缓存
        self._catalog = {f.file_key: f for f in files}
```

**优点**:
- AFS 可以独立工作
- 本地操作不依赖 GptsMemory

**缺点**:
- 仍然有两层缓存（AFS._catalog 和 GptsMemory 的底层持久化缓存）
- 恢复时需要重建缓存

---

### 方案C：懒加载模式（当前已部分实现，建议优化）

**核心思想**：
- GptsMemory 缓存是按需加载的（懒加载）
- AFS 也是按需加载 catalog
- 两者独立，通过接口协作

**协作流程**:

```python
# 保存文件
async def save_file(self, file_key, data, ...):
    # AFS步骤
    local_path = await self._write_local(data)
    oss_url = await self._upload_oss(local_path)

    # 创建元数据
    metadata = AgentFileMetadata(
        file_key=file_key,
        local_path=local_path,
        oss_url=oss_url,
        ...
    )

    # 保存到 GptsMemory（更新缓存+持久化）
    if self.gpts_memory:
        await self.gpts_memory.append_file(self.conv_id, metadata)

    # AFS也更新自己的catalog（用于本地文件管理）
    self._catalog[file_key] = {
        "local_path": local_path,
        "oss_url": oss_url,
        ...
    }
    await self._save_catalog_to_disk()
```

**问题**:
- 元数据保存了两份（GptsMemory + AFS catalog）
- 可能导致不一致

---

## 推荐实现：方案A - GptsMemory 主导

### 具体变更

#### 1. 移除 AgentFileSystem._catalog

```python
class AgentFileSystem:
    def __init__(self, conv_id, gpts_memory, ...):
        self.conv_id = conv_id
        self.gpts_memory = gpts_memory  # 必须传入
        self._oss_client = oss_client
        # 移除以下字段:
        # self._catalog
        # self._hash_index
        # self._loaded
        # self.meta_path  # 如果GptsMemory管理所有元数据，不需要本地catalog
```

#### 2. AFS 方法改为从 GptsMemory 获取元数据

```python
async def list_files(self, file_type=None):
    """从 GptsMemory 获取文件列表"""
    if not self.gpts_memory:
        return []

    if file_type:
        files = await self.gpts_memory.get_files_by_type(self.conv_id, file_type)
    else:
        files = await self.gpts_memory.get_files(self.conv_id)

    return [f.to_dict() for f in files]

async def get_file_info(self, file_key):
    """从 GptsMemory 获取文件元数据"""
    if not self.gpts_memory:
        return None
    return await self.gpts_memory.get_file_by_key(self.conv_id, file_key)
```

#### 3. GptsMemory 缓存策略

```python
class ConversationCache:
    def __init__(self, ...):
        # files 缓存仍然需要，用于快速访问
        self.files: Dict[str, AgentFileMetadata] = {}
        self.file_key_index: Dict[str, str] = {}

class GptsMemory:
    async def append_file(self, conv_id, file_metadata):
        # 1. 更新缓存
        cache = await self._get_or_create_cache(conv_id)
        async with await self._get_conv_lock(conv_id):
            cache.files[file_metadata.file_id] = file_metadata
            cache.file_key_index[file_metadata.file_key] = file_metadata.file_id

        # 2. 持久化
        await blocking_func_to_async(
            self._executor, self._file_memory.append, file_metadata
        )
```

#### 4. AFS 只保留本地文件管理功能

```python
class AgentFileSystem:
    """Agent文件IO系统 - 只负责文件操作，不管理元数据"""

    async def _write_local(self, file_key: str, data: Any) -> Path:
        """写入本地文件"""
        ...

    async def _read_local(self, local_path: Path) -> str:
        """读取本地文件"""
        ...

    async def _upload_oss(self, local_path: Path) -> str:
        """上传OSS"""
        ...

    async def _download_oss(self, oss_url: str, local_path: Path):
        """从OSS下载"""
        ...

    async def delete_local(self, file_key: str):
        """删除本地文件"""
        # 从 GptsMemory 获取路径，然后删除
        metadata = await self.gpts_memory.get_file_by_key(self.conv_id, file_key)
        if metadata:
            await self._delete_file(Path(metadata.local_path))
```

### 优势

1. **单一数据源**：GptsMemory 是文件元数据的唯一真相来源
2. **职责清晰**：
   - GptsMemory：元数据管理（缓存+持久化）
   - AFS：文件IO（本地+OSS）
3. **简化维护**：不需要维护两套catalog
4. **更好的恢复机制**：恢复时 GptsMemory.naive_load 加载持久化数据，AFS 恢复本地文件

### 迁移路径

1. **阶段1**：保持当前设计，添加 deprecation warning
2. **阶段2**：修改 AFS 使用 GptsMemory 获取元数据
3. **阶段3**：移除 AFS._catalog 和相关方法
4. **阶段4**：更新文档和示例

## 当前设计的折中方案

如果暂时不想大幅重构，可以采用以下折中方案：

### 明确职责分工

| 功能 | GptsMemory | AgentFileSystem |
|-----|------------|-----------------|
| 元数据缓存 | ✅ 唯一的内存缓存 | ❌ 使用GptsMemory |
| 元数据持久化 | ✅ 通过file_memory | ❌ 不使用 |
| 本地文件catalog | ❌ 使用GptsMemory | ✅ 可选（本地文件管理） |
| 本地文件IO | ❌ | ✅ |
| OSS操作 | ❌ | ✅ |
| URL生成 | ❌ | ✅ |
| d-attach推送 | ✅ 通过push_message | ✅ 调用GptsMemory |

### 关键约定

1. AFS.catalog 只用于**本地文件路径管理**（不保存完整元数据）
2. 完整的元数据始终从 GptsMemory 获取
3. sync_workspace 时从 GptsMemory 加载元数据，检查本地文件
