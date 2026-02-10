# AgentFileSystem V2 架构设计

## 设计目标

解决V1中"多重缓存"的问题，同时保持**扩展性**，使AgentFileSystem可以在不同场景下灵活使用。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    AgentFileSystem V2                           │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │  File IO Layer  │    │    Metadata Storage Interface       │ │
│  │                 │    │                                     │ │
│  │  - Local Read   │◄──►│  FileMetadataStorage (Interface)    │ │
│  │  - Local Write  │    │                                     │ │
│  │  - OSS Upload   │    └──────────────┬──────────────────────┘ │
│  │  - OSS Download │                   │                        │
│  └─────────────────┘                   ▼                        │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │  URL Generator  │    │   Storage Implementations           │ │
│  │                 │    │                                     │ │
│  │  - Preview URL  │    │  ┌───────────────┐ ┌──────────────┐ │ │
│  │  - Download URL │    │  │  GptsMemory   │ │ SimpleFile   │ │ │
│  └─────────────────┘    │  │  (Full)       │ │ Metadata     │ │ │
│                         │  │               │ │ Storage      │ │ │
│  ┌─────────────────┐    │  │  • Cache      │ │ (Light)      │ │ │
│  │  Content Hash   │    │  │  • Persist    │ │              │ │ │
│  │  Index (Dedup)  │    │  │  • Push Msg   │ │  • Memory    │ │ │
│  └─────────────────┘    │  └───────────────┘ └──────────────┘ │ │
│                         └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 关键设计思路

### 1. 明确职责分离

| 组件 | 职责 | 不做什么 |
|------|------|----------|
| **AgentFileSystem** | 文件IO、OSS操作、URL生成、去重 | 不存储元数据 |
| **FileMetadataStorage** (接口) | 定义元数据操作契约 | 不处理文件IO |
| **GptsMemory** (实现) | 元数据缓存+持久化+消息推送 | 不处理文件IO |
| **SimpleFileMetadataStorage** (实现) | 轻量级内存存储 | 不处理文件IO |

### 2. FileMetadataStorage 接口

这是连接AgentFileSystem与各种存储实现的桥梁：

```python
class FileMetadataStorage(ABC):
    """文件元数据存储接口."""

    @abstractmethod
    async def save_file_metadata(self, file_metadata: AgentFileMetadata) -> None: ...

    @abstractmethod
    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]: ...

    @abstractmethod
    async def list_files(self, conv_id: str, ...) -> List[AgentFileMetadata]: ...

    # ... 其他方法
```

### 3. 存储实现对比

| 特性 | GptsMemory | SimpleFileMetadataStorage | 自定义实现 |
|------|-----------|---------------------------|-----------|
| 内存缓存 | ✅ 带LRU | ✅ 纯内存 | 自定义 |
| 持久化 | ✅ 是 | ❌ 否 | 自定义 |
| 消息推送 | ✅ 支持 | ❌ 不支持 | 自定义 |
| 适用场景 | 生产环境 | 测试/轻量 | 特殊需求 |

## 使用场景示例

### 场景1: 完整应用（推荐）使用 GptsMemory

```python
from derisk.agent.core.memory.gpts import GptsMemory
from derisk.agent.expand.pdca_agent.agent_file_system_v2 import AgentFileSystem

# 1. 创建GptsMemory（带缓存+持久化+消息推送）
gpts_memory = GptsMemory()
await gpts_memory.start()

# 2. 创建AFS，传入GptsMemory作为存储
afs = AgentFileSystem(
    conv_id="session_001",
    metadata_storage=gpts_memory,  # 使用GptsMemory
)

# 3. 使用AFS
metadata = await afs.save_conclusion(
    data="# Report",
    file_name="report.md",
)
# 元数据会自动保存到GptsMemory，并推送d-attach消息
```

### 场景2: 轻量级应用使用 SimpleFileMetadataStorage

```python
from derisk.agent.core.memory.gpts import SimpleFileMetadataStorage
from derisk.agent.expand.pdca_agent.agent_file_system_v2 import AgentFileSystem

# 1. 创建简单存储（仅内存，无持久化）
simple_storage = SimpleFileMetadataStorage()

# 2. 创建AFS
afs = AgentFileSystem(
    conv_id="temp_session",
    metadata_storage=simple_storage,
)

# 3. 使用AFS（适合临时任务、脚本、测试）
metadata = await afs.save_tool_output(
    tool_name="analyzer",
    output="result data",
)
```

