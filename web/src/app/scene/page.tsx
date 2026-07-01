'use client';

import React, { useState, useCallback, useRef } from 'react';
import { Typography, Button, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { SceneList, SceneListRef } from '@/components/scene/SceneList';
import { SceneEditor } from '@/components/scene/SceneEditor';
import '@/components/scene/scene-blueprint.css';

type PageMode = 'list' | 'create' | 'edit';

export default function ScenePage() {
  const [mode, setMode] = useState<PageMode>('list');
  const [currentSceneId, setCurrentSceneId] = useState<string | undefined>();
  const sceneListRef = useRef<SceneListRef>(null);

  const handleCreate = useCallback(() => {
    setMode('create');
    setCurrentSceneId(undefined);
  }, []);

  const handleEdit = useCallback((sceneId: string) => {
    setMode('edit');
    setCurrentSceneId(sceneId);
  }, []);

  const handleSave = useCallback(() => {
    setMode('list');
    setCurrentSceneId(undefined);
    message.success(mode === 'create' ? '场景已创建' : '场景已更新');
    sceneListRef.current?.refresh();
  }, [mode]);

  const handleCancel = useCallback(() => {
    setMode('list');
    setCurrentSceneId(undefined);
  }, []);

  if (mode === 'list') {
    return (
      <div className="bp-root" style={{ padding: 32 }}>
        <header className="bp-header">
          <p className="bp-eyebrow">SCENES</p>
          <h1 className="bp-title">场景管理</h1>
          <p className="bp-subtitle">管理和配置 AI 场景，从触发源到产出物。</p>
        </header>
        <SceneList ref={sceneListRef} onCreate={handleCreate} onEdit={handleEdit} />
      </div>
    );
  }

  return (
    <div className="bp-root" style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={handleCancel}
          className="bp-btn-ghost"
        >
          返回列表
        </Button>
      </div>
      <SceneEditor sceneId={currentSceneId} onSave={handleSave} onCancel={handleCancel} />
    </div>
  );
}
