# DeriskIncrVisWindow3Converter 修复总结

## 问题描述
PDCA Agent 使用 DeriskIncrVisWindow3Converter 布局模式时，planning window 区域出现以下问题：
1. stage 类型的任务丢失，没有正确展示
2. stage 被挂在多个相同的根节点下
3. todolist 组件被嵌套在 stage 中

## 根本原因
1. **parent_id 设置错误**: PDCA Agent 中创建 stage 节点时，parent_id 设置为自己（stage_id），导致 stage 成为孤立节点
2. **数据格式不匹配**: 后端使用 `parent_id` 字段，但前端期望 `parent_uid` 字段
3. **数据嵌套错误**: action 内容被包装成独立的 `<d-agent-plan>` 节点嵌套在 stage 中
4. **todolist 位置错误**: todolist 内容作为 stage 的 markdown 嵌入，应该独立显示

## 修复内容

### 1. 修复 stage 节点的 parent_id (pdca_agent.py:172-183)
**修改前:**
```python
if current_stage:
    reply_message.goal_id = current_stage.stage_id
    # reply_message.goal_id 同时用于设置 parent_id，导致 stage 成为自己的父节点
```

**修改后:**
```python
if current_stage:
    reply_message.goal_id = current_stage.stage_id
    # stage 的 parent_id 应该是 agent task 节点 (received_message.message_id)
    await self.memory.gpts_memory.upsert_task(
        task=TreeNodeData(
            node_id=current_stage.stage_id,
            parent_id=received_message.message_id,  # 正确设置父节点
            ...
        )
    )
```

### 2. 添加 parent_uid 字段支持 (derisk_plan.py:22)
**新增字段:**
```python
class AgentPlanItem(DrskVisBase):
    parent_uid: Optional[str] = Field(
        None, description="父节点UID，用于前端构建树形结构"
    )
```

### 3. 设置 parent_uid 字段 (derisk_vis_window3_converter.py)
**在 _gen_plan_tree_by_task:**
```python
current_item = AgentPlanItem(
    uid=current_task.node_id,
    parent_uid=current_task.parent_id,  # 添加父节点UID
    ...
)
```

**在 _unpack_task_space:**
```python
return AgentPlanItem(
    uid=task_space.node_id,
    parent_uid=task_space.parent_id,  # 添加父节点UID
    ...
)
```

### 4. 修复数据返回格式 (derisk_vis_window3_converter.py:503-529)
**优化前:** 所有节点嵌套在 PlanningSpace 的 markdown 中

**优化后:**
```python
# PlanningSpace 容器 + 独立的 AgentPlan 节点
planning_window_content = PlanningSpaceContent(
    uid=f"{conv_id}_planning",
    todolist=todolist_vis,  # todolist 独立放置
    markdown=None,  # 子节点不在 markdown 中嵌套
)
# 返回容器 + 所有独立节点
return planning_space_vis + "\n" + "\n".join(task_items_vis)
```

### 5. 特殊处理 todolist (derisk_vis_window3_converter.py:402-438)
**提取 todolist 内容:**
```python
todolist_vis = None
# 从 create_kanban action 提取
todolist_content = action_out.simple_view or action_out.view or action_out.content
```

**排除 todolist 从 stage markdown:**
```python
def _act_out_2_plan(self, action_out, layer_count):
    if action_out.action == "create_kanban":
        # todolist 不嵌入到 stage，返回空字符串
        return ""
```

### 6. 过滤空字符串 (derisk_vis_window3_converter.py:289-293)
```python
if action_outs:
    for action_out in action_outs:
        plan_item = self._act_out_2_plan(action_out, layer_count)
        if plan_item:  # 过滤空字符串
            plan_tasks_vis.append(plan_item)
```

## 效果验证

### 修复前
```
PlanningSpace (root)
  └── Stage (错误挂载)
      ├── Content
      ├── Tool
      └── Todolist (嵌套在 stage 中)
```

### 修复后
```
PlanningSpace (container)
├── Todolist (独立显示在 agent 信息后)
├── Agent-Task (parent_uid=null)
│   ├── Stage-1 (parent_uid=agent-task-id)
│   │   ├── Content
│   │   └── Tool
│   └── Stage-2 (parent_uid=agent-task-id)
│       ├── Content
│       └── Tool
```

## 关键改进
1. ✅ stage 正确显示在 agent task 节点下
2. ✅ 不再重复挂载到根节点
3. ✅ todolist 独立显示，不嵌套在 stage 中
4. ✅ tool 和 content 正确展示在对应 stage 下
5. ✅ 前端根据 parent_uid 正确构建树形结构

## 修改文件列表
1. `packages/derisk-core/src/derisk/agent/expand/pdca_agent/pdca_agent.py`
2. `packages/derisk-ext/src/derisk_ext/vis/common/tags/derisk_plan.py`
3. `packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_window3_converter.py`

## 注意事项
- PlanningSpace 容器仍然需要，因为它包含 agent 信息（avatar、name 等）
- todolist 现在作为 PlanningSpace 的独立字段，不是 markdown 的一部分
- 前端需要支持根据 `parent_uid` 智能挂载节点
