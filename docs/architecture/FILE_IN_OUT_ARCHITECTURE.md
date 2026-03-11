📋 完整文件处理全流程梳理

一、整体架构图

┌─────────────────────────────────────────────────────────────────────────────┐
│                            用户上传文件                                       │
│                     前端 → POST /api/v1/files/{bucket}                        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          文件分流决策层                                        │
│                   derisk_serve/agent/nex/file_type_config.py                  │
│                                                                               │
│   ┌─────────────────┐              ┌─────────────────────────────┐           │
│   │  MODEL_DIRECT   │              │     SANDBOX_TOOL            │           │
│   │  (模型直消费)    │              │     (沙箱工具处理)           │           │
│   │  图片/GIF等      │              │     文档/代码/数据/压缩包     │           │
│   └────────┬────────┘              └──────────────┬──────────────┘           │
│            │                                       │                          │
│            ▼                                       ▼                          │
│   ┌─────────────────┐              ┌─────────────────────────────┐           │
│   │  多模态模型输入   │              │    SandboxFileRef          │           │
│   │  ChatCompletion │              │    下载到沙箱工作目录         │           │
│   │  ContentPart    │              │    注册到AgentFileSystem     │           │
│   └─────────────────┘              └─────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          沙箱文件处理层                                        │
│                   derisk/agent/core/file_system/                              │
│                                                                               │
│   AgentFileSystem ──────────────────────────────────────────────────────────  │
│   ├── FileStorageClient (优先)                                               │
│   ├── OSS Client (回退)                                                      │
│   └── LocalFileStorage (最后回退)                                             │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          工具生成文件                                         │
│                   derisk/agent/core/sandbox/tools/                            │
│                                                                               │
│   ├── create_file_tool.py (创建文件)                                          │
│   ├── edit_file_tool.py (编辑文件)                                            │
│   └── deliver_file_tool.py (交付文件) ⭐                                      │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          文件交付标记                                         │
│                   deliver_file_tool.py + dattach_utils.py                     │
│                                                                               │
│   1. 读取沙箱文件内容                                                          │
│   2. 上传到OSS获取持久化链接                                                    │
│   3. 生成d-attach组件                                                          │
│   4. 注册到AgentFileSystem                                                    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          前端展示                                             │
│                   VisDAttachList / d-attach-list 组件                         │
│                                                                               │
│   ├── 预览功能 (preview_url)                                                  │
│   ├── 下载功能 (download_url)                                                 │
│   └── 批量下载                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
二、文件分流决策逻辑（核心）

关键文件: derisk_serve/agent/nex/file_type_config.py

class FileProcessMode(str, Enum):
    MODEL_DIRECT = "model_direct"      # 直接发送给模型
    SANDBOX_TOOL = "sandbox_tool"       # 通过沙箱工具处理

# 分流规则：
# MODEL_DIRECT: 图片类型
# SANDBOX_TOOL: 文档/代码/数据/压缩等
# 默认: SANDBOX_TOOL
分流触发点: derisk_serve/agent/nex/query_builder.py

def get_file_process_mode(file_name: str, mime_type: str) -> FileProcessMode:
    # 根据扩展名和MIME类型返回处理模式
    
# 如果是 MODEL_DIRECT:
#   → 返回 ChatCompletionContentPartImageParam
#   → 直接作为多模态模型输入

# 如果是 SANDBOX_TOOL:
#   → 返回 SandboxFileRef
#   → 下载到沙箱工作目录
#   → 注册到 AgentFileSystem
三、迁移核心文件清单

✅ 必须迁移（按优先级排序）

序号	文件路径	核心类/函数	职责
1	derisk-core/src/derisk/core/interface/file.py	FileStorageClient, FileStorageSystem, StorageBackend, FileMetadata, FileStorageURI	文件存储抽象层核心
2	derisk-core/src/derisk/agent/core/file_system/agent_file_system.py	AgentFileSystem	Agent文件系统V3
3	derisk-core/src/derisk/agent/core/file_system/dattach_utils.py	render_dattach, create_dattach_content	d-attach组件生成
4	derisk-core/src/derisk/agent/core/sandbox/tools/deliver_file_tool.py	execute_deliver_file	文件交付工具 ⭐
5	derisk-core/src/derisk/agent/core/sandbox_manager.py	SandboxManager	沙箱生命周期管理
6	derisk-serve/src/derisk_serve/agent/nex/file_type_config.py	FileProcessMode, get_file_process_mode	文件分流决策
7	derisk-serve/src/derisk_serve/agent/nex/query_builder.py	QueryBuilder, SandboxFileRef	文件路由处理
8	derisk-serve/src/derisk_serve/file/api/endpoints.py	upload_files, download_file	文件API端点
9	derisk-serve/src/derisk_serve/file/service/service.py	Service.upload_files	文件服务层
10	derisk-serve/src/derisk_serve/file/api/schemas.py	UploadFileResponse, FileMetadataResponse	数据模型
📦 按需迁移