### 场景3: 自定义存储（如数据库）

```python
from derisk.agent.core.memory.gpts import FileMetadataStorage

class DatabaseFileMetadataStorage(FileMetadataStorage):
    """数据库存储实现"""

    async def save_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        # 使用SQLAlchemy等ORM保存
        await db.session.add(file_metadata)
        await db.session.commit()

    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        # 从数据库查询
        return await db.session.query(...).filter_by(...).first()

    # ... 其他方法

# 使用自定义存储
db_storage = DatabaseFileMetadataStorage()
afs = AgentFileSystem(
    conv_id="session_001",
    metadata_storage=db_storage,
)
```

## 迁移路径

### 从V1迁移到V2

V1 API:
```python
afs = AgentFileSystem(
    conv_id="xxx",
    gpts_memory=gpts_memory,  # V1: 直接依赖GptsMemory
)
```

V2 API:
```python
afs = AgentFileSystem(
    conv_id="xxx",
    metadata_storage=gpts_memory,  # V2: 通过接口解耦
)
```

**向后兼容**: 可以通过别名保持兼容
```python
class AgentFileSystem:
    def __init__(self, ..., gpts_memory=None, metadata_storage=None):
        if gpts_memory and not metadata_storage:
            metadata_storage = gpts_memory
        self.metadata_storage = metadata_storage
```

## 扩展性设计

### 如何添加新的存储实现

1. **实现FileMetadataStorage接口**
```python
class RedisFileMetadataStorage(FileMetadataStorage):
    def __init__(self, redis_client):
        self.redis = redis_client

    async def save_file_metadata(self, metadata: AgentFileMetadata) -> None:
        await self.redis.set(f"file:{metadata.file_id}", metadata.to_json())

    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        data = await self.redis.get(f"file:{file_key}")
        return AgentFileMetadata.from_json(data) if data else None

    # ... 实现其他方法
```

2. **使用新实现**
```python
redis_storage = RedisFileMetadataStorage(redis_client)
afs = AgentFileSystem(metadata_storage=redis_storage)
```

### 存储组合模式

```python
class CachedFileMetadataStorage(FileMetadataStorage):
    """带缓存的装饰器"""

    def __init__(self, backend: FileMetadataStorage, cache: Cache):
        self.backend = backend
        self.cache = cache

    async def get_file_by_key(self, conv_id: str, file_key: str):
        # 先查缓存
        if cached := await self.cache.get(f"file:{file_key}"):
            return cached
        # 再查后端
        metadata = await self.backend.get_file_by_key(conv_id, file_key)
        if metadata:
            await self.cache.set(f"file:{file_key}", metadata)
        return metadata

    # ... 其他方法转发到backend

# 使用组合
cached_storage = CachedFileMetadataStorage(
    backend=DatabaseFileMetadataStorage(),
    cache=RedisCache(),
)
afs = AgentFileSystem(metadata_storage=cached_storage)
```

## 设计优势

1. **单一职责**: AgentFileSystem只负责文件IO
2. **依赖抽象**: 通过接口而非具体实现交互
3. **可替换**: 可以轻松替换存储后端
4. **可测试**: 可以使用MockStorage进行单元测试
5. **向后兼容**: 保持与V1类似的API

## 文件结构

```
derisk-core/src/derisk/agent/
├── core/memory/gpts/
│   ├── file_base.py                  # FileMetadataStorage接口
│   │                                 # SimpleFileMetadataStorage实现
│   ├── default_file_memory.py        # DefaultAgentFileMemory
│   ├── gpts_memory.py                # GptsMemory实现FileMetadataStorage
│   └── __init__.py                   # 导出所有接口
│
└── expand/pdca_agent/
    ├── agent_file_system.py          # V1实现（保留兼容）
    ├── agent_file_system_v2.py       # V2实现（基于接口）
    ├── AGENT_FILE_SYSTEM_V2_DESIGN.md # 本文档
    └── ...
```
