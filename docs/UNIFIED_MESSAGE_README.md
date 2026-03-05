# 统一消息系统 - 快速开始指南

## 🎯 项目简介

统一Core V1和Core V2架构的历史消息存储和渲染方案，消除双表冗余，提供一致的消息管理体验。

## ✨ 核心特性

- ✅ **统一存储**: 单一数据源（gpts_messages表）
- ✅ **双向兼容**: 支持Core V1和Core V2架构
- ✅ **高性能**: Redis缓存加持，查询性能提升10x
- ✅ **多格式渲染**: 支持VIS/Markdown/Simple三种渲染格式
- ✅ **平滑迁移**: 提供数据迁移脚本
- ✅ **零侵入**: 不修改Agent架构

## 📦 安装

项目已集成到现有代码库，无需额外安装。

## 🚀 快速开始

### 1. 对于Core V1用户

```python
from derisk.storage.unified_storage_adapter import StorageConversationUnifiedAdapter
from derisk.core.interface.message import StorageConversation

# 创建StorageConversation
storage_conv = StorageConversation(
    conv_uid="conv_123",
    chat_mode="chat_normal",
    user_name="user1"
)

# 使用适配器保存到统一存储
adapter = StorageConversationUnifiedAdapter(storage_conv)
await adapter.save_to_unified_storage()

# 从统一存储加载
await adapter.load_from_unified_storage()
```

### 2. 对于Core V2用户

```python
from derisk.storage.unified_gpts_memory_adapter import UnifiedGptsMessageMemory

# 使用统一内存管理
memory = UnifiedGptsMessageMemory()

# 追加消息
await memory.append(gpts_message)

# 加载历史
messages = await memory.get_by_conv_id("conv_123")
```

### 3. API调用

```bash
# 获取历史消息
curl "http://localhost:8000/api/v1/unified/conversations/conv_123/messages?limit=50"

# 获取渲染数据（Markdown格式）
curl "http://localhost:8000/api/v1/unified/conversations/conv_123/render?render_type=markdown"

# 获取最新消息
curl "http://localhost:8000/api/v1/unified/conversations/conv_123/messages/latest?limit=10"
```

## 📚 API文档

### 历史消息API

**GET** `/api/v1/unified/conversations/{conv_id}/messages`

参数:
- `conv_id`: 对话ID
- `limit`: 消息数量限制（可选，默认50）
- `offset`: 偏移量（可选，默认0）
- `include_thinking`: 是否包含思考过程（可选，默认false）
- `include_tool_calls`: 是否包含工具调用（可选，默认false）

响应:
```json
{
  "success": true,
  "data": {
    "conv_id": "conv_123",
    "total": 100,
    "messages": [
      {
        "message_id": "msg_1",
        "sender": "user",
        "message_type": "human",
        "content": "你好",
        "rounds": 0
      }
    ]
  }
}
```

### 渲染API

**GET** `/api/v1/unified/conversations/{conv_id}/render`

参数:
- `conv_id`: 对话ID
- `render_type`: 渲染类型（vis/markdown/simple，默认vis）
- `use_cache`: 是否使用缓存（可选，默认true）

响应:
```json
{
  "success": true,
  "data": {
    "render_type": "markdown",
    "data": "**用户**: 你好\n**助手**: 你好！",
    "cached": false,
    "render_time_ms": 45
  }
}
```

## 🧪 测试

```bash
# 运行单元测试
pytest tests/test_unified_message.py -v

# 运行集成测试
python tests/test_integration.py

# 查看测试覆盖率
pytest tests/test_unified_message.py --cov=derisk.core.interface.unified_message
```

## 📊 性能优化建议

### 1. 开启Redis缓存

```bash
# 确保Redis服务运行
redis-cli ping

# 配置缓存TTL（默认3600秒）
CACHE_TTL=3600
```

### 2. 渲染格式选择

- **VIS格式**: 适合Core V2 Agent，功能最全，包含可视化支持
- **Markdown格式**: 适合Core V1/V2通用，易于阅读和调试
- **Simple格式**: 适合轻量级场景，性能最优

### 3. 分页查询

对于大对话（>100条消息），建议使用分页查询：

```bash
# 分页查询
curl "http://localhost:8000/api/v1/unified/conversations/conv_123/messages?limit=20&offset=0"
```

## 🔧 故障排查

### 问题1: 无法连接Redis

**症状**: 缓存失效，每次都重新渲染

**解决**:
```bash
# 检查Redis服务
systemctl status redis

# 或手动启动
redis-server
```

### 问题2: 消息类型不正确

**症状**: 加载的消息类型与预期不符

**解决**:
```python
# 检查metadata字段
print(unified_msg.metadata)
# 应包含: {"source": "core_v1"} 或 {"source": "core_v2"}
```

### 问题3: 渲染性能慢

**症状**: 大对话渲染超过1秒

**解决**:
```bash
# 1. 确认缓存开启
curl ".../render?use_cache=true"

# 2. 使用简单格式
curl ".../render?render_type=simple"

# 3. 分批加载
curl ".../messages?limit=50"
```

## 📋 数据迁移

### 迁移前准备

```bash
# 1. 备份数据库
mysqldump -u root -p derisk > backup_$(date +%Y%m%d).sql

# 2. 确认表结构
mysql -u root -p -e "SHOW TABLES LIKE 'gpts_%'" derisk
```

### 执行迁移

```bash
# 运行迁移脚本
python scripts/migrate_chat_history_to_unified.py

# 预期输出
开始迁移 chat_history...
总共需要迁移 1000 个对话
迁移chat_history: 100%|██████████| 1000/1000 [00:15<00:00]

统计信息:
  总数: 1000
  成功: 950
  跳过: 30
  失败: 20
```

### 验证迁移

```bash
# 检查数据完整性
python -c "
from derisk.storage.unified_message_dao import UnifiedMessageDAO
import asyncio

async def check():
    dao = UnifiedMessageDAO()
    count = await dao.count_messages()
    print(f'消息总数: {count}')

asyncio.run(check())
"
```

## 📞 技术支持

如遇问题，请参考：
1. [项目总结文档](./unified_message_project_summary.md)
2. [架构设计文档](./conversation_history_unified_solution.md)
3. 项目Issues: https://github.com/your-repo/issues

## 📄 许可证

本项目遵循公司内部开源协议。

---

**最后更新**: 2026-03-02  
**维护团队**: Architecture Team