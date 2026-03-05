"""
响应式状态管理单元测试
"""

import pytest
import asyncio

from derisk.vis.reactive import (
    Signal,
    Effect,
    Computed,
    batch,
    ReactiveDict,
    ReactiveList,
)


class TestSignal:
    """Signal测试"""
    
    def test_create_signal(self):
        """测试创建Signal"""
        count = Signal(0)
        
        assert count.value == 0
    
    def test_set_value(self):
        """测试设置值"""
        count = Signal(0)
        count.value = 10
        
        assert count.value == 10
    
    def test_update_function(self):
        """测试更新函数"""
        count = Signal(5)
        count.update(lambda x: x * 2)
        
        assert count.value == 10
    
    def test_subscribe(self):
        """测试订阅"""
        count = Signal(0)
        values = []
        
        def callback(value):
            values.append(value)
        
        count.subscribe(callback)
        
        count.value = 1
        count.value = 2
        count.value = 3
        
        assert values == [1, 2, 3]


class TestEffect:
    """Effect测试"""
    
    def test_effect_execution(self):
        """测试Effect执行"""
        count = Signal(0)
        executions = []
        
        effect = Effect(lambda: executions.append(count.value))
        
        assert len(executions) == 1
        assert executions[0] == 0
    
    def test_effect_reactivity(self):
        """测试Effect响应性"""
        count = Signal(0)
        values = []
        
        effect = Effect(lambda: values.append(count.value))
        
        count.value = 1
        count.value = 2
        count.value = 3
        
        assert values == [0, 1, 2, 3]
    
    def test_effect_dispose(self):
        """测试Effect释放"""
        count = Signal(0)
        values = []
        
        effect = Effect(lambda: values.append(count.value))
        
        count.value = 1
        assert values == [0, 1]
        
        # 释放effect
        effect.dispose()
        
        count.value = 2
        # 不应该再触发
        assert values == [0, 1]
    
    def test_multiple_signals(self):
        """测试多个Signal"""
        a = Signal(1)
        b = Signal(2)
        results = []
        
        effect = Effect(lambda: results.append(a.value + b.value))
        
        assert results == [3]
        
        a.value = 10
        assert results == [3, 12]
        
        b.value = 20
        assert results == [3, 12, 30]


class TestComputed:
    """Computed测试"""
    
    def test_computed_value(self):
        """测试计算属性"""
        a = Signal(10)
        b = Signal(20)
        
        total = Computed(lambda: a.value + b.value)
        
        assert total.value == 30
    
    def test_computed_reactivity(self):
        """测试计算属性响应性"""
        first_name = Signal("John")
        last_name = Signal("Doe")
        
        full_name = Computed(lambda: f"{first_name.value} {last_name.value}")
        
        assert full_name.value == "John Doe"
        
        first_name.value = "Jane"
        assert full_name.value == "Jane Doe"
        
        last_name.value = "Smith"
        assert full_name.value == "Jane Smith"
    
    def test_computed_caching(self):
        """测试计算属性缓存"""
        count = Signal(0)
        computations = []
        
        def compute():
            computations.append(1)
            return count.value * 2
        
        double = Computed(compute)
        
        # 首次访问
        assert double.value == 0
        assert len(computations) == 1
        
        # 再次访问(应该使用缓存)
        assert double.value == 0
        assert len(computations) == 1
        
        # 值变化后重新计算
        count.value = 5
        assert double.value == 10
        assert len(computations) == 2


class TestBatch:
    """批量更新测试"""
    
    def test_batch_updates(self):
        """测试批量更新"""
        a = Signal(1)
        b = Signal(2)
        updates = []
        
        effect = Effect(lambda: updates.append((a.value, b.value)))
        
        assert updates == [(1, 2)]
        
        # 批量更新
        with batch():
            a.value = 10
            b.value = 20
            # 不应该立即触发effect
        
        # 退出批量后才触发
        assert updates == [(1, 2), (10, 20)]
    
    def test_nested_batch(self):
        """测试嵌套批量更新"""
        count = Signal(0)
        updates = []
        
        effect = Effect(lambda: updates.append(count.value))
        
        assert updates == [0]
        
        with batch():
            count.value = 1
            with batch():
                count.value = 2
            count.value = 3
        
        # 只触发一次
        assert updates == [0, 3]


class TestReactiveDict:
    """响应式字典测试"""
    
    def test_get_set(self):
        """测试获取和设置"""
        state = ReactiveDict()
        
        state.set("name", "Alice")
        assert state.get("name") == "Alice"
        
        state.set("age", 25)
        assert state.get("age") == 25
    
    def test_subscribe_key(self):
        """测试订阅特定key"""
        state = ReactiveDict()
        values = []
        
        state.subscribe("count", lambda v: values.append(v))
        
        state.set("count", 1)
        state.set("count", 2)
        
        assert values == [1, 2]
    
    def test_to_dict(self):
        """测试转换为字典"""
        state = ReactiveDict({"a": 1, "b": 2})
        
        result = state.to_dict()
        
        assert result == {"a": 1, "b": 2}


class TestReactiveList:
    """响应式列表测试"""
    
    def test_append(self):
        """测试追加元素"""
        items = ReactiveList()
        
        items.append(1)
        items.append(2)
        
        assert len(items) == 2
        assert items[0] == 1
        assert items[1] == 2
    
    def test_reactivity(self):
        """测试响应性"""
        items = ReactiveList()
        lengths = []
        
        effect = Effect(lambda: lengths.append(len(items)))
        
        items.append(1)
        items.append(2)
        
        assert lengths == [0, 1, 2]
    
    def test_remove(self):
        """测试移除元素"""
        items = ReactiveList([1, 2, 3])
        
        items.remove(2)
        
        assert len(items) == 2
        assert items.to_list() == [1, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])