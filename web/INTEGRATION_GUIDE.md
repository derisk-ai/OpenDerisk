# 应用构建模块 - 场景集成说明

## ✅ 已完成

**场景 Tab 组件已创建完成！**

文件位置：`web/src/app/application/app/components/tab-scenes.tsx`

---

## 🔧 集成步骤

### 步骤 1: 导入场景 Tab 组件

在 `web/src/app/application/app/page.tsx` 文件中添加导入：

```typescript
// 在文件顶部的导入区域添加（第18行左右）
import TabScenes from './components/tab-scenes';
```

### 步骤 2: 在 renderTabContent 函数中添加场景 Tab

在 `renderTabContent` 函数中添加场景 Tab 的渲染逻辑：

```typescript
// 在 renderTabContent 函数中添加（第165行左右）
case 'scenes':
  return <TabScenes />;
```

### 步骤 3: 在 AgentHeader 中添加场景 Tab 标签

在 `web/src/app/application/app/components/agent-header.tsx` 中添加场景菜单项：

```typescript
// 在 tabs 数组中添加场景标签
{
  key: 'scenes',
  label: (
    <span className="flex items-center gap-1.5">
      <AppstoreOutlined className="text-purple-500" />
      <span>场景配置</span>
    </span>
  ),
}
```

---

## 📋 完整修改示例

### 1. page.tsx 修改

```typescript
// 文件：web/src/app/application/app/page.tsx

// 在顶部导入区域添加
import TabScenes from './components/tab-scenes';

// 在 renderTabContent 函数中添加
const renderTabContent = () => {
  if (!selectedAppCode || !appInfo?.app_code) return null;
  switch (activeTab) {
    case 'overview':
      return <TabOverview />;
    case 'prompts':
      return <TabPrompts />;
    case 'tools':
      return <TabTools />;
    case 'skills':
      return <TabSkills />;
    case 'scenes':          // ← 新增
      return <TabScenes />; // ← 新增
    case 'sub-agents':
      return <TabAgents />;
    case 'knowledge':
      return <TabKnowledge />;
    default:
      return <TabOverview />;
  }
};
```

### 2. agent-header.tsx 修改

```typescript
// 文件：web/src/app/application/app/components/agent-header.tsx

// 在 tabs 数组中添加
const tabs = [
  {
    key: 'overview',
    label: (
      <span className="flex items-center gap-1.5">
        <AppstoreOutlined className="text-blue-500" />
        <span>概览</span>
      </span>
    ),
  },
  {
    key: 'prompts',
    label: (
      <span className="flex items-center gap-1.5">
        <ThunderboltOutlined className="text-amber-500" />
        <span>提示词</span>
      </span>
    ),
  },
  {
    key: 'scenes',  // ← 新增
    label: (
      <span className="flex items-center gap-1.5">
        <AppstoreOutlined className="text-purple-500" />
        <span>场景配置</span>
      </span>
    ),
  },
  // ... 其他 tabs
];
```

---

## 🎯 功能特性

### 场景 Tab 提供的功能

1. **查看可用场景**
   - 显示所有已创建的场景
   - 显示场景详细信息（名称、描述、关键词、优先级）

2. **添加场景到应用**
   - 从下拉列表选择场景
   - 自动更新应用配置

3. **移除场景**
   - 一键移除已配置的场景
   - 自动更新应用配置

4. **查看场景详情**
   - 模态框展示完整场景信息
   - 包括角色设定、工具列表等

5. **使用说明**
   - 内置使用指南
   - 场景功能说明

---

## 🚀 使用流程

### 1. 创建场景

访问场景管理页面创建场景：

```
http://localhost:3000/scene
```

### 2. 在应用中配置场景

1. 进入应用详情页
2. 切换到"场景配置" Tab
3. 点击"添加场景"下拉框
4. 选择需要的场景
5. 场景会自动保存到应用配置中

### 3. 场景自动生效

Agent 运行时会：
- 根据用户输入自动识别场景
- 注入场景角色设定到 System Prompt
- 动态加载场景相关工具
- 按需切换场景

---

## 📊 数据流

```
用户创建场景 (/scene)
    ↓
场景保存到后端
    ↓
应用配置中引用场景
    ↓
Agent 运行时加载场景
    ↓
自动场景检测和切换
```

---

## 🎨 界面预览

### 场景 Tab 界面包括：

1. **标题栏**
   - 场景配置标题
   - 刷新按钮

2. **添加场景区**
   - 场景选择下拉框
   - 使用提示

3. **已配置场景列表**
   - 场景名称和 ID
   - 触发关键词
   - 优先级标签
   - 查看和移除按钮

4. **使用说明卡片**
   - 功能说明
   - 使用提示

---

## 💡 注意事项

1. **场景必须先创建**
   - 在使用前，需要在场景管理页面创建场景

2. **自动保存**
   - 场景配置会自动保存，无需手动保存

3. **实时生效**
   - 场景配置后立即生效，无需重启

4. **场景优先级**
   - 多个场景匹配时，优先级高的优先

---

## 🔗 相关文档

- [场景管理页面使用指南](../../SCENE_MODULE_GUIDE.md)
- [前端集成详细指南](../../../examples/scene_aware_agent/FRONTEND_INTEGRATION.md)
- [项目总结](../../../examples/scene_aware_agent/PROJECT_SUMMARY.md)

---

**完成时间**: 2026-03-04
**版本**: 1.0.0
**状态**: ✅ 组件已创建，待集成

---

## ⚡ 快速集成命令

如果您想快速集成，可以执行以下修改：

```bash
# 1. 在 page.tsx 添加导入
# 2. 在 renderTabContent 添加 case
# 3. 在 agent-header.tsx 添加 tab
```

集成完成后，访问任意应用详情页即可看到"场景配置" Tab！