# 场景化 Agent 架构 - 单元测试示例

## 测试概述

本文档提供场景化 Agent 架构的单元测试示例。

## 测试框架

使用 `pytest` 作为测试框架。

## 测试示例

### 1. 测试 MD 解析器

```python
import pytest
from derisk.agent.core_v2.scene_definition_parser import SceneDefinitionParser
from derisk.agent.core_v2.scene_definition import AgentRoleDefinition, SceneDefinition

@pytest.mark.asyncio
async def test_parse_agent_role():
    """测试解析 Agent 角色定义"""
    parser = SceneDefinitionParser()
    
    # 使用实际的 MD 文件路径
    md_path = "examples/scene_aware_agent/sre_diagnostic/agent-role.md"
    
    role_def = await parser.parse_agent_role(md_path)
    
    assert role_def is not None
    assert role_def.name == "SRE诊断助手"
    assert len(role_def.core_capabilities) > 0
    assert len(role_def.available_scenes) > 0

@pytest.mark.asyncio
async def test_parse_scene_definition():
    """测试解析场景定义"""
    parser = SceneDefinitionParser()
    
    md_path = "examples/scene_aware_agent/sre_diagnostic/scenes/scene-fault-diagnosis.md"
    
    scene_def = await parser.parse_scene_definition(md_path)
    
    assert scene_def is not None
    assert scene_def.scene_id == "fault_diagnosis"
    assert len(scene_def.trigger_keywords) > 0
    assert scene_def.trigger_priority > 0
```

### 2. 测试场景切换检测器

```python
import pytest
from derisk.agent.core_v2.scene_switch_detector import SceneSwitchDetector, SessionContext
from derisk.agent.core_v2.scene_definition import SceneDefinition, SceneTriggerType

def test_keyword_match():
    """测试关键词匹配"""
    # 创建测试场景
    scene_def = SceneDefinition(
        scene_id="test_scene",
        scene_name="测试场景",
        trigger_keywords=["测试", "test"],
        trigger_type=SceneTriggerType.KEYWORD,
    )
    
    detector = SceneSwitchDetector(available_scenes=[scene_def])
    
    # 测试关键词匹配
    result = detector._keyword_match("这是一个测试输入")
    
    assert result.scene_id == "test_scene"
    assert result.confidence > 0
    assert "测试" in result.matched_keywords
```

### 3. 测试场景运行时管理器

```python
import pytest
from derisk.agent.core_v2.scene_runtime_manager import SceneRuntimeManager
from derisk.agent.core_v2.scene_definition import AgentRoleDefinition, SceneDefinition

def test_build_system_prompt():
    """测试构建 System Prompt"""
    # 创建测试数据
    agent_role = AgentRoleDefinition(
        name="测试Agent",
        core_capabilities=["能力1", "能力2"]
    )
    
    scene_def = SceneDefinition(
        scene_id="test_scene",
        scene_name="测试场景",
        scene_role_prompt="这是场景角色设定"
    )
    
    manager = SceneRuntimeManager(
        agent_role=agent_role,
        scene_definitions={"test_scene": scene_def}
    )
    
    # 构建提示词
    prompt = manager.build_system_prompt("test_scene")
    
    assert "测试Agent" in prompt
    assert "能力1" in prompt
    assert "场景角色设定" in prompt
```

### 4. 测试工具注入器

```python
import pytest
from derisk.agent.core_v2.tool_injector import ToolInjector
from derisk.agent.core_v2.tools_v2 import ToolRegistry

@pytest.mark.asyncio
async def test_inject_tools():
    """测试工具注入"""
    registry = ToolRegistry()
    injector = ToolInjector(registry)
    
    # 注入工具
    count = await injector.inject_scene_tools(
        session_id="test_session",
        tool_names=["read", "write", "grep"]
    )
    
    assert count > 0
    
    # 检查已注入工具
    injected = injector.get_injected_tools("test_session")
    assert "read" in injected
```

### 5. 测试钩子执行引擎

```python
import pytest
from derisk.agent.core_v2.hook_executor import HookExecutor

@pytest.mark.asyncio
async def test_execute_hook():
    """测试钩子执行"""
    executor = HookExecutor()
    
    # 注册测试钩子
    async def test_hook(agent, context):
        return {"result": "test"}
    
    executor.register_hook("test_hook", test_hook)
    
    # 执行钩子
    result = await executor.execute_hook("test_hook", None, {})
    
    assert result is not None
    assert result["result"] == "test"
```

## 运行测试

```bash
# 运行所有测试
pytest tests/scene_aware_agent/

# 运行特定测试
pytest tests/scene_aware_agent/test_parser.py -v

# 生成测试覆盖率报告
pytest --cov=derisk.agent.core_v2 tests/scene_aware_agent/
```

---

**创建时间**: 2026-03-04
**版本**: 1.0.0