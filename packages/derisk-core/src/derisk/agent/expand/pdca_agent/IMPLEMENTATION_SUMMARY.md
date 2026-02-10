# AgentFileSystem 实现总结

## 完成的工作

### 1. 核心架构实现 ✅

#### 1.1 文件元数据模型 (`file_base.py`)
- **AgentFileMetadata**: 完整的文件元数据模型
  - 基础标识: file_id, conv_id, conv_session_id
  - 文件信息: file_key, file_name, file_type, file_size
  - 存储路径: local_path, oss_url, preview_url, download_url
  - 内容相关: content_hash（用于去重）
  - 状态管理: status（pending/completed/failed/expired）
  - 关联信息: task_id, message_id, tool_name, created_by
  - 转换为d-attach组件格式的接口

- **FileType 枚举**: 11种文件类型分类
  - TOOL_OUTPUT: 工具结果临时文件
  - WRITE_FILE: write工具写入的文件
  - SANDBOX_FILE: 沙箱环境文件
  - CONCLUSION: 结论文件（推送给用户）
  - KANBAN: 看板相关文件
  - DELIVERABLE: 交付物文件
  - TRUNCATED_OUTPUT: 截断输出文件
  - WORKFLOW: 工作流文件
  - KNOWLEDGE: 知识库文件
  - TEMP: 临时文件

- **AgentFileMemory 接口**: 参考GptsMessageMemory设计
  - append(): 添加文件元数据
  - update(): 更新文件元数据
  - get_by_conv_id(): 获取会话的所有文件
  - get_by_file_id(): 通过ID获取文件
  - get_by_file_key(): 通过key获取文件
  - get_by_file_type(): 按类型查询文件
  - delete_by_conv_id(): 删除会话的所有文件

#### 1.2 内存存储实现 (`default_file_memory.py`)
- **DefaultAgentFileMemory**: 默认的内存存储实现
  - _storage: conv_id -> {file_id -> AgentFileMetadata}
  - _key_index: conv_id -> {file_key -> file_id}
  - get_conclusion_files(): 便捷方法获取结论文件
  - get_tool_output_files(): 便捷方法获取工具输出文件

- **DefaultAgentFileCatalogMemory**: 文件目录存储实现
  - 管理会话级的文件索引（file_key -> file_id）

#### 1.3 GPTSMemory集成 (`gpts_memory.py`)
扩展了GPTSMemory类：
- 添加 file_memory 和 file_catalog_memory 属性
- **ConversationCache文件字段**:
  - files: Dict[str, AgentFileMetadata]
  - file_catalog: Optional[AgentFileCatalog]
  - file_key_index: Dict[str, str]

- **新增方法**:
  - append_file(): 添加文件元数据
  - update_file(): 更新文件元数据
  - get_files(): 获取会话的所有文件
  - get_file_by_id(): 通过ID获取文件
  - get_file_by_key(): 通过key获取文件
  - get_files_by_type(): 按类型查询
  - get_conclusion_files(): 获取结论文件
  - save_file_catalog(): 保存文件目录
  - load_file_catalog(): 加载文件目录

### 2. 核心AgentFileSystem实现 (`agent_file_system.py`)

#### 2.1 完整文件操作
- **save_file()**: 核心保存方法
  - 支持所有文件类型
  - 内容去重（基于MD5哈希）
  - OSS自动上传
  - 预览/下载URL生成
  - 元数据持久化到GPTSMemory
  - 结论文件自动推送d-attach

- **read_file()**: 异步读取文件
  - 本地优先读取
  - 本地不存在时从OSS下载
  - 支持沙箱环境

- **delete_file()**: 异步删除文件
  - 删除本地文件
  - 更新catalog
  - 清理哈希索引

- **list_files()**: 列出文件
  - 支持file_type过滤
  - 支持category过滤
  - 返回完整文件信息

