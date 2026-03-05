# Web Frontend Architecture Guide

> 本文档为前端工程架构指导手册，采用多层渐进式结构，帮助开发者快速理解项目结构、定位功能模块。

## 📑 Quick Navigation

- [工程概述](#工程概述)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [功能模块详解](#功能模块详解)
- [核心配置](#核心配置)
- [开发指南](#开发指南)

---

## 工程概述

**项目名称**: derisk-web  
**项目类型**: Next.js 15 应用 (静态导出)  
**构建方式**: 静态导出 (output: 'export')  
**UI框架**: Ant Design 5 + Tailwind CSS  
**状态管理**: React Context + Hooks  
**国际化**: i18next  

---

## 技术栈

### 核心框架
- **Next.js**: 15.4.2 (App Router)
- **React**: 18.2.0
- **TypeScript**: 5.x

### UI & 样式
- **Ant Design**: 5.26.6 (主UI组件库)
- **Tailwind CSS**: 4.1.18 (样式工具)
- **@ant-design/icons**: 6.0.0
- **@ant-design/x**: 1.5.0 (AI对话组件)

### 数据可视化
- **@antv/g6**: 5.0.49 (图可视化)
- **@antv/gpt-vis**: 0.5.2 (GPT可视化组件)
- **@antv/ava**: 3.4.1 (自动图表)

### 状态与通信
- **Axios**: 1.10.0 (HTTP请求)
- **@microsoft/fetch-event-source**: 2.0.1 (SSE流式请求)
- **ahooks**: 3.9.0 (React Hooks工具集)

### 其他
- **reactflow**: 11.11.4 (流程图编辑器)
- **CodeMirror**: 6.x (代码编辑器)
- **markdown-it**: 14.1.0 (Markdown渲染)

---

## 目录结构

### 一级目录结构

```
web/
├── public/              # 静态资源
├── src/                 # 源代码
│   ├── app/             # Next.js App Router 页面
│   ├── client/          # API客户端层
│   ├── components/      # 可复用组件
│   ├── contexts/        # React Context 状态管理
│   ├── hooks/           # 自定义Hooks
│   ├── locales/         # 国际化资源
│   ├── services/        # 业务服务层
│   ├── styles/          # 全局样式
│   ├── types/           # TypeScript类型定义
│   └── utils/           # 工具函数
├── next.config.mjs      # Next.js配置
├── tsconfig.json        # TypeScript配置
├── tailwind.config.js   # Tailwind配置
└── package.json         # 项目依赖
```

### 详细目录树

<details>
<summary><b>📁 src/app - 页面路由结构</b></summary>

```
src/app/
├── layout.tsx              # 根布局 (全局Provider)
├── page.tsx                # 首页 (Chat主页)
├── not-found.tsx           # 404页面
├── i18n.ts                 # 国际化初始化
│
├── application/            # 【应用管理模块】
│   ├── page.tsx           # 应用列表
│   ├── layout.tsx         # 应用布局
│   ├── app/               # 应用详情页
│   │   ├── page.tsx
│   │   └── components/    # 应用详情组件
│   │       ├── chat-content.tsx
│   │       ├── agent-header.tsx
│   │       ├── tab-agents.tsx
│   │       ├── tab-knowledge.tsx
│   │       ├── tab-prompts.tsx
│   │       ├── tab-skills.tsx
│   │       └── tab-tools.tsx
│   └── explore/           # 应用探索页
│
├── chat/                   # 【独立对话页面】
│   └── page.tsx
│
├── knowledge/              # 【知识库管理】
│   ├── page.tsx           # 知识库列表
│   └── chunk/             # 知识块管理
│
├── prompt/                 # 【提示词管理】
│   ├── page.tsx
│   ├── layout.tsx
│   └── [type]/            # 动态路由 - 提示词详情
│
├── agent-skills/           # 【Agent技能管理】
│   ├── page.tsx           # 技能列表
│   └── detail/            # 技能详情
│
├── v2-agent/               # 【V2 Agent页面】
│   └── page.tsx
│
├── mcp/                    # 【MCP工具管理】
│   ├── page.tsx
│   ├── detail/
│   ├── CreatMcpModel.tsx
│   └── CustomUpload.tsx
│
├── models/                 # 【模型管理】
│   └── page.tsx
│
├── channel/                # 【渠道管理】
│   ├── page.tsx           # 渠道列表
│   ├── create/            # 创建渠道
│   ├── [id]/              # 编辑渠道 (动态路由)
│   └── components/        # 渠道组件
│
├── cron/                   # 【定时任务】
│   ├── page.tsx           # 任务列表
│   ├── create/            # 创建任务
│   ├── edit/              # 编辑任务
│   └── components/
│
├── settings/               # 【系统设置】
│   └── config/
│
└── vis-merge-test/         # 【可视化测试页】
    └── page.tsx
```
</details>

<details>
<summary><b>📁 src/components - 组件库</b></summary>

```
src/components/
├── layout/                 # 布局组件
│   ├── side-bar.tsx       # 侧边栏导航
│   ├── float-helper.tsx   # 浮动帮助
│   ├── user-bar.tsx       # 用户栏
│   └── menlist.tsx        # 菜单列表
│
├── chat/                   # 【对话组件模块】 ⭐核心模块
│   ├── content/           # 对话内容区
│   │   └── home-chat.tsx  # 首页对话容器
│   ├── input/             # 输入组件
│   ├── auto-chart/        # 自动图表生成
│   │   ├── advisor/       # 图表推荐算法
│   │   ├── charts/        # 图表类型实现
│   │   └── helpers/       # 辅助工具
│   └── chat-content-components/  # 对话内容子组件
│       ├── VisComponents/ # 可视化组件集合
│       │   ├── VisStepCard/
│       │   ├── VisMsgCard/
│       │   ├── VisLLM/
│       │   ├── VisCodeIde/
│       │   ├── VisMonitor/
│       │   ├── VisRunningWindow/
│       │   └── ... (20+组件)
│       └── ...
│
├── vis-merge/              # 可视化合并组件
├── blurred-card/           # 模糊卡片
└── agent-version-selector/ # Agent版本选择器
```
</details>

<details>
<summary><b>📁 src/client/api - API客户端</b></summary>

```
src/client/api/
├── index.ts                # API基础封装 (GET/POST/PUT/DELETE)
├── request.ts              # 请求工具
│
├── app/                    # 应用相关API
├── chat/                   # 对话相关API
│   └── index.ts           # 推荐问题、反馈、停止对话
├── flow/                   # 流程编排API
├── knowledge/              # 知识库API
├── prompt/                 # 提示词API
├── tools/                  # 工具API
│   ├── index.ts
│   ├── v2.ts
│   └── interceptors.ts
├── skill/                  # 技能API
├── cron/                   # 定时任务API
├── channel/                # 渠道API
├── evaluate/               # 评估API
└── v2/                     # V2版本API
```
</details>

<details>
<summary><b>📁 src/types - TypeScript类型定义</b></summary>

```
src/types/
├── global.d.ts            # 全局类型声明
├── app.ts                 # 应用类型 (IApp, AgentParams等)
├── agent.ts               # Agent类型 (IAgentPlugin, IMyPlugin等)
├── chat.ts                # 对话类型 (ChartData, SceneResponse等)
├── knowledge.ts           # 知识库类型
├── prompt.ts              # 提示词类型
├── model.ts               # 模型类型
├── flow.ts                # 流程编排类型
├── editor.ts              # 编辑器类型
├── evaluate.ts            # 评估类型
├── v2.ts                  # V2版本类型
├── db.ts                  # 数据库类型
├── userinfo.ts            # 用户信息类型
└── common.ts              # 通用类型
```
</details>

<details>
<summary><b>📁 src/contexts - 状态管理</b></summary>

```
src/contexts/
├── index.ts                     # 统一导出
├── app-context.tsx              # 应用全局状态
│   # - collapsed: 侧边栏折叠
│   # - appInfo: 应用信息
│   # - chatId: 会话ID
│   # - versionData: 版本数据
│
├── chat-context.tsx             # 对话上下文
│   # - mode: 主题模式 (light/dark)
│   # - 对话状态管理
│
└── chat-content-context.tsx     # 对话内容上下文
```
</details>

<details>
<summary><b>📁 src/utils - 工具函数</b></summary>

```
src/utils/
├── index.ts                # 工具函数统一入口
├── request.ts              # 请求封装
├── ctx-axios.ts            # Axios上下文封装
├── storage.ts              # 本地存储工具
├── markdown.ts             # Markdown处理
├── json.ts                 # JSON处理
├── graph.ts                # 图数据处理
├── fileUtils.ts            # 文件工具
├── dom.ts                  # DOM操作
├── event-emitter.ts        # 事件发射器
├── parse-vis.ts            # VIS协议解析器
│
└── constants/              # 常量定义
    ├── index.ts
    ├── storage.ts          # 存储键名
    ├── header.ts           # HTTP Header常量
    └── error-code.ts       # 错误码
```
</details>

---

## 功能模块详解

### 🏠 首页对话模块
**路径**: `src/app/page.tsx` → `src/components/chat/content/home-chat.tsx`

**功能**:
- 对话主界面
- 多轮对话
- 流式响应 (SSE)
- 自动图表生成

**关键组件**:
- `home-chat.tsx` - 主对话容器
- `input/` - 输入框组件
- `VisComponents/` - 消息可视化组件

---

### 📱 应用管理模块
**路径**: `src/app/application/`

**子功能**:
1. **应用列表** (`page.tsx`)
   - 应用创建、编辑、删除
   - 应用收藏、发布

2. **应用详情** (`app/page.tsx`)
   - Agent配置
   - 知识库关联
   - 提示词管理
   - 工具绑定
   - 技能管理

3. **应用探索** (`explore/page.tsx`)
   - 公开应用浏览

**关键类型**: `IApp`, `IDetail`, `ParamNeed` (src/types/app.ts)

---

### 💬 对话核心模块
**路径**: `src/components/chat/`

**架构设计**:
```
Chat Module
├── UI Layer (chat-content-components)
│   ├── 消息渲染 (VisMsgCard)
│   ├── 代码执行 (VisCodeIde)
│   ├── LLM调用 (VisLLM)
│   └── 图表展示 (VisStepCard)
│
├── Input Layer (input/)
│   └── 输入框、文件上传
│
└── Logic Layer
    ├── auto-chart/ - 自动图表
    └── hooks/use-chat.ts - 对话逻辑
```

**核心Hook**: `useChat` (src/hooks/use-chat.ts)
- 支持V1/V2 Agent版本
- SSE流式响应处理
- 错误处理与重试

---

### 📚 知识库模块
**路径**: `src/app/knowledge/`

**功能**:
- 知识库CRUD
- 文档上传与解析
- 知识块管理 (`chunk/`)
- 向量检索配置

**API**: `src/client/api/knowledge/`

---

### 🎯 提示词模块
**路径**: `src/app/prompt/`

**功能**:
- 提示词模板管理
- 场景分类
- 提示词测试

**API**: `src/client/api/prompt/`

---

### 🤖 Agent技能模块
**路径**: `src/app/agent-skills/`

**功能**:
- 技能市场
- 自定义技能上传
- 技能详情查看

**类型**: `IAgentPlugin`, `IMyPlugin` (src/types/agent.ts)

---

### 🛠️ MCP工具模块
**路径**: `src/app/mcp/`

**功能**:
- MCP工具管理
- 工具配置
- 工具测试

**组件**:
- `CreatMcpModel.tsx` - 创建MCP模型
- `CustomUpload.tsx` - 自定义上传

---

### ⏰ 定时任务模块
**路径**: `src/app/cron/`

**功能**:
- 定时任务创建
- 任务调度管理
- 执行日志查看

**组件**:
- `cron-form.tsx` - 任务表单

---

### 🔌 渠道管理模块
**路径**: `src/app/channel/`

**功能**:
- 多渠道配置 (飞书、钉钉等)
- 消息推送配置
- 渠道测试

**组件**:
- `channel-form.tsx` - 渠道表单

---

### 🎨 模型管理模块
**路径**: `src/app/models/`

**功能**:
- LLM模型配置
- 模型参数管理
- 模型测试

---

## 核心配置

### Next.js 配置
**文件**: `next.config.mjs`

```javascript
{
  transpilePackages: ['@antv/gpt-vis'],
  images: { unoptimized: true },
  output: 'export',           // 静态导出
  trailingSlash: true,
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true }
}
```

### TypeScript 配置
**文件**: `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "jsx": "preserve",
    "module": "esnext",
    "moduleResolution": "bundler",
    "paths": {
      "@/*": ["./src/*"]      // 路径别名
    }
  }
}
```

### Tailwind 配置
**文件**: `tailwind.config.js`

**主题色**:
- Primary: `#0069fe`
- Success: `#52C41A`
- Error: `#FF4D4F`
- Warning: `#FAAD14`

**暗色模式**: `darkMode: 'class'`

### 环境变量
**文件**: `.env.local` (需创建)

```bash
NEXT_PUBLIC_API_BASE_URL=http://your-api-server
```

---

## 开发指南

### 常用命令

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 启动生产服务
npm run start

# 代码检查
npm run lint
```

### 路径别名
使用 `@/` 作为 `src/` 的别名:
```typescript
import { something } from '@/components/...';
import { api } from '@/client/api';
```

### API调用示例
```typescript
import { GET, POST } from '@/client/api';

// GET请求
const response = await GET<ParamType, ResponseType>('/api/v1/resource', params);

// POST请求
const result = await POST<DataType, ResponseType>('/api/v1/resource', data);
```

### 对话Hook使用
```typescript
import useChat from '@/hooks/use-chat';

const { chat, ctrl } = useChat({ 
  queryAgentURL: '/api/v1/chat/completions',
  app_code: 'your-app-code',
  agent_version: 'v2'
});

// 发起对话
await chat({
  data: { user_input: '你好', conv_uid: 'session-id' },
  onMessage: (msg) => console.log(msg),
  onDone: () => console.log('完成'),
  onError: (err) => console.error(err)
});
```

### Context使用
```typescript
import { AppContext, ChatContext } from '@/contexts';

// 应用上下文
const { appInfo, chatId, collapsed } = useContext(AppContext);

// 对话上下文
const { mode } = useContext(ChatContext);
```

---

## 架构设计原则

### 1. 分层架构
```
Pages (app/) 
  → Components (components/)
    → Hooks (hooks/)
      → API Client (client/api/)
        → Types (types/)
```

### 2. 组件设计
- **容器组件**: 页面级，负责数据获取和状态管理
- **展示组件**: 可复用UI组件，只接收props
- **高阶组件**: 如Context Provider

### 3. 状态管理
- **全局状态**: Context (AppContext, ChatContext)
- **局部状态**: useState/useReducer
- **服务端状态**: 直接API调用

### 4. 样式方案
- **优先使用**: Tailwind CSS工具类
- **组件样式**: styled-components / CSS Modules
- **主题定制**: Ant Design ConfigProvider

---

## 快速定位指南

### 我想找到...

| 需求 | 路径 |
|------|------|
| 修改首页对话UI | `src/components/chat/content/home-chat.tsx` |
| 添加新的API接口 | `src/client/api/[module]/index.ts` |
| 修改侧边栏 | `src/components/layout/side-bar.tsx` |
| 添加新的消息类型组件 | `src/components/chat/chat-content-components/VisComponents/` |
| 修改应用配置逻辑 | `src/app/application/app/page.tsx` |
| 添加新的类型定义 | `src/types/[module].ts` |
| 修改对话逻辑 | `src/hooks/use-chat.ts` |
| 添加新的工具函数 | `src/utils/[filename].ts` |
| 修改国际化文案 | `src/locales/[lang]/[module].ts` |
| 修改主题样式 | `src/styles/globals.css` + `tailwind.config.js` |

---

## 常见问题

### Q: 如何添加新的页面路由?
A: 在 `src/app/` 下创建目录，添加 `page.tsx` 文件。

### Q: 如何添加新的API?
A: 
1. 在 `src/types/` 定义类型
2. 在 `src/client/api/` 对应模块添加函数
3. 导出至 `src/client/api/index.ts`

### Q: 如何添加全局状态?
A: 在 `src/contexts/` 创建新的Context，在 `layout.tsx` 中注入Provider。

### Q: 如何使用国际化?
A: 
```typescript
import { useTranslation } from 'react-i18next';
const { t } = useTranslation();
// 使用: t('key')
```

---

## 相关文档索引

- [Next.js 官方文档](https://nextjs.org/docs)
- [Ant Design 组件库](https://ant.design/components/overview-cn/)
- [Tailwind CSS 文档](https://tailwindcss.com/docs)
- [React Flow 文档](https://reactflow.dev/docs/)

---

**最后更新**: 2026-02-27  
**维护者**: Derisk Team