文件路径	核心类/函数	职责
derisk-ext/src/derisk_ext/storage/file/oss/oss_storage.py	AliyunOSSStorage	阿里云OSS存储
derisk-ext/src/derisk_ext/storage/file/ant_oss/oss_storage.py	AntOSSStorage	蚂蚁OSS存储
derisk-ext/src/derisk_ext/storage/file/s3/s3_storage.py	S3Storage	S3存储
derisk-core/src/derisk/agent/core/sandbox/tools/create_file_tool.py	execute_create_file	创建文件工具
derisk-core/src/derisk/agent/core/sandbox/tools/edit_file_tool.py	execute_edit_file	编辑文件工具
derisk-core/src/derisk/agent/core/sandbox/tools/download_file_tool.py	execute_download_file	下载文件工具
🔗 依赖文件

文件路径	核心类/函数	职责
derisk-core/src/derisk/agent/core/memory/gpts/file_base.py	AgentFileMetadata, FileType	文件元数据模型
derisk-core/src/derisk/vis/schema.py	VisAttachContent, VisAttachListContent	可视化数据模型
derisk-core/src/derisk/sandbox/client/file/client.py	FileClient	沙箱文件客户端接口
derisk-core/src/derisk/sandbox/client/file/types.py	FileInfo, OSSFile	文件类型定义
四、核心数据结构

1. FileMetadata（文件存储层）

@dataclass
class FileMetadata(StorageItem):
    file_id: str           # 文件ID
    bucket: str            # 存储桶
    file_name: str         # 文件名
    file_size: int         # 文件大小
    storage_type: str      # 存储类型
    storage_path: str      # 存储路径
    uri: str               # 统一资源标识
    custom_metadata: Dict  # 自定义元数据
    file_hash: str         # 文件哈希
2. AgentFileMetadata（Agent层）

class AgentFileMetadata:
    file_id: str
    conv_id: str           # 会话ID
    file_key: str          # 文件键
    file_name: str
    file_type: FileType    # CONCLUSION/DELIVERABLE/TOOL_OUTPUT等
    oss_url: str           # OSS地址
    preview_url: str       # 预览URL
    download_url: str      # 下载URL
    mime_type: str
    created_at: datetime
    expires_at: datetime
3. FileType枚举

class FileType(str, Enum):
    TEMP = "temp"                    # 临时文件
    TOOL_OUTPUT = "tool_output"       # 工具输出
    TRUNCATED_OUTPUT = "truncated"    # 截断输出
    CONCLUSION = "conclusion"         # 结论文件
    DELIVERABLE = "deliverable"       # 交付物 ⭐
    KANBAN = "kanban"
    WRITE_FILE = "write_file"
4. SandboxFileRef（分流层）

@dataclass
class SandboxFileRef:
    file_name: str         # 文件名
    file_url: str          # 文件URL
    mime_type: str         # MIME类型
    object_path: str       # OSS对象路径
    sandbox_path: str      # 沙箱本地路径
五、关键API接口

文件上传

POST /api/v1/files/{bucket}
Request:  multipart/form-data (files[])
Response: List[UploadFileResponse]
          - file_name, file_id, bucket, uri
文件下载

GET /api/v1/files/{bucket}/{file_id}
Response: StreamingResponse (application/octet-stream)
文件预览

GET /api/v1/files/preview?url={oss_url}
Response: Response (with Content-Type header)
文件元数据

GET /api/v1/files/metadata?uri={uri}
POST /api/v1/files/metadata/batch
Response: FileMetadataResponse
          - file_name, file_id, bucket, uri, file_size
六、迁移步骤建议

第一步：迁移存储抽象层

# 1. 复制核心接口文件
derisk-core/src/derisk/core/interface/file.py

# 2. 选择存储后端实现
# 阿里云OSS
derisk-ext/src/derisk_ext/storage/file/oss/oss_storage.py
# 或 S3
derisk-ext/src/derisk_ext/storage/file/s3/s3_storage.py
第二步：迁移文件服务层

# API端点
derisk-serve/src/derisk_serve/file/api/endpoints.py
derisk-serve/src/derisk_serve/file/api/schemas.py

# 服务实现
derisk-serve/src/derisk_serve/file/service/service.py
第三步：迁移分流决策层

# 文件类型配置
derisk-serve/src/derisk_serve/agent/nex/file_type_config.py

# 路由处理
derisk-serve/src/derisk_serve/agent/nex/query_builder.py
第四步：迁移沙箱文件系统

# Agent文件系统
derisk-core/src/derisk/agent/core/file_system/agent_file_system.py
derisk-core/src/derisk/agent/core/file_system/dattach_utils.py

# 沙箱管理器
derisk-core/src/derisk/agent/core/sandbox_manager.py

# 文件工具
derisk-core/src/derisk/agent/core/sandbox/tools/deliver_file_tool.py
第五步：迁移前端组件

# Vis数据模型
derisk-core/src/derisk/vis/schema.py

# 前端组件（如需要）
web/src/components/chat/chat-content-components/VisComponents/VisDAttachList/
七、注意事项

依赖注入: FileStorageClient 需要通过 SystemApp 注册和获取
配置项: 需要配置OSS/S3的访问凭证和endpoint
沙箱环境: 如使用沙箱功能，需配置沙箱服务（XIC等）
URL生成: 确保存储后端支持生成公开访问URL（签名URL）
元数据存储: 需要配置数据库或内存存储文件元数据
文件类型扩展: 如需新增文件类型分流规则，修改 file_type_config.py