#### 2.2 分类管理
```python
class FileCategory(Enum):
    WORKSPACE = "workspace"      # 工作区文件
    TOOL_OUTPUT = "tool_output"  # 工具输出
    CONCLUSION = "conclusion"    # 结论文件
    RESOURCE = "resource"        # 资源文件
```

#### 2.3 URL生成
- **_generate_preview_url()**: 生成预览URL
  - 仅支持特定MIME类型（text/*, image/*, pdf等）
  - 生成带签名的临时URL

- **_generate_download_url()**: 生成下载URL
  - 带文件名提示
  - 签名有效期可配置

#### 2.4 便捷方法
- **save_tool_output()**: 保存工具输出
- **save_conclusion()**: 保存结论文件（自动推送d-attach）
- **save_truncated_output()**: 保存截断输出
- **get_file_for_attach()**: 获取d-attach组件内容

#### 2.5 可视化交互
- **_push_file_attach()**: 推送d-attach组件到前端
  - 使用VisAttachContent数据模型
  - 通过GPTSMemory.push_message()推送

- **push_conclusion_files()**: 推送所有结论文件

#### 2.6 会话恢复
- **sync_workspace()**: 同步工作区
  1. 加载本地catalog
  2. 合并GPTSMemory的持久化数据
  3. 检查本地文件完整性
  4. 从OSS下载缺失文件
  5. 重建hash索引

### 3. d-attach组件支持 (`schema.py`)

#### 3.1 VisAttachContent数据模型
```python
class VisAttachContent(VisBase):
    file_id: str           # 文件唯一标识
    file_name: str         # 文件名
    file_type: str         # 文件类型
    file_size: int         # 文件大小
    oss_url: str           # OSS地址
    preview_url: str       # 预览地址
    download_url: str      # 下载地址
    mime_type: str         # MIME类型
    created_at: str        # 创建时间
    task_id: str           # 关联任务ID
    description: str       # 文件描述
```

### 4. 截断输出集成 (`truncation.py`)

#### 4.1 更新内容
- 添加异步保存方法 `_save_via_agent_file_system()`
- 添加同步包装方法 `_save_via_agent_file_system_sync()`
- 异步读取方法 `read_truncated_content_async()`
- 更新 `create_truncator_with_fs()` 支持新AFS

#### 4.2 变化
- Truncator现在使用AgentFileSystem保存截断内容
- 生成file_key而非临时文件路径
- 支持从AFS读取完整内容

### 5. ReActMasterAgent集成 (`react_master_agent.py`)

#### 5.1 新增方法
- **_ensure_agent_file_system()**: 懒加载AFS
- **save_conclusion_file()**: 保存结论文件
- **get_agent_files()**: 获取Agent文件列表
- **push_all_conclusions()**: 推送所有结论
- **sync_file_workspace()**: 同步文件工作区

#### 5.2 初始化变更
- AgentFileSystem改为懒加载模式
- 在 `_load_thinking_messages()` 中初始化

### 6. 向后兼容 (`agent_system_file.py`)

- 发出DeprecationWarning警告
- 从新的agent_file_system导入所有内容
- 保持旧代码的兼容性

## 关键设计决策

### 1. 元数据存储分离
- 文件内容存储在本地FS/OSS
- 元数据存储在GPTSMemory
- Catalog用于快速索引

### 2. 三层架构
```
Local FS (快速访问)
    ↓
OSS (持久化、URL访问)
    ↓
GPTSMemory (元数据管理)
```

### 3. 异步设计
- 所有IO操作都是异步的
- 使用asyncio.to_thread进行同步IO转换
- 支持高并发协程环境

### 4. 沙箱支持
- 支持有/无沙箱环境
- 自动检测并使用相应的文件操作
- OSS上传时处理沙箱文件提取

## 使用示例

### 基础使用
```python
from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

afs = AgentFileSystem(conv_id="my_session")

# 保存工具输出
await afs.save_tool_output(tool_name="analyzer", output="result")

# 保存结论（自动推送d-attach）
await afs.save_conclusion(data="# Report", file_name="report.md")

# 读取文件
content = await afs.read_file(file_key)
```

### ReActMasterAgent使用
```python
class MyAgent(ReActMasterAgent):
    async def run(self):
        # 保存结论文件
        await self.save_conclusion_file(
            content="# Analysis\n\nPassed!",
            file_name="分析报告.md",
        )

        # 获取所有文件
        files = await self.get_agent_files()
```

## 文件列表

### 新增文件
1. `packages/derisk-core/src/derisk/agent/core/memory/gpts/file_base.py` - 元数据模型和接口
2. `packages/derisk-core/src/derisk/agent/core/memory/gpts/default_file_memory.py` - 默认内存实现
3. `packages/derisk-core/src/derisk/agent/expand/pdca_agent/agent_file_system.py` - 核心AFS实现
4. `examples/agent_file_system_demo.py` - 演示代码
5. `packages/derisk-core/src/derisk/agent/expand/pdca_agent/AGENT_FILE_SYSTEM.md` - 架构文档
6. `packages/derisk-core/src/derisk/agent/expand/pdca_agent/IMPLEMENTATION_SUMMARY.md` - 本文档

### 修改文件
1. `packages/derisk-core/src/derisk/agent/core/memory/gpts/__init__.py` - 导出新的类
2. `packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py` - 集成文件管理
3. `packages/derisk-core/src/derisk/vis/schema.py` - 添加VisAttachContent
4. `packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py` - 集成AFS
5. `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py` - 集成AFS
6. `packages/derisk-core/src/derisk/agent/expand/pdca_agent/agent_system_file.py` - 向后兼容

## 后续优化建议

### 1. 数据库存储实现
```python
class DatabaseAgentFileMemory(AgentFileMemory):
    """基于数据库的持久化实现"""
    def append(self, file_metadata: AgentFileMetadata):
        # 使用SQLAlchemy等ORM保存到数据库
        pass
```

### 2. 文件过期清理
```python
async def cleanup_expired_files(self):
    """清理过期文件"""
    expired = [
        f for f in await self.list_files()
        if f.expires_at and f.expires_at < datetime.utcnow()
    ]
    for f in expired:
        await self.delete_file(f.file_key)
```

### 3. 批量操作
```python
async def save_files_batch(
    self,
    files: List[Tuple[str, Any, FileType]],
) -> List[AgentFileMetadata]:
    """批量保存文件"""
    tasks = [
        self.save_file(key, data, ftype)
        for key, data, ftype in files
    ]
    return await asyncio.gather(*tasks)
```

### 4. 文件压缩
```python
async def compress_large_files(self, threshold_mb: int = 10):
    """压缩大文件"""
    for f in await self.list_files():
        if f.file_size > threshold_mb * 1024 * 1024:
            # 压缩并更新OSS
            pass
```

## 测试建议

### 单元测试
```python
async def test_save_and_read():
    afs = AgentFileSystem(conv_id="test")
    metadata = await afs.save_file("key", "data", FileType.TEMP)
    content = await afs.read_file("key")
    assert content == "data"
```

### 集成测试
```python
async def test_session_recovery():
    # 创建文件
    afs1 = AgentFileSystem(conv_id="test_recovery")
    await afs1.save_conclusion(data="test", file_name="test.md")

    # 重新创建并恢复
    afs2 = AgentFileSystem(conv_id="test_recovery")
    await afs2.sync_workspace()

    # 验证文件存在
    files = await afs2.list_files()
    assert len(files) == 1
```

## 总结

本实现提供了一个完整的Agent文件系统，解决了以下问题：
1. ✅ 补齐了agent运行过程的所有文件数据
2. ✅ 支持可视化交互，自动推送d-attach组件
3. ✅ d-attach组件支持文件预览和下载
4. ✅ 参考GPTSMemory设计了元数据存储机制
5. ✅ 实现了会话恢复功能

所有代码都遵循了现有架构的设计模式，并保持了向后兼容性。
