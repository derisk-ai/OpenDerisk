### d-llm

```d-llm
{
  "uid": "test123",
  "type": "incr",
  "markdown": "# 这是一个示例回复\n\n这是来自AI助手的示例回复内容，支持**Markdown**格式。\n\n- 列表项1\n- 列表项2\n- 列表项3",
  "token_use": 256,
  "token_speed": 45.8,
  "llm_model": "gpt-4-turbo",
  "llm_avatar": "https://example.com/avatars/ai-assistant.png",
  "start_time": "2024-01-15T14:30:00Z",
  "firt_out_time": "2024-01-15T14:30:02.345Z",
  "cost": 2345,
  "link_url": "https://example.com/chat/session-12345",
  "status": "completed"
}
```


### 工具
```d-tool
{
  "uid": "a1b2c3d4e5f67890",
  "message_id": "msg_20250405_123456",
  "type": "all",
  "avatar": null,
  "status": "running",
  "tool_name": "get_weather",
  "tool_desc": "获取指定城市的当前天气信息",
  "tool_version": null,
  "tool_author": null,
  "need_ask_user": false,
  "tool_args": {
    "city": "北京",
    "unit": "celsius"
  },
  "out_type": "json",
  "tool_result": "{\"a\": \"hello world\"}",
  "run_env": "xic-instance-01(python3.10)",
  "tool_cost": 10,
  "start_time": "2025-12-02 11:00:00",
  "err_msg": null,
  "progress": null
}
```
