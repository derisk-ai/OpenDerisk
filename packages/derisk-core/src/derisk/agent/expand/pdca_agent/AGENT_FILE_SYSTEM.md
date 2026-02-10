# AgentFileSystem 完整架构文档

## 1. 概述

AgentFileSystem (AFS) 是一个完整的Agent文件管理系统，为ReActMasterV2和PDCA Agent提供统一的文件管理能力。

### 核心特性

- **文件分类管理**: 支持工具输出、写入文件、结论文件、看板文件等多种类型
- **元数据持久化**: 参考GPTSMemory设计，支持数据库级别的文件元数据存储
- **OSS集成**: 自动上传文件到OSS，生成可访问的URL
- **可视化交互**: 结论文件自动推送d-attach组件到前端
- **会话恢复**: 支持会话重启后的文件系统状态恢复
- **内容去重**: 基于哈希的内容去重机制

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         AgentFileSystem                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ File Storage │  │   Metadata   │  │   Visualization      │   │
│  │   (文件存储)  │  │   (元数据)    │  │     (可视化)          │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                     │               │
│    ┌────▼────┐      ┌────▼────┐          ┌─────▼─────┐         │
│    │  Local  │      │  GPTS   │          │  d-attach │         │
│    │   FS    │      │ Memory  │          │ Component │         │
│    └────┬────┘      └────┬────┘          └─────┬─────┘         │
│         │                │                      │               │
│    ┌────▼────────────────▼──────────────────────▼────┐          │
│    │                   OSS                          │          │
│    └────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据模型

#### AgentFileMetadata（文件元数据）

参考 `GptsMessage` 和 `GptsPlan` 的设计：

```python
@dataclass
class AgentFileMetadata:
    file_id: str              # 文件唯一标识符
    conv_id: str              # 会话ID
    conv_session_id: str      # 会话会话ID
    file_key: str             # 文件系统内的key
    file_name: str            # 文件名
    file_type: str            # 文件类型（枚举值）
    file_size: int            # 文件大小（字节）
    local_path: str           # 本地文件路径
    oss_url: str              # OSS URL
    preview_url: str          # 预览URL
    download_url: str         # 下载URL
    content_hash: str         # 内容哈希（用于去重）
    status: str               # 文件状态
    created_by: str           # 创建者（agent名称）
    created_at: datetime      # 创建时间
    updated_at: datetime      # 更新时间
    expires_at: datetime      # 过期时间
    metadata: Dict            # 额外元数据
    task_id: str              # 关联任务ID
    message_id: str           # 关联消息ID
    tool_name: str            # 关联工具名称
```

#### FileType（文件类型枚举）

```python
class FileType(Enum):
    TOOL_OUTPUT = "tool_output"           # 工具结果临时文件
    WRITE_FILE = "write_file"             # write工具写入的文件
    SANDBOX_FILE = "sandbox_file"         # 沙箱环境文件
    CONCLUSION = "conclusion"             # 结论文件（推送给用户）
    KANBAN = "kanban"                     # 看板相关文件
    DELIVERABLE = "deliverable"           # 交付物文件
    TRUNCATED_OUTPUT = "truncated_output" # 截断输出文件
    WORKFLOW = "workflow"                 # 工作流文件
    KNOWLEDGE = "knowledge"               # 知识库文件
    TEMP = "temp"                         # 临时文件
```

### 2.3 存储机制

#### 三层存储架构

1. **本地文件系统**
   - 路径: `{DATA_DIR}/agent_storage/{session_id}/{goal_id}/`
   - 用途: 临时存储、快速访问

2. **OSS对象存储**
   - 路径: `oss://bucket/{session_id}/{goal_id}/{filename}`
   - 用途: 持久化存储、生成访问URL

3. **元数据存储**
   - 接口: `AgentFileMemory`
   - 默认实现: `DefaultAgentFileMemory`（内存）
   - 扩展: 可接入数据库持久化

#### Catalog机制

