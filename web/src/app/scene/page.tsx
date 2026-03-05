'use client';

import React, { useState, useCallback, useRef } from 'react';
import { Typography, Card, Button, message } from 'antd';
import {
  PlusOutlined,
  ArrowLeftOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { SceneList, SceneListRef } from '@/components/scene/SceneList';
import { SceneEditor } from '@/components/scene/SceneEditor';

const { Title } = Typography;

type PageMode = 'list' | 'create' | 'edit';

/**
 * 场景管理页面
 * 采用沉浸式布局，将表单直接融合到页面中
 */
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
    message.success(mode === 'create' ? '场景创建成功' : '场景更新成功');
    // 刷新列表
    sceneListRef.current?.refresh();
  }, [mode]);

  const handleCancel = useCallback(() => {
    setMode('list');
    setCurrentSceneId(undefined);
  }, []);

  const getPageTitle = () => {
    switch (mode) {
      case 'create':
        return '新建场景';
      case 'edit':
        return '编辑场景';
      default:
        return '场景管理';
    }
  };

  const getPageDescription = () => {
    switch (mode) {
      case 'create':
        return '创建一个新的场景定义，配置触发条件和行为规则';
      case 'edit':
        return '修改场景的配置信息和行为定义';
      default:
        return '管理和配置 AI 场景，设置触发条件和响应行为';
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* 页面标题区域 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
          {mode !== 'list' && (
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={handleCancel}
              size="large"
            >
              返回列表
            </Button>
          )}
          <Title level={2} style={{ margin: 0 }}>
            {getPageTitle()}
          </Title>
        </div>
        <Typography.Text type="secondary" style={{ fontSize: 14, marginLeft: mode !== 'list' ? 64 : 0 }}>
          {getPageDescription()}
        </Typography.Text>
      </div>

      {/* 列表模式 */}
      {mode === 'list' && (
        <SceneList
          ref={sceneListRef}
          onCreate={handleCreate}
          onEdit={handleEdit}
        />
      )}

      {/* 创建/编辑模式 - 直接嵌入页面 */}
      {(mode === 'create' || mode === 'edit') && (
        <Card
          bordered={false}
          style={{
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
            borderRadius: 12,
          }}
          bodyStyle={{ padding: 32 }}
        >
          <SceneEditor
            sceneId={currentSceneId}
            onSave={handleSave}
            onCancel={handleCancel}
          />
        </Card>
      )}
    </div>
  );
}
