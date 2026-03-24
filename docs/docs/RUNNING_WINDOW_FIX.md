# Running Window 修复总结

## 问题描述

在 vis_window3 布局下，当用户在 running window 中进行追问（follow-up questions）时，AgentFolder 组件中的数据没有追加更新，用户看不到后续对话的内容。

## 问题分析

### 1. 后端问题（根本原因）
- `_running_vis_build` 方法只在 `is_first_push=True` 时构建 `main_agent_folder`
- 追问时（`is_first_push=False`），`main_agent_folder` 为 `None`
- 导致 `WorkSpaceContent` 的 `explorer` 字段为空
- 前端没有收到 AgentFolder 的数据，无法显示目录结构

### 2. 前端数据处理
- RunningWindowV2 使用 `data.explorer` 显示左侧目录（AgentFolder）
- 使用 `data.items` 显示右侧内容
- VIS 协议支持增量更新（type=INCR）和全量更新（type=ALL）

## 修复内容

### 后端修复（✅ 已应用）
**文件**: `packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_window3_converter.py`

**修改**: `_running_vis_build` 方法（第 1164-1197 行）

**变更**:
```python
# 修改前
main_agent_folder = None
if is_first_push:
    logger.info("构建vis_window3空间，进行首次资源管理器刷新!")
    main_agent_folder = await self._build_agent_folder(main_agent=main_agent)
    file_system_folder = await self._build_file_system_folder(...)

# 修改后
# 🔧 修复：每次都构建 agent folder，确保 explorer 始终存在
# 这样追问时也能正确更新 AgentFolder 数据
main_agent_folder = await self._build_agent_folder(main_agent=main_agent)

if is_first_push:
    logger.info("构建vis_window3空间，进行首次资源管理器刷新!")
    file_system_folder = await self._build_file_system_folder(...)
```

**原因**: 
- 前端需要 `explorer` 始终存在来显示目录结构
- AgentFolder 使用增量更新模式（type=INCR），空 items 会保留原有数据
- 确保追问时也能正确渲染目录树

### 2. 数据关联

**数据结构**:
- `WorkSpaceContent.explorer`: AgentFolder 的 vis 文本（目录树）
- `WorkSpaceContent.items`: FolderNode 列表（任务列表）

**关联逻辑**:
- `gen_work_item` 创建的 item 的 `path` = `{conv_session_id}_{agent_app_code}`
- `_build_agent_folder` 创建的 folder 的 `uid` = `{conv_session_id}_{agent_app_code}`
- 两者匹配，任务应该挂载到对应的 folder 下

**目录结构**:
```
Root Folder (uid: conv_session_id_main_app_code)
├── Sub Folder 1 (uid: conv_session_id_sub_app_code_1)
│   └── items with path = conv_session_id_sub_app_code_1
├── Sub Folder 2 (uid: conv_session_id_sub_app_code_2)
│   └── items with path = conv_session_id_sub_app_code_2
└── ...
```

## 验证步骤

1. **启动服务**: 重新启动后端服务以应用修改
2. **运行测试**: 使用 PDCA Agent 执行一个任务
3. **检查 running window**: 
   - 左侧应该显示目录结构（explorer）
   - 右侧应该显示任务内容（items）
   - 点击左侧目录项应该切换右侧显示

## 可能的问题

如果修复后仍有问题，可能原因：

1. **路径不匹配**: item 的 path 和 folder 的 uid 不匹配
2. **前端渲染问题**: VisAgentFolder 或 RunningWindowV2 组件没有正确处理数据
3. **数据格式问题**: WorkSpaceContent 或 FolderNode 字段不正确

## 调试建议

1. 在后端添加日志，打印 `main_agent_folder` 和 `work_items` 的内容
2. 在前端添加日志，打印 `data.explorer` 和 `data.items` 的内容
3. 检查浏览器控制台是否有错误信息
4. 使用 VIS 合并测试页面验证数据结构
