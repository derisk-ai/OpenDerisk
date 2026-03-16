# 流式参数配置系统

## 概述

流式参数配置系统支持**应用级别**的工具流式参数配置，可在前端 UI 中独立编辑和管理。

---

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      应用编辑页面                               │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  Tabs: 基本信息 | 工具配置 | 流式参数配置 | 其他配置        ││
│  └────────────────────────────────────────────────────────────┘│
│                              │                                  │
│                              ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  StreamingConfigEditor 组件                                ││
│  │                                                            ││
│  │  ┌────────────────┐  ┌────────────────┐                   ││
│  │  │ 工具列表       │  │ 参数配置表格   │                   ││
│  │  │ - write        │  │ - content      │                   ││
│  │  │ - edit         │  │ - threshold    │                   ││
│  │  │ - bash         │  │ - strategy     │                   ││
│  │  └────────────────┘  └────────────────┘                   ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ API
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    后端 API 服务                                 │
│                                                                 │
│  GET    /api/v1/streaming-config/apps/{app_code}               │
│  PUT    /api/v1/streaming-config/apps/{app_code}/tools/{tool}  │
│  DELETE /api/v1/streaming-config/apps/{app_code}/tools/{tool}  │
│  GET    /api/v1/streaming-config/tools/available               │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    数据库存储                                    │
│                                                                 │
│  streaming_tool_config 表                                       │
│  - app_code, tool_name                                         │
│  - param_configs (JSON)                                        │
│  - global_threshold, global_strategy, global_renderer          │
│  - enabled, priority                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 在应用编辑页面集成

```tsx
// app/[appCode]/edit/page.tsx

import { Tabs } from 'antd';
import { StreamingConfigEditor } from '@/components/streaming';

export default function AppEditPage({ params }) {
  const appCode = params.appCode;
  
  return (
    <Tabs
      items={[
        { key: 'basic', label: '基本信息', children: <BasicInfo /> },
        { key: 'tools', label: '工具配置', children: <ToolConfig /> },
        { 
          key: 'streaming', 
          label: '流式参数配置', 
          children: (
            <StreamingConfigEditor 
              appCode={appCode}
              onConfigChange={(config) => {
                console.log('Config saved:', config);
              }}
            />
          )
        },
      ]}
    />
  );
}
```

### 2. 后端 API 路由

```python
# derisk_serve/streaming_config/api.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from derisk.model.streaming.config_manager import (
    StreamingConfigManager,
    ToolStreamingConfig,
    get_config_manager,
)
from derisk.model.streaming.db_models import (
    StreamingToolConfigInput,
    StreamingToolConfigResponse,
)

router = APIRouter(prefix="/api/v1/streaming-config")


@router.get("/apps/{app_code}")
async def get_app_configs(
    app_code: str,
    db: Session = Depends(get_db),
):
    """获取应用的所有流式配置"""
    manager = StreamingConfigManager(db)
    configs = manager.get_app_configs(app_code)
    
    return {
        "app_code": app_code,
        "configs": [c.to_dict() for c in configs.values()],
        "total": len(configs),
    }


@router.put("/apps/{app_code}/tools/{tool_name}")
async def save_tool_config(
    app_code: str,
    tool_name: str,
    config_input: StreamingToolConfigInput,
    db: Session = Depends(get_db),
):
    """保存工具流式配置"""
    manager = StreamingConfigManager(db)
    
    # 转换输入
    config = ToolStreamingConfig(
        tool_name=tool_name,
        app_code=app_code,
        param_configs={
            p.param_name: ParamStreamingConfig.from_dict(p.dict())
            for p in config_input.param_configs
        },
        global_threshold=config_input.global_threshold,
        global_strategy=config_input.global_strategy,
        global_renderer=config_input.global_renderer,
        enabled=config_input.enabled,
        priority=config_input.priority,
    )
    
    success = manager.save_tool_config(app_code, tool_name, config)
    
    return {"success": success, "config": config.to_dict()}


@router.delete("/apps/{app_code}/tools/{tool_name}")
async def delete_tool_config(
    app_code: str,
    tool_name: str,
    db: Session = Depends(get_db),
):
    """删除工具流式配置"""
    manager = StreamingConfigManager(db)
    success = manager.delete_tool_config(app_code, tool_name)
    return {"success": success}


@router.get("/tools/available")
async def get_available_tools(
    app_code: str = None,
    db: Session = Depends(get_db),
):
    """获取可用工具列表"""
    # 返回工具注册表中的工具
    from derisk.agent.tools import ToolRegistry
    
    tools = ToolRegistry.list_tools()
    
    result = []
    for tool in tools:
        # 检查是否已有配置
        has_config = False
        if app_code:
            manager = StreamingConfigManager(db)
            config = manager.get_tool_config(app_code, tool.name)
            has_config = config is not None
        
        result.append({
            "tool_name": tool.name,
            "tool_display_name": tool.display_name,
            "description": tool.description,
            "parameters": [
                {"name": p.name, "type": p.type, "description": p.description}
                for p in tool.parameters
            ],
            "has_streaming_config": has_config,
        })
    
    return {"tools": result}
```

---

## 配置示例

### 完整的工具配置结构

```json
{
  "tool_name": "write",
  "app_code": "my_app",
  "param_configs": {
    "content": {
      "param_name": "content",
      "threshold": 1024,
      "strategy": "semantic",
      "chunk_size": 100,
      "chunk_by_line": true,
      "renderer": "code",
      "enabled": true,
      "description": "文件内容，超过 1KB 启用流式"
    }
  },
  "global_threshold": 256,
  "global_strategy": "adaptive",
  "global_renderer": "default",
  "enabled": true,
  "priority": 0
}
```

### 分片策略说明

| 策略 | 适用场景 | 说明 |
|------|---------|------|
| `adaptive` | 通用 | 自动识别内容类型，选择最佳策略 |
| `line_based` | 代码 | 按代码行分片，每 N 行一个 chunk |
| `semantic` | 代码 | 按语义单元（函数/类）分片 |
| `fixed_size` | 文本 | 按固定字符数分片 |

### 渲染器说明

| 渲染器 | 适用场景 | 特性 |
|--------|---------|------|
| `code` | 代码内容 | 语法高亮、行号、打字机效果 |
| `text` | 纯文本 | 打字机效果、进度条 |
| `default` | 通用 | 基础进度显示 |

---

## 运行时使用

### 在 Agent 中使用配置

```python
from derisk.model.streaming import (
    StreamingFunctionCallProcessor,
    get_config_manager,
)

async def chat_handler(session_id: str, app_code: str, llm_stream):
    # 获取配置管理器
    config_manager = get_config_manager()
    
    # 获取工具配置
    tool_config = config_manager.get_tool_config(app_code, "write")
    
    # 检查参数是否应该流式
    if tool_config.should_stream("content", large_content):
        param_config = tool_config.get_param_config("content")
        # 使用配置中的策略
        strategy = param_config.strategy
        threshold = param_config.threshold
        # ...
```

### 前端使用配置

```tsx
import { useStreamingFunctionCall } from '@/utils/streaming';

function MyChatComponent({ appCode }) {
  const { handleMessage, streamingParams } = useStreamingFunctionCall({
    onParamChunk: (callId, paramName, chunk) => {
      console.log('Received chunk:', chunk);
    },
  });
  
  // SSE 消息处理
  useEffect(() => {
    const eventSource = new EventSource(`/api/chat/stream?app_code=${appCode}`);
    
    eventSource.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      // 处理流式参数消息
      if (message.type?.startsWith('tool_param')) {
        handleMessage(message);
      }
    };
    
    return () => eventSource.close();
  }, [appCode]);
  
  return (
    <div>
      {/* 渲染流式参数 */}
      {Array.from(streamingParams.entries()).map(([key, state]) => (
        <StreamingParamRenderer
          key={key}
          callId={state.callId}
          paramName={state.paramName}
          builder={builder}
        />
      ))}
    </div>
  );
}
```

---

## 扩展机制

### 添加新的分片策略

```python
# derisk/model/streaming/chunk_strategies.py

class MyCustomChunkStrategy(IChunkStrategy):
    """自定义分片策略"""
    
    @property
    def name(self) -> str:
        return "my_custom"
    
    async def chunk(self, content: str, options: Dict[str, Any]) -> AsyncGenerator[str, None]:
        # 实现自定义分片逻辑
        pass
    
    def estimate_chunks(self, content: str) -> Optional[int]:
        # 估算分片数量
        pass

# 注册策略
STRATEGY_REGISTRY[ChunkStrategy.MY_CUSTOM] = MyCustomChunkStrategy
```

### 添加新的渲染器

```tsx
// utils/streaming/streaming-renderer.tsx

const MyCustomRenderer: React.FC<StreamingRendererProps> = (props) => {
  return (
    <div className="my-custom-renderer">
      {/* 自定义渲染逻辑 */}
    </div>
  );
};

// 注册渲染器
rendererRegistry.register({
  name: 'my_custom',
  supports: (props) => props.renderer === 'my_custom',
  render: (props) => <MyCustomRenderer {...props} />,
});
```

---

## 数据库迁移

```sql
-- 创建流式工具配置表
CREATE TABLE streaming_tool_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    app_code VARCHAR(128) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    tool_display_name VARCHAR(256),
    tool_description TEXT,
    param_configs JSON NOT NULL DEFAULT '{}',
    global_threshold INT DEFAULT 256,
    global_strategy VARCHAR(32) DEFAULT 'adaptive',
    global_renderer VARCHAR(32) DEFAULT 'default',
    enabled BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(128),
    updated_by VARCHAR(128),
    
    UNIQUE KEY uk_app_tool (app_code, tool_name),
    INDEX idx_app_code (app_code),
    INDEX idx_tool_name (tool_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## API 接口文档

### GET /api/v1/streaming-config/apps/{app_code}

获取应用的所有流式配置。

**响应:**
```json
{
  "app_code": "my_app",
  "configs": [...],
  "total": 3
}
```

### PUT /api/v1/streaming-config/apps/{app_code}/tools/{tool_name}

保存工具的流式配置。

**请求体:**
```json
{
  "tool_name": "write",
  "param_configs": [...],
  "global_threshold": 256,
  "enabled": true
}
```

### DELETE /api/v1/streaming-config/apps/{app_code}/tools/{tool_name}

删除工具的流式配置。

### GET /api/v1/streaming-config/tools/available

获取可用工具列表及其参数信息。

**参数:**
- `app_code` (可选): 应用代码，用于检查配置状态

**响应:**
```json
{
  "tools": [
    {
      "tool_name": "write",
      "tool_display_name": "Write Tool",
      "description": "创建或覆写文件",
      "parameters": [
        {"name": "content", "type": "string", "description": "文件内容"}
      ],
      "has_streaming_config": true
    }
  ]
}
```