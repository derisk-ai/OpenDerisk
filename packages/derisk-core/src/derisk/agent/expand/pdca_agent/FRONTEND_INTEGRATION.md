# 前端对接文档 - Terminate 文件交付

## 概述

实现了 Terminate（任务终止）时向后端发送文件列表，并由前端展示的功能。

## 前端需要实现的内容

### 1. d-attach-list 组件

**组件名称**: `d-attach-list`
**用途**: 展示多个文件的交付列表

#### 接收数据格式

```typescript
interface VisAttachListContent {
  uid: string;              // 组件唯一标识
  type: "all" | "incr";     // 更新类型
  title?: string;           // 列表标题（默认"交付文件"）
  description?: string;     // 列表描述（如"共3个文件，总大小1.5MB"）
  files: VisAttachContent[];// 文件列表
  total_count: number;      // 文件总数
  total_size: number;       // 文件总大小（字节）
  show_batch_download: boolean; // 是否显示批量下载按钮
}

interface VisAttachContent {
  uid: string;              // 文件组件UID
  type: "all" | "incr";     // 更新类型
  file_id: string;          // 文件唯一标识
  file_name: string;        // 文件名（如"报告.md"）
  file_type: string;        // 文件类型（如"conclusion", "deliverable"）
  file_size: number;        // 文件大小（字节）
  oss_url?: string;         // OSS访问地址
  preview_url?: string;     // 预览URL（带签名）
  download_url?: string;    // 下载URL（带签名）
  mime_type?: string;       // MIME类型（如"text/markdown"）
  created_at?: string;      // 创建时间ISO格式
  task_id?: string;         // 关联任务ID
  description?: string;     // 文件描述
}
```

#### 示例数据

```json
{
  "uid": "terminate_files_conv_123",
  "type": "all",
  "title": "交付文件",
  "description": "共 3 个文件，总大小 1.5 MB",
  "files": [
    {
      "uid": "file_xxx_1",
      "type": "all",
      "file_id": "uuid-1",
      "file_name": "分析报告.md",
      "file_type": "conclusion",
      "file_size": 10240,
      "oss_url": "oss://bucket/path/file1.md",
      "preview_url": "https://oss.com/file1.md?signature=xxx",
      "download_url": "https://oss.com/file1.md?download&signature=xxx",
      "mime_type": "text/markdown",
      "created_at": "2024-01-15T10:30:00",
      "task_id": "task_001",
      "description": "任务执行分析报告"
    },
    {
      "uid": "file_xxx_2",
      "type": "all",
      "file_id": "uuid-2",
      "file_name": "数据.json",
      "file_type": "deliverable",
      "file_size": 5120,
      "oss_url": "oss://bucket/path/file2.json",
      "preview_url": "https://oss.com/file2.json?signature=xxx",
      "download_url": "https://oss.com/file2.json?download&signature=xxx",
      "mime_type": "application/json",
      "created_at": "2024-01-15T10:30:00",
      "task_id": "task_002",
      "description": "原始数据文件"
    }
  ],
  "total_count": 3,
  "total_size": 1572864,
  "show_batch_download": true
}
```

#### UI设计建议

1. **标题区域**:
   - 显示 `title`（如"交付文件"）
   - 显示 `description`（如"共3个文件，总大小1.5MB"）

2. **文件列表**:
   - 每个文件显示为一个卡片/行
   - 文件图标：根据 `mime_type` 或 `file_name` 后缀显示不同图标
   - 文件名：可点击预览
   - 文件大小：格式化显示
   - 操作按钮：预览 | 下载

3. **批量操作**:
   - 当 `show_batch_download=true` 时显示
   - 支持"下载全部"功能

4. **空状态**:
   - 当 `files` 为空时显示"暂无文件"

### 2. d-attach 单文件组件增强

**组件名称**: `d-attach`
**用途**: 展示单个文件（已有组件，需要增强）

#### 新增功能

1. **预览功能**:

```typescript
// 根据 mime_type 决定预览方式
function previewFile(file: VisAttachContent) {
  switch (file.mime_type) {
    case 'text/plain':
    case 'text/markdown':
    case 'text/csv':
    case 'application/json':
      // 文本文件：直接文本预览
      openTextPreview(file.preview_url || file.oss_url);
      break;

    case 'image/png':
    case 'image/jpeg':
    case 'image/gif':
      // 图片文件：图片预览
      openImagePreview(file.preview_url || file.oss_url);
      break;

    case 'application/pdf':
      // PDF文件：PDF预览器
      openPdfPreview(file.preview_url || file.oss_url);
      break;

    default:
      // 其他文件：显示下载提示
      showDownloadPrompt(file);
  }
}
```

2. **下载功能**:

```typescript
function downloadFile(file: VisAttachContent) {
  const url = file.download_url || file.oss_url;
  const filename = file.file_name;

  // 创建临时下载链接
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.target = '_blank';  // 如果签名URL可能需要新窗口打开
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
```

