# Terminate 文件交付功能实现总结

## 功能概述

实现了在 Terminate（任务终止）时向用户交付相关文件的完整流程，包括：
1. 后端文件收集与传递
2. 前端文件展示（d-attach/d-attach-list组件）
3. 支持文件预览和下载

## 实现内容

### 1. 数据模型扩展 (`derisk/vis/schema.py`)

新增 `VisAttachListContent` 模型，用于多文件列表展示：

```python
class VisAttachListContent(VisBase):
    """文件附件列表内容 - 用于d-attach-list组件展示多个文件"""
    title: Optional[str] = Field(default="交付文件", description="文件列表标题")
    description: Optional[str] = Field(default=None, description="文件列表描述")
    files: List[VisAttachContent] = Field(default_factory=list, description="文件列表")
    total_count: int = Field(default=0, description="文件总数")
    total_size: int = Field(default=0, description="文件总大小（字节）")
    show_batch_download: bool = Field(default=True, description="是否显示批量下载按钮")
```

### 2. 多文件组件 (`derisk_ext/vis/common/tags/derisk_attach_list.py`)

创建新的 Vis 组件 `DeriskAttachList`：
- vis_tag: `d-attach-list`
- 用于展示多个文件的交付场景
- 支持批量下载

### 3. AgentFileSystem V2 文件收集 (`agent_file_system_v2.py`)

新增 `collect_delivery_files` 方法：

```python
async def collect_delivery_files(self, file_types=None) -> List[Dict[str, Any]]:
    """收集用于交付的文件列表.

    适用于terminate时收集所有相关文件进行交付。
    默认收集：结论文件(CONCLUSION)和交付物文件(DELIVERABLE)
    """
```

### 4. ReActMasterAgent 文件附加 (`react_master_agent.py`)

在 `act` 方法中添加逻辑：
- 检测 terminate action
- 调用 `_attach_delivery_files` 方法
- 将收集的文件附加到 `ActionOutput.output_files`

```python
async def _attach_delivery_files(self, action_out: ActionOutput) -> ActionOutput:
    """为terminate action附加交付文件."""
    # 1. 确保AgentFileSystem已初始化
    # 2. 收集交付文件
    # 3. 附加到ActionOutput.output_files
```

### 5. NexIncrVisWindow2Converter 文件渲染 (`nex_vis_window2_converter.py`)

在 `final_view` 方法中添加文件渲染：

```python
async def _render_terminate_files(self, messages, senders_map) -> Optional[str]:
    """渲染terminate时交付的文件列表."""
    # 1. 从messages中查找terminate action
    # 2. 从output_files获取文件信息
    # 3. 构建VisAttachContent列表
    # 4. 渲染d-attach-list组件
```

渲染流程：
1. 遍历所有消息，查找 terminate action
2. 提取 `output_files` 字段中的文件信息
3. 转换为 `VisAttachContent` 对象
4. 构建 `VisAttachListContent`（包含文件列表、总数、总大小等）
5. 使用 `DeriskAttachList` 组件渲染
6. 将渲染结果添加到 `running_window`

## 前端对接说明

### d-attach-list 组件接口

前端需要实现 `d-attach-list` 组件，接收以下数据格式：

```json
{
  "uid": "terminate_files_{conv_id}",
  "type": "all",
  "title": "交付文件",
  "description": "共 3 个文件，总大小 1.5 MB",
  "files": [
    {
      "file_id": "xxx",
      "file_name": "报告.md",
      "file_type": "conclusion",
      "file_size": 1024,
      "oss_url": "oss://...",
      "preview_url": "https://...",
      "download_url": "https://...",
      "mime_type": "text/markdown",
      "created_at": "2024-01-01T00:00:00",
      "task_id": "task_001",
      "description": "任务执行报告"
    }
  ],
  "total_count": 3,
  "total_size": 1572864,
  "show_batch_download": true
}
```

### d-attach 单文件组件增强

建议前端同时增强 `d-attach` 组件，支持：
1. **预览功能**：根据 mime_type 提供不同预览方式
   - 文本文件：直接文本预览
   - 图片文件：缩略图预览
   - PDF文件：PDF预览器
   - 其他文件：显示图标

2. **下载功能**：
   - 点击下载按钮触发文件下载
   - 使用 `download_url` 或 `oss_url`

3. **文件信息展示**：
   - 文件名
   - 文件大小（格式化显示）
   - 创建时间
   - 文件类型图标

## 使用流程

```
用户请求
    ↓
Agent 执行任务
    ↓
AgentFileSystem 保存结论文件
    ↓
Agent 调用 terminate
    ↓
ReActMasterAgent._attach_delivery_files
    ↓ 收集文件到 ActionOutput.output_files
NexIncrVisWindow2Converter.final_view
    ↓ 检测到terminate，渲染文件列表
前端 d-attach-list 组件
    ↓ 展示文件列表，支持预览/下载
用户查看/下载文件
```

## 配置说明

### 文件类型收集规则

默认收集以下类型的文件：
- `FileType.CONCLUSION` - 结论文件
- `FileType.DELIVERABLE` - 交付物文件

可在 `collect_delivery_files` 方法中自定义：

```python
# 自定义收集文件类型
delivery_files = await afs.collect_delivery_files(
    file_types=[FileType.CONCLUSION, FileType.TOOL_OUTPUT]
)
```

## 测试验证

### 1. 文件收集测试

```python
from derisk.agent.expand.pdca_agent.agent_file_system_v2 import AgentFileSystem
from derisk.agent.core.memory.gpts import SimpleFileMetadataStorage

afs = AgentFileSystem(
    conv_id="test_conv",
    metadata_storage=SimpleFileMetadataStorage()
)

# 保存测试文件
await afs.save_conclusion(data="# Test Report", file_name="report.md")

# 收集交付文件
files = await afs.collect_delivery_files()
assert len(files) == 1
assert files[0]["file_name"] == "report.md"
```

### 2. Vis 渲染测试

```python
from derisk.vis.schema import VisAttachListContent, VisAttachContent

content = VisAttachListContent(
    uid="test_files",
    type="all",
    title="交付文件",
    files=[
        VisAttachContent(
            uid="file_1",
            type="all",
            file_id="f1",
            file_name="test.txt",
            file_type="temp",
            file_size=100,
            download_url="https://..."
        )
    ],
    total_count=1,
    total_size=100
)
```

## 注意事项

1. **文件大小格式化**：`_format_file_size` 方法自动转换 B/KB/MB/GB
2. **文件去重**：`collect_delivery_files` 会自动去重（基于 file_id）
3. **错误处理**：各环节都有异常捕获，确保不影响主流程
4. **向后兼容**：如果 AgentFileSystem 未初始化，会跳过文件收集

## 后续优化建议

1. **前端实现**：
   - 实现 `d-attach-list` 组件
   - 增强 `d-attach` 组件的预览和下载功能
   - 支持文件批量下载

2. **后端增强**：
   - 支持文件过期自动清理
   - 支持文件权限控制
   - 支持文件版本管理

3. **交互优化**：
   - 支持 terminate 时确认文件列表
   - 支持用户选择需要下载的文件
