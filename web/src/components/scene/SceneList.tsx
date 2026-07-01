'use client';

import React, { useEffect, useState, useImperativeHandle, forwardRef } from 'react';
import { Table, Button, Modal, message, Tag, Space, Popconfirm, Typography } from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { sceneApi, SceneDefinition } from '@/client/api/scene';
import './scene-blueprint.css';

interface SceneListProps {
  onEdit: (sceneId: string) => void;
  onCreate: () => void;
}

export interface SceneListRef {
  refresh: () => void;
}

const PriorityBar: React.FC<{ priority: number }> = ({ priority }) => (
  <span className="bp-priority-bar">
    <span className="bp-priority-track">
      {Array.from({ length: 10 }).map((_, i) => (
        <span
          key={i}
          className={`bp-priority-cell ${i < priority ? 'is-on' : ''}`}
        />
      ))}
    </span>
    <span>{priority}/10</span>
  </span>
);

export const SceneList = forwardRef<SceneListRef, SceneListProps>(
  ({ onEdit, onCreate }, ref) => {
    const [scenes, setScenes] = useState<SceneDefinition[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
      loadScenes();
    }, []);

    const loadScenes = async () => {
      setLoading(true);
      try {
        const data = await sceneApi.list();
        setScenes(data);
      } catch {
        message.error('加载场景失败');
      } finally {
        setLoading(false);
      }
    };

    useImperativeHandle(ref, () => ({ refresh: loadScenes }));

    const handleDelete = async (sceneId: string) => {
      try {
        await sceneApi.delete(sceneId);
        message.success('已删除');
        loadScenes();
      } catch {
        message.error('删除失败');
      }
    };

    const handleView = (scene: SceneDefinition) => {
      Modal.info({
        title: scene.scene_name,
        width: 720,
        content: (
          <div style={{ marginTop: 12 }}>
            <p><strong>场景 ID:</strong> <code>{scene.scene_id}</code></p>
            <p><strong>描述:</strong> {scene.description || '暂无'}</p>
            <p>
              <strong>触发方式:</strong> {scene.trigger_type} · 优先级 {scene.trigger_priority}
            </p>
            <p>
              <strong>触发关键词:</strong>{' '}
              {scene.trigger_keywords.map((k) => <Tag key={k}>{k}</Tag>)}
            </p>
            <p>
              <strong>工具:</strong>{' '}
              {scene.scene_tools.map((t) => <Tag key={t} color="blue">{t}</Tag>)}
            </p>
            {scene.tasks?.length > 0 && (
              <p><strong>任务步骤:</strong> {scene.tasks.length} 步</p>
            )}
            {scene.deliverables?.length > 0 && (
              <p><strong>产出物:</strong> {scene.deliverables.map((d) => <Tag key={d.name}>{d.name}</Tag>)}</p>
            )}
            {scene.scene_role_prompt && (
              <div>
                <strong>角色设定:</strong>
                <pre style={{ maxHeight: 200, overflow: 'auto', background: '#f5f5f5', padding: 12, fontSize: 12 }}>
                  {scene.scene_role_prompt}
                </pre>
              </div>
            )}
          </div>
        ),
      });
    };

    const columns = [
      {
        title: 'ID',
        dataIndex: 'scene_id',
        key: 'scene_id',
        render: (text: string) => <code className="bp-id-code">{text}</code>,
      },
      {
        title: '场景',
        dataIndex: 'scene_name',
        key: 'scene_name',
        render: (text: string, record: SceneDefinition) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{text}</Typography.Text>
            {record.description && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {record.description.length > 40 ? record.description.slice(0, 40) + '…' : record.description}
              </Typography.Text>
            )}
          </Space>
        ),
      },
      {
        title: '触发',
        dataIndex: 'trigger_keywords',
        key: 'trigger_keywords',
        render: (keywords: string[], record: SceneDefinition) => (
          <Space direction="vertical" size={2}>
            <span className="bp-tag-mono">{record.trigger_type}</span>
            {keywords.length > 0 ? (
              <Space size={4} wrap>
                {keywords.slice(0, 3).map((k) => <Tag key={k}>{k}</Tag>)}
                {keywords.length > 3 && <Tag>+{keywords.length - 3}</Tag>}
              </Space>
            ) : (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>—</Typography.Text>
            )}
          </Space>
        ),
      },
      {
        title: '优先级',
        dataIndex: 'trigger_priority',
        key: 'trigger_priority',
        width: 140,
        render: (priority: number) => <PriorityBar priority={priority} />,
        sorter: (a: SceneDefinition, b: SceneDefinition) => a.trigger_priority - b.trigger_priority,
      },
      {
        title: '任务 / 产出',
        key: 'meta',
        render: (_: any, record: SceneDefinition) => (
          <Space size={12}>
            <span className="bp-tag-mono">{record.tasks?.length ?? 0} 任务</span>
            <span className="bp-tag-mono">{record.deliverables?.length ?? 0} 产出</span>
          </Space>
        ),
      },
      {
        title: '更新',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 150,
        render: (time: string) => (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(time).toLocaleDateString()}
          </Typography.Text>
        ),
      },
      {
        title: '操作',
        key: 'action',
        width: 200,
        render: (_: any, record: SceneDefinition) => (
          <Space>
            <Button icon={<EyeOutlined />} onClick={() => handleView(record)} size="small">查看</Button>
            <Button
              icon={<EditOutlined />}
              onClick={() => onEdit(record.scene_id)}
              size="small"
              type="primary"
              ghost
            >
              编辑
            </Button>
            <Popconfirm
              title="确认删除"
              description="此操作不可逆。"
              onConfirm={() => handleDelete(record.scene_id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button icon={<DeleteOutlined />} danger size="small" />
            </Popconfirm>
          </Space>
        ),
      },
    ];

    return (
      <div className="bp-list-wrap">
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={onCreate} size="large">
              新建场景
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadScenes} size="large">刷新</Button>
          </Space>
          <Typography.Text type="secondary" className="bp-tag-mono">
            共 {scenes.length} 个场景
          </Typography.Text>
        </div>
        <Table
          dataSource={scenes}
          columns={columns}
          loading={loading}
          rowKey="scene_id"
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
        />
      </div>
    );
  }
);

SceneList.displayName = 'SceneList';

export default SceneList;