每个会话维护一个文件目录（Catalog）:
```json
{
  "file_key_1": {
    "file_id": "uuid",
    "file_name": "xxx.md",
    "file_type": "conclusion",
    "local_path": "/path/to/file",
    "oss_url": "oss://...",
    "hash": "md5_hash",
    "created_at": "2024-01-01T00:00:00",
    "created_by": "AgentName"
  }
}
```

## 3. 核心API

### 3.1 AgentFileSystem 类

#### 初始化

```python
afs = AgentFileSystem(
    conv_id=str,              # 会话ID
    session_id=str,           # 会话会话ID（可选）
    goal_id=str,              # 目标ID（可选）
    base_working_dir=str,     # 基础工作目录
    sandbox=SandboxBase,      # 沙箱环境（可选）
    gpts_memory=GptsMemory,   # GPTS内存（可选）
    oss_client=OSSClient,     # OSS客户端（可选）
)
```

#### 文件操作

```python
# 保存文件
file_metadata = await afs.save_file(
    file_key="unique_key",
    data="content",
    file_type=FileType.CONCLUSION,
    file_name="report.md",
    is_conclusion=True,  # 自动推送d-attach
)

# 读取文件
content = await afs.read_file(file_key)

# 删除文件
success = await afs.delete_file(file_key)

# 列出文件
files = await afs.list_files(file_type=FileType.CONCLUSION)
```

#### 便捷方法

```python
# 保存工具输出
file_metadata = await afs.save_tool_output(
    tool_name="analyzer",
    output="output content",
)

# 保存结论文件（自动推送d-attach）
file_metadata = await afs.save_conclusion(
    data="# Report",
    file_name="结论报告.md",
    created_by="ReActMasterV2",
    task_id="task_001",
)
```

### 3.2 GPTSMemory 集成

```python
# 从GPTSMemory获取文件管理接口
file_memory = gpts_memory.file_memory
catalog_memory = gpts_memory.file_catalog_memory

# 添加文件元数据
await gpts_memory.append_file(conv_id, file_metadata)

# 获取会话的所有文件
files = await gpts_memory.get_files(conv_id)

# 获取结论文件
conclusion_files = await gpts_memory.get_conclusion_files(conv_id)

# 按类型查询
filtered_files = await gpts_memory.get_files_by_type(conv_id, FileType.TOOL_OUTPUT)
```

### 3.3 ReActMasterAgent 集成

```python
class MyAgent(ReActMasterAgent):
    async def run_task(self, task):
        # 执行任务...

        # 保存结论文件（自动推送d-attach）
        await self.save_conclusion_file(
            content="# 分析结果\n\n代码质量评分: 95",
            file_name="分析报告.md",
            task_id=task.id,
        )

        # 获取所有文件
        files = await self.get_agent_files()

        # 推送所有结论文件
        await self.push_all_conclusions()
```

## 4. 可视化交互

### 4.1 d-attach 组件

当保存结论文件时，系统自动推送 `d-attach` 组件到前端：

```html
<d-attach
  file_id="xxx"
  file_name="分析报告.md"
  file_type="conclusion"
  file_size="1024"
  oss_url="oss://..."
  preview_url="https://..."
  download_url="https://..."
  mime_type="text/markdown"
/>
```

### 4.2 VisAttachContent 数据模型

```python
class VisAttachContent(VisBase):
    file_id: str
    file_name: str
    file_type: str
    file_size: int
    oss_url: str
    preview_url: str
    download_url: str
    mime_type: str
    created_at: str
    task_id: str
    description: str
```

## 5. 会话恢复

### 5.1 恢复流程

1. **加载Catalog**: 从本地加载文件目录
2. **加载元数据**: 从GPTSMemory加载持久化的文件元数据
3. **合并数据**: 合并本地和持久化的文件信息
4. **检查完整性**: 检查本地文件是否存在
5. **OSS同步**: 从OSS下载缺失的文件

### 5.2 恢复代码

```python
# 创建新的AgentFileSystem实例
afs = AgentFileSystem(
    conv_id="existing_conv_id",
    gpts_memory=gpts_memory,  # 传入GPTSMemory以加载持久化数据
)

# 同步工作区（自动恢复）
await afs.sync_workspace()

# 现在可以访问之前的所有文件
files = await afs.list_files()
```

