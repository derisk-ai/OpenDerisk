# 场景管理前端集成指南

## 概述

本文档提供场景管理功能的前端集成方案，包括场景管理页面、MD 编辑器组件和场景引用管理。

## 技术栈建议

- **框架**: React 18+ / Vue 3+
- **UI 库**: Ant Design / Material-UI / shadcn/ui
- **编辑器**: Monaco Editor / CodeMirror / react-markdown-editor-lite
- **状态管理**: Zustand / Redux / Pinia
- **HTTP 客户端**: axios / fetch

---

## 组件架构

```
SceneManagement/
├── SceneList/          # 场景列表组件
├── SceneEditor/        # 场景编辑器组件
├── MDEditor/          # Markdown 编辑器
├── ScenePreview/      # 场景预览组件
└── SceneReference/    # 场景引用管理组件
```

---

## 核心组件实现

### 1. 场景列表组件

```typescript
// SceneList.tsx
import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';

interface Scene {
  scene_id: string;
  scene_name: string;
  description: string;
  trigger_keywords: string[];
  trigger_priority: number;
  created_at: string;
  updated_at: string;
}

export const SceneList: React.FC = () => {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadScenes();
  }, []);

  const loadScenes = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/scenes');
      const data = await response.json();
      setScenes(data);
    } catch (error) {
      message.error('加载场景失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (sceneId: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个场景吗？',
      onOk: async () => {
        try {
          await fetch(`/api/scenes/${sceneId}`, { method: 'DELETE' });
          message.success('删除成功');
          loadScenes();
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  const columns = [
    { title: '场景 ID', dataIndex: 'scene_id', key: 'scene_id' },
    { title: '场景名称', dataIndex: 'scene_name', key: 'scene_name' },
    { title: '描述', dataIndex: 'description', key: 'description' },
    { 
      title: '触发关键词', 
      dataIndex: 'trigger_keywords', 
      key: 'trigger_keywords',
      render: (keywords: string[]) => keywords.join(', ')
    },
    { title: '优先级', dataIndex: 'trigger_priority', key: 'trigger_priority' },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Scene) => (
        <div>
          <Button icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button 
            icon={<DeleteOutlined />} 
            danger 
            onClick={() => handleDelete(record.scene_id)}
          >
            删除
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />}>
          新建场景
        </Button>
      </div>
      <Table 
        dataSource={scenes} 
        columns={columns} 
        loading={loading}
        rowKey="scene_id"
      />
    </div>
  );
};
```

### 2. Markdown 编辑器组件

```typescript
// MDEditor.tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Tabs } from 'antd';

interface MDEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  height?: number;
}

export const MDEditor: React.FC<MDEditorProps> = ({
  value,
  onChange,
  placeholder = '请输入 Markdown 内容',
  height = 400,
}) => {
  return (
    <div style={{ border: '1px solid #d9d9d9', borderRadius: 4 }}>
      <Tabs defaultActiveKey="edit">
        <Tabs.TabPane tab="编辑" key="edit">
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            style={{
              width: '100%',
              height: height,
              padding: 12,
              border: 'none',
              outline: 'none',
              resize: 'vertical',
              fontFamily: 'monospace',
            }}
          />
        </Tabs.TabPane>
        <Tabs.TabPane tab="预览" key="preview">
          <div style={{ padding: 12, height: height, overflow: 'auto' }}>
            <ReactMarkdown>{value || '*暂无内容*'}</ReactMarkdown>
          </div>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};
```

### 3. 场景编辑器组件

```typescript
// SceneEditor.tsx
import React, { useState } from 'react';
import { Form, Input, InputNumber, Button, Select, message } from 'antd';
import { MDEditor } from './MDEditor';

interface SceneEditorProps {
  sceneId?: string;
  onSave: () => void;
  onCancel: () => void;
}

export const SceneEditor: React.FC<SceneEditorProps> = ({
  sceneId,
  onSave,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const [mdContent, setMdContent] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      const url = sceneId ? `/api/scenes/${sceneId}` : '/api/scenes';
      const method = sceneId ? 'PUT' : 'POST';
      
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...values,
          md_content: mdContent,
        }),
      });
      
      message.success('保存成功');
      onSave();
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSubmit}>
      <Form.Item name="scene_id" label="场景 ID" rules={[{ required: true }]}>
        <Input placeholder="例如：fault_diagnosis" disabled={!!sceneId} />
      </Form.Item>
      
      <Form.Item name="scene_name" label="场景名称" rules={[{ required: true }]}>
        <Input placeholder="例如：故障诊断" />
      </Form.Item>
      
      <Form.Item name="description" label="场景描述">
        <Input.TextArea rows={3} placeholder="详细描述场景用途..." />
      </Form.Item>
      
      <Form.Item name="trigger_keywords" label="触发关键词">
        <Select 
          mode="tags" 
          placeholder="输入关键词后按回车"
        />
      </Form.Item>
      
      <Form.Item name="trigger_priority" label="优先级" initialValue={5}>
        <InputNumber min={1} max={10} />
      </Form.Item>
      
      <Form.Item label="场景定义 (Markdown)">
        <MDEditor
          value={mdContent}
          onChange={setMdContent}
          placeholder="使用 Markdown 格式定义场景..."
          height={300}
        />
      </Form.Item>
      
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={loading}>
          保存
        </Button>
        <Button style={{ marginLeft: 8 }} onClick={onCancel}>
          取消
        </Button>
      </Form.Item>
    </Form>
  );
};
```

