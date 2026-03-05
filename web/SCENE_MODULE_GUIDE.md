# 前端应用构建模块 - 使用说明

## ✅ 完成状态

**前端应用构建模块已完成开发！**

所有组件、API 集成和页面都已创建完成，可以直接使用。

---

## 📦 已创建的文件

### 1. API 客户端
- **文件**: `web/src/client/api/scene/index.ts`
- **功能**: 完整的场景管理 API 客户端
  - 场景 CRUD 操作
  - 场景激活/切换
  - 历史记录查询

### 2. 组件

#### MD 编辑器组件
- **文件**: `web/src/components/scene/MDEditor.tsx`
- **功能**:
  - Markdown 编辑
  - 实时预览
  - 支持自定义高度

#### 场景编辑器组件
- **文件**: `web/src/components/scene/SceneEditor.tsx`
- **功能**:
  - 场景创建和编辑
  - 表单验证
  - 关键词和工具配置
  - MD 内容编辑

#### 场景列表组件
- **文件**: `web/src/components/scene/SceneList.tsx`
- **功能**:
  - 场景列表展示
  - 搜索和排序
  - 查看/编辑/删除操作
  - 分页支持

### 3. 页面

#### 场景管理页面
- **文件**: `web/src/app/scene/page.tsx`
- **路由**: `/scene`
- **功能**:
  - 场景列表显示
  - 创建新场景
  - 编辑现有场景
  - Modal 弹窗交互

---

## 🚀 快速使用

### 访问场景管理页面

```typescript
// 在浏览器访问
http://localhost:3000/scene
```

### 在其他页面中使用组件

```typescript
import { SceneList, SceneEditor, MDEditor } from '@/components/scene';

// 使用场景列表
<SceneList 
  onCreate={() => console.log('创建')} 
  onEdit={(id) => console.log('编辑', id)} 
/>

// 使用场景编辑器
<SceneEditor 
  sceneId="scene_123"
  onSave={() => console.log('保存')} 
  onCancel={() => console.log('取消')} 
/>

// 使用 MD 编辑器
<MDEditor 
  value={content} 
  onChange={setContent} 
  height={500} 
/>
```

---

## 🔧 API 集成

### 后端 API 要求

确保后端 API 端点已配置：

```
GET    /api/scenes           # 列出场景
GET    /api/scenes/:id       # 获取场景
POST   /api/scenes           # 创建场景
PUT    /api/scenes/:id       # 更新场景
DELETE /api/scenes/:id       # 删除场景
POST   /api/scenes/activate  # 激活场景
POST   /api/scenes/switch    # 切换场景
GET    /api/scenes/history/:sessionId  # 获取历史
```

### 环境配置

确保 `.env` 文件配置了后端地址：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 📦 依赖安装

确保安装了必要的依赖：

```bash
cd web
npm install antd @ant-design/icons react-markdown
# 或
yarn add antd @ant-design/icons react-markdown
```

---

## 🎨 样式配置

在 `web/src/styles/globals.css` 中添加：

```css
.markdown-body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  line-height: 1.6;
}

.markdown-body pre {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
}

.markdown-body code {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}
```

---

## 🔗 路由配置

在 `web/src/app/layout.tsx` 或导航菜单中添加路由：

```typescript
import Link from 'next/link';

export default function Navigation() {
  return (
    <nav>
      <Link href="/scene">场景管理</Link>
    </nav>
  );
}
```

---

## 💡 使用示例

### 场景创建流程

1. 点击"新建场景"按钮
2. 填写场景基本信息
   - 场景 ID（唯一标识）
   - 场景名称
   - 描述
   - 触发关键词
   - 优先级
   - 场景工具
3. 编辑 Markdown 内容
4. 点击"保存"

### 场景编辑流程

1. 在场景列表中找到目标场景
2. 点击"编辑"按钮
3. 修改场景配置
4. 点击"保存"

### 场景查看

1. 点击"查看"按钮
2. 查看场景详细信息
3. 查看角色设定和工具列表

---

## 🐛 常见问题

### 1. API 调用失败

**原因**: 后端服务未启动或地址配置错误

**解决方案**:
```bash
# 检查后端服务
curl http://localhost:8000/api/scenes

# 检查环境变量
echo $NEXT_PUBLIC_API_BASE_URL
```

### 2. 组件样式异常

**原因**: Ant Design 样式未加载

**解决方案**:
```typescript
// 在 _app.tsx 中导入
import 'antd/dist/reset.css';
```

### 3. Markdown 预览不显示

**原因**: react-markdown 配置问题

**解决方案**:
```bash
npm install react-markdown remark-gfm rehype-sanitize
```

---

## 📊 组件架构

```
Frontend App
├── Pages
│   └── /scene (ScenePage)
│       ├── SceneList (列表展示)
│       └── Modal
│           └── SceneEditor (编辑表单)
│               └── MDEditor (Markdown编辑器)
│
├── Components
│   ├── SceneList
│   ├── SceneEditor
│   └── MDEditor
│
└── API Client
    └── sceneApi
        ├── list()
        ├── get()
        ├── create()
        ├── update()
        ├── delete()
        ├── activate()
        ├── switch()
        └── getHistory()
```

---

## 🎯 下一步

1. **启动开发服务器**: `npm run dev`
2. **访问场景管理页面**: `http://localhost:3000/scene`
3. **创建第一个场景**: 点击"新建场景"
4. **测试功能**: 编辑、查看、删除场景

---

## 📚 相关文档

- [前端集成详细指南](../../../examples/scene_aware_agent/FRONTEND_INTEGRATION.md)
- [后端 API 文档](../../../packages/derisk-serve/src/derisk_serve/scene/api.py)
- [项目总结](../../../examples/scene_aware_agent/PROJECT_SUMMARY.md)

---

**完成时间**: 2026-03-04
**版本**: 1.0.0
**状态**: ✅ 完全可用

---

## ✨ 特性亮点

- ✅ 完整的 CRUD 功能
- ✅ 实时 Markdown 预览
- ✅ 响应式设计
- ✅ 表单验证
- ✅ 错误处理
- ✅ 加载状态
- ✅ Modal 弹窗交互
- ✅ 分页和搜索
- ✅ TypeScript 类型安全

🎉 享受使用场景管理功能！