## 6. 使用示例

### 6.1 基本使用

```python
import asyncio
from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

async def main():
    # 创建文件系统
    afs = AgentFileSystem(conv_id="my_session")

    # 保存工具输出
    await afs.save_tool_output(
        tool_name="file_search",
        output="Found 10 files...",
    )

    # 保存结论（自动推送d-attach）
    await afs.save_conclusion(
        data="# Analysis Result\n\nPassed!",
        file_name="result.md",
    )

    # 同步（恢复时调用）
    await afs.sync_workspace()

asyncio.run(main())
```

### 6.2 与ReActMasterAgent集成

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

class MyAnalyzer(ReActMasterAgent):
    async def analyze_code(self, code):
        # 分析代码...

        # 保存详细报告
        await self.save_conclusion_file(
            content=report_content,
            file_name="代码分析报告.md",
        )

        # 保存原始数据
        await self.save_conclusion_file(
            content=json.dumps(raw_data),
            file_name="原始数据.json",
            extension="json",
        )
```

### 6.3 截断输出保存

```python
from derisk.agent.expand.react_master_agent.truncation import create_truncator_with_fs

# 创建带AFS的截断器
truncator = await create_truncator_with_fs(
    conv_id="my_session",
    gpts_memory=gpts_memory,
)

# 截断大输出
result = truncator.truncate(
    content=large_output,  # 10000行内容
    tool_name="log_reader",
)

# 结果被截断，但完整内容通过AFS保存
print(result.file_key)  # 可以读取完整内容
```

## 7. 配置选项

### 7.1 环境变量

```bash
# 基础存储目录
DERISK_AGENT_STORAGE_DIR=/path/to/storage

# OSS配置
DERISK_OSS_BUCKET=your-bucket
DERISK_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
```

### 7.2 初始化参数

```python
AgentFileSystem(
    conv_id="required",
    session_id="optional",
    goal_id="optional",
    base_working_dir="agent_storage",  # 默认
    sandbox=None,                      # 沙箱环境
    gpts_memory=None,                  # GPTS内存
    oss_client=None,                   # OSS客户端
)
```

## 8. 扩展开发

### 8.1 自定义文件类型

```python
from derisk.agent.core.memory.gpts import FileType

# 定义新的文件类型
FileType.CUSTOM_REPORT = "custom_report"

# 使用
await afs.save_file(
    file_key="my_report",
    data=content,
    file_type="custom_report",
)
```

### 8.2 自定义存储后端

```python
from derisk.agent.core.memory.gpts import AgentFileMemory

class MyFileMemory(AgentFileMemory):
    def append(self, file_metadata: AgentFileMetadata):
        # 实现你的存储逻辑
        pass

    # 实现其他方法...

# 使用自定义存储
gpts_memory = GptsMemory(file_memory=MyFileMemory())
```

## 9. 注意事项

1. **异步操作**: 所有文件操作都是异步的，需要使用 `await`
2. **内存管理**: 大文件不会缓存在内存中，只保存元数据
3. **过期清理**: 文件默认7天过期，需要定期清理
4. **OSS依赖**: 如果不配置OSS，使用模拟的local:// URL
5. **会话隔离**: 不同会话的文件存储在独立的目录中

## 10. 迁移指南

### 从旧版迁移

旧版代码:
```python
from derisk.agent.expand.pdca_agent.agent_system_file import AgentFileSystem

afs = AgentFileSystem(conv_id="xxx")
afs.save_file("key", "data")
```

新版代码:
```python
from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

afs = AgentFileSystem(conv_id="xxx")
await afs.save_file(
    file_key="key",
    data="data",
    file_type=FileType.TEMP,
)
```

主要变化:
- 导入路径: `agent_system_file` -> `agent_file_system`
- `save_file` 变为异步方法
- 需要指定 `file_type` 参数
- 新增大量便捷方法和功能