---

## API 集成

### HTTP 客户端配置

```typescript
// api/scenes.ts
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

export const sceneApi = {
  list: () => api.get('/scenes'),
  get: (id: string) => api.get(`/scenes/${id}`),
  create: (data: any) => api.post('/scenes', data),
  update: (id: string, data: any) => api.put(`/scenes/${id}`, data),
  delete: (id: string) => api.delete(`/scenes/${id}`),
  activate: (sessionId: string, agentId: string) => 
    api.post('/scenes/activate', { session_id: sessionId, agent_id: agentId }),
  switch: (sessionId: string, fromScene: string, toScene: string, reason: string) =>
    api.post('/scenes/switch', { 
      session_id: sessionId, 
      from_scene: fromScene, 
      to_scene: toScene, 
      reason 
    }),
  history: (sessionId: string) => api.get(`/scenes/history/${sessionId}`),
};
```

---

## 场景引用管理

### 在 Agent Prompt 中维护场景引用

```typescript
// SceneReferenceManager.ts
import { sceneApi } from './api/scenes';

export class SceneReferenceManager {
  /**
   * 构建 Agent System Prompt
   */
  async buildSystemPrompt(
    basePrompt: string,
    currentSceneId: string | null
  ): Promise<string> {
    let prompt = basePrompt;
    
    if (currentSceneId) {
      try {
        const response = await sceneApi.get(currentSceneId);
        const scene = response.data;
        
        // 添加场景特定提示词
        prompt += `\n\n# 当前场景\n\n`;
        prompt += `## ${scene.scene_name}\n\n`;
        prompt += `${scene.description}\n\n`;
        
        if (scene.scene_role_prompt) {
          prompt += `## 场景角色设定\n\n${scene.scene_role_prompt}\n\n`;
        }
        
        if (scene.trigger_keywords.length > 0) {
          prompt += `## 触发关键词\n\n${scene.trigger_keywords.join(', ')}\n\n`;
        }
      } catch (error) {
        console.error('Failed to load scene for prompt:', error);
      }
    }
    
    return prompt;
  }
  
  /**
   * 获取可用场景列表
   */
  async getAvailableScenes(): Promise<any[]> {
    try {
      const response = await sceneApi.list();
      return response.data;
    } catch (error) {
      console.error('Failed to load scenes:', error);
      return [];
    }
  }
  
  /**
   * 检测场景切换
   */
  async detectSceneSwitch(
    userInput: string,
    currentSceneId: string | null
  ): Promise<{ shouldSwitch: boolean; targetScene?: string }> {
    const scenes = await this.getAvailableScenes();
    
    // 简单的关键词匹配
    for (const scene of scenes) {
      if (scene.scene_id === currentSceneId) continue;
      
      for (const keyword of scene.trigger_keywords) {
        if (userInput.toLowerCase().includes(keyword.toLowerCase())) {
          return {
            shouldSwitch: true,
            targetScene: scene.scene_id,
          };
        }
      }
    }
    
    return { shouldSwitch: false };
  }
}
```

---

## 路由配置

```typescript
// routes.tsx
import { Route, Routes } from 'react-router-dom';
import { SceneList } from './components/SceneList';
import { SceneEditor } from './components/SceneEditor';

export const SceneRoutes = () => (
  <Routes>
    <Route path="/scenes" element={<SceneList />} />
    <Route path="/scenes/create" element={<SceneEditor />} />
    <Route path="/scenes/:id/edit" element={<SceneEditor />} />
  </Routes>
);
```

---

## 状态管理

### 使用 Zustand（推荐）

```typescript
// store/sceneStore.ts
import { create } from 'zustand';

interface SceneState {
  scenes: any[];
  currentScene: string | null;
  loading: boolean;
  loadScenes: () => Promise<void>;
  setCurrentScene: (sceneId: string | null) => void;
}

export const useSceneStore = create<SceneState>((set) => ({
  scenes: [],
  currentScene: null,
  loading: false,
  
  loadScenes: async () => {
    set({ loading: true });
    try {
      const response = await fetch('/api/scenes');
      const data = await response.json();
      set({ scenes: data, loading: false });
    } catch (error) {
      set({ loading: false });
    }
  },
  
  setCurrentScene: (sceneId) => set({ currentScene: sceneId }),
}));
```

---

## 部署注意事项

1. **API 代理配置**：
   ```nginx
   location /api/scenes {
       proxy_pass http://backend:8000;
       proxy_set_header Host $host;
   }
   ```

2. **环境变量**：
   ```env
   REACT_APP_API_BASE_URL=http://localhost:8000
   ```

3. **构建优化**：
   ```json
   {
     "scripts": {
       "build": "vite build --mode production",
       "preview": "vite preview"
     }
   }
   ```

---

**创建时间**: 2026-03-04
**版本**: 1.0.0