3. **文件大小格式化**:

```typescript
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
```

## 后端发送数据时机

### 触发时机

1. 用户发送任务请求
2. Agent 执行完成任务
3. Agent 调用 `terminate` Action 终止任务
4. 后端自动收集文件并附加到 `ActionOutput.output_files`
5. 后端调用 `NexIncrVisWindow2Converter.final_view()`
6. 后端渲染 `d-attach-list` 组件
7. 前端接收 vis 数据并展示

### 数据流向

```
[AgentFileSystem] 保存文件
       ↓
[terminate action] 终止任务（带output_files）
       ↓
[NexIncrVisWindow2Converter] 检测terminate，渲染文件
       ↓
[d-attach-list 组件数据] → 前端
       ↓
[前端展示] 文件列表
```

## 文件类型映射

常用文件类型及对应图标：

| file_type | 说明 | 建议图标 |
|-----------|------|---------|
| conclusion | 结论文件 | 📄 文档图标 |
| deliverable | 交付物 | 📦 包裹图标 |
| tool_output | 工具输出 | 🔧 工具图标 |
| write_file | 写入文件 | ✏️ 编辑图标 |
| temp | 临时文件 | 📝 文件图标 |

MIME类型与预览方式：

| mime_type | 预览方式 |
|-----------|---------|
| text/* | 文本预览 |
| image/* | 图片预览 |
| application/pdf | PDF预览 |
| application/json | JSON格式化预览 |
| text/csv | 表格预览 |

## 错误处理

1. **预览失败**:
   - 提示"暂不支持该文件类型预览"
   - 提供下载按钮

2. **下载失败**:
   - 提示"文件下载失败，请重试"
   - 记录错误日志

3. **URL过期**:
   - 提示"预览链接已过期，请重新获取"
   - 提供刷新机制（可选）

## 安全注意事项

1. **URL签名**: `preview_url` 和 `download_url` 包含OSS签名，会过期
2. **文件类型检查**: 预览前检查 mime_type，避免安全风险
3. **XSS防护**: 文本预览时进行HTML转义

## 测试数据

用于前端开发的测试数据：

```javascript
const testData = {
  uid: "terminate_files_test",
  type: "all",
  title: "交付文件",
  description: "共 3 个文件，总大小 15.6 KB",
  files: [
    {
      uid: "file_1",
      type: "all",
      file_id: "uuid-1",
      file_name: "执行报告.md",
      file_type: "conclusion",
      file_size: 10240,
      oss_url: "https://example.com/report.md",
      preview_url: "https://example.com/report.md?preview",
      download_url: "https://example.com/report.md?download",
      mime_type: "text/markdown",
      created_at: "2024-01-15T10:30:00",
      task_id: "task_001",
      description: "任务执行详细报告"
    },
    {
      uid: "file_2",
      type: "all",
      file_id: "uuid-2",
      file_name: "数据.json",
      file_type: "deliverable",
      file_size: 3072,
      oss_url: "https://example.com/data.json",
      preview_url: "https://example.com/data.json?preview",
      download_url: "https://example.com/data.json?download",
      mime_type: "application/json",
      created_at: "2024-01-15T10:30:00",
      task_id: "task_002",
      description: "JSON格式原始数据"
    },
    {
      uid: "file_3",
      type: "all",
      file_id: "uuid-3",
      file_name: "图表.png",
      file_type: "deliverable",
      file_size: 2048,
      oss_url: "https://example.com/chart.png",
      preview_url: "https://example.com/chart.png?preview",
      download_url: "https://example.com/chart.png?download",
      mime_type: "image/png",
      created_at: "2024-01-15T10:30:00",
      task_id: "task_003",
      description: "数据可视化图表"
    }
  ],
  total_count: 3,
  total_size: 15360,
  show_batch_download: true
};
```

## 联调检查清单

- [ ] `d-attach-list` 组件能正确渲染
- [ ] 单文件预览功能正常（文本/图片/PDF）
- [ ] 单文件下载功能正常
- [ ] 批量下载功能正常
- [ ] 文件大小格式化显示正确
- [ ] 文件图标根据类型正确显示
- [ ] 空文件列表状态显示正常
- [ ] 任务终止时文件列表自动展示

## 相关文件

后端实现文件：
- `packages/derisk-core/src/derisk/vis/schema.py` - 数据模型
- `packages/derisk-ext/src/derisk_ext/vis/common/tags/derisk_attach_list.py` - Vis组件
- `packages/derisk-core/src/derisk/agent/expand/pdca_agent/agent_file_system_v2.py` - 文件系统
- `packages/derisk-ext/src/derisk_ext/vis/nex/nex_vis_window2_converter.py` - 渲染器

前端对接文档：
- 本文档
- `FILE_DELIVERY_IMPLEMENTATION.md` - 设计实现总结
