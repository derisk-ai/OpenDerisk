# 统一架构完整模块化重构方案

## 📁 标准项目结构

```
unified/
├── __init__.py                    # 只导出公共API
├── application/
│   ├── __init__.py                # 导出: UnifiedAppBuilder, UnifiedAppInstance
│   ├── models.py                  # 数据模型: UnifiedResource, UnifiedAppInstance
│   └── builder.py                 # 业务逻辑: UnifiedAppBuilder实现
├── session/
│   ├── __init__.py                # 导出: UnifiedSessionManager, UnifiedSession
│   ├── models.py                  # 数据模型: UnifiedMessage, UnifiedSession
│   └── manager.py                 # 业务逻辑: UnifiedSessionManager实现
├── interaction/
│   ├── __init__.py                # 导出: UnifiedInteractionGateway
│   ├── models.py                  # 数据模型: InteractionRequest, InteractionResponse等
│   └── gateway.py                 # 业务逻辑: UnifiedInteractionGateway实现
├── visualization/
│   ├── __init__.py                # 导出: UnifiedVisAdapter
│   ├── models.py                  # 数据模型: VisOutput, VisMessageType等
│   └── adapter.py                 # 业务逻辑: UnifiedVisAdapter实现
└── api/
    ├── __init__.py                # 导出: router
    ├── routes.py                  # API路由实现
    └── schemas.py                 # Pydantic请求/响应模型
```

## ✅ 已完成模块

### 1. application模块 ✅
- `models.py` - 完成
- `builder.py` - 完成
- `__init__.py` - 完成

### 2. session模块
- `models.py` - 已创建，需要补充

## 📝 重构状态

### 模块重构进度
- [x] application模块 - 已完成标准化重构
- [ ] session模块 - models.py已创建，需要补充manager.py
- [ ] interaction模块 - 需要完整重构
- [ ] visualization模块 - 需要完整重构
- [ ] api模块 - 需要完整重构

## 🔧 重构要点

### 1. `__init__.py` 应该只做导出

**错误示例**（之前的方式）:
```python
# __init__.py
class UnifiedAppBuilder:
    # 所有业务逻辑都写在这里
    pass
```

**正确示例**（现在的方式）:
```python
# __init__.py
from .builder import UnifiedAppBuilder
from .models import UnifiedAppInstance, UnifiedResource

__all__ = ["UnifiedAppBuilder", "UnifiedAppInstance", "UnifiedResource"]
```

### 2. 分离关注点

- **models.py**: 纯数据模型，使用dataclass或Pydantic
- **builder.py/manager.py**: 核心业务逻辑，依赖注入，异步处理
- **__init__.py**: 清晰的API导出，隐藏内部实现

### 3. 依赖注入和接口设计

```python
# builder.py
class UnifiedAppBuilder:
    def __init__(self, system_app=None):
        self._system_app = system_app
        self._app_cache = {}
    
    async def build_app(self, app_code: str) -> UnifiedAppInstance:
        # 清晰的业务逻辑
        pass
```

## 🎯 下一步工作

1. 完成session模块的manager.py
2. 重构interaction模块
3. 重构visualization模块
4. 创建独立的API schemas和routes
5. 添加单元测试

---

**文档创建时间**: 2026-03-01  
**重构负责人**: Derisk Team