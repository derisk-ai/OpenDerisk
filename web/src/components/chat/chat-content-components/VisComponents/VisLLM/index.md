---
group:
  order: 1
  title: VIS卡片
---

# VisLLM

## 基础用法

```jsx
import React from 'react';
import { Space } from 'antd';
import { VisLLM } from '@alipay/uni-chat';

export default () => {
  return (
    <div style={{width: '100%'}}>
      <div
      style={{
        width: '50%',
        // background: '#e7ecf8',
        // borderRadius: '16px',
        // padding: '16px',
      }}
    >
      <Space direction="vertical" style={{ width: '365px' }}>
        <VisLLM
        data={
          {
            "uid": "test123",
            "type": "incr",
            "markdown": "# 这是一个示例回复\n\n这是来自AI助手的示例回复内容，支持**Markdown**格式。\n\n- 列表项1\n- 列表项2\n- 列表项3",
            "token_use": 256,
            "token_speed": 45.8,
            "llm_model": "gpt-4-turbo",
            "llm_avatar": "https://local.alipay/avatars/ai-assistant.png",
            "start_time": "2024-01-15T14:30:00Z",
            "firt_out_time": "2024-01-15T14:30:02.345Z",
            "cost": 2345,
            "link_url": "https://example.com/chat/session-12345",
            "status": "completed"
          }
        }
        />
      </Space>
    </div>
    <div
      style={{
        width: '100%',
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <VisLLM
        data={
          {
            "uid": "test123",
            "type": "incr",
            "markdown": "# 这是一个示例回复\n\n这是来自AI助手的示例回复内容，支持**Markdown**格式。\n\n- 列表项1\n- 列表项2\n- 列表项3",
            "token_use": 256,
            "token_speed": 45.8,
            "llm_model": "gpt-4-turbo",
            "llm_avatar": "https://local.alipay/avatars/ai-assistant.png",
            "start_time": "2024-01-15T14:30:00Z",
            "firt_out_time": "2024-01-15T14:30:02.345Z",
            "cost": 2345,
            "link_url": "https://example.com/chat/session-12345",
            "status": "completed"
          }
        }
        />
      </Space>
    </div>
    </div>
  );
};
```

```ts
// DataIProps
{
  markdown: string;
  [key: string]: any;
}
```

## API

| 字段名称    | 字段类型                  | 字段描述 | 默认值 |
| ----------- | ------------------------- | -------- | ------ |
| data_source | <Badge>DataIProps</Badge> | 数据源   | -      |
