'use client';

import React, { useEffect, useState, useImperativeHandle, forwardRef } from 'react';
import { Table, Button, Modal, message, Tag, Space, Popconfirm, Card, Typography } from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { sceneApi, SceneDefinition } from '@/client/api/scene';

interface SceneListProps {
  onEdit: (sceneId: string) => void;
  onCreate: () => void;
}

export interface SceneListRef {
  refresh: () => void;
}

/**
 * 场景列表组件
 */
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
      } catch (error) {
        message.error('加载场景失败');
      } finally {
        setLoading(false);
      }
    };

    // 暴露刷新方法给父组件
    useImperativeHandle(ref, () => ({
      refresh: loadScenes,
    }));

    const handleDelete = async (sceneId: string) => {
      try {
        await sceneApi.delete(sceneId);
        message.success('删除成功');
        loadScenes();
      } catch (error) {
        message.error('删除失败');
      }
    };

    const handleView = (scene: SceneDefinition) => {
      Modal.info({
        title: scene.scene_name,
        width: 800,
        content: (
          <div>
            <p>
              <strong>场景 ID:</strong> {scene.scene_id}
            </p>
            <p>
              <strong>描述:</strong> {scene.description || '暂无'}
            </p>
            <p>
              <strong>触发关键词:</strong>{' '}
              {scene.trigger_keywords.map((k) => (
                <Tag key={k}>{k}</Tag>
              ))}
            </p>
            <p>
              <strong>优先级:</strong> {scene.trigger_priority}
            </p>
            <p>
              <strong>工具:</strong>{' '}
              {scene.scene_tools.map((t) => (
                <Tag key={t} color="blue">
                  {t}
                </Tag>
              ))}
            </p>
            {scene.scene_role_prompt && (
              <div>
                <strong>角色设定:</strong>
                <pre style={{ maxHeight: 200, overflow: 'auto', background: '#f5f5f5', padding: 12 }}>
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
        title: '场景 ID',
        dataIndex: 'scene_id',
        key: 'scene_id',
        render: (text: string) => <code style={{ color: '#0069fe' }}>{text}</code>,
      },
      {
        title: '场景名称',
        dataIndex: 'scene_name',
        key: 'scene_name',
        render: (text: string, record: SceneDefinition) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{text}</Typography.Text>
            {record.description && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {record.description.length > 30
                  ? record.description.slice(0, 30) + '...'
                  : record.description}
              </Typography.Text>
            )}
          </Space>
        ),
      },
      {
        title: '触发关键词',
        dataIndex: 'trigger_keywords',
        key: 'trigger_keywords',
        render: (keywords: string[]) =>
          keywords.length > 0 ? (
            <Space size={4} wrap>
              {keywords.slice(0, 3).map((k) => (
                <Tag key={k} size="small">{k}</Tag>
              ))}
              {keywords.length > 3 && (
                <Tag size="small">+{keywords.length - 3}</Tag>
              )}
            </Space>
          ) : (
            <Typography.Text type="secondary">-</Typography.Text>
          ),
      },
      {
        title: '优先级',
        dataIndex: 'trigger_priority',
        key: 'trigger_priority',
        width: 100,
        render: (priority: number) => (
          <Tag color={priority >= 7 ? 'red' : priority >= 4 ? 'orange' : 'green'}>
            {priority}
          </Tag>
        ),
        sorter: (a: SceneDefinition, b: SceneDefinition) =>
          a.trigger_priority - b.trigger_priority,
      },
      {
        title: '工具',
        dataIndex: 'scene_tools',
        key: 'scene_tools',
        render: (tools: string[]) =>
          tools.length > 0 ? (
            <Space size={4} wrap>
              {tools.slice(0, 3).map((t) => (
                <Tag key={t} color="blue" size="small">{t}</Tag>
              ))}
              {tools.length > 3 && (
                <Tag size="small">+{tools.length - 3}</Tag>
              )}
            </Space>
          ) : (
            <Typography.Text type="secondary">-</Typography.Text>
          ),
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 180,
        render: (time: string) => (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(time).toLocaleString()}
          </Typography.Text>
        ),
      },
      {
        title: '操作',
        key: 'action',
        width: 200,
        render: (_: any, record: SceneDefinition) => (
          <Space>
            <Button
              icon={<EyeOutlined />}
              onClick={() => handleView(record)}
              size="small"
            >
              查看
            </Button>
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
              description="确定要删除这个场景吗？此操作不可逆。"
              onConfirm={() => handleDelete(record.scene_id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button icon={<DeleteOutlined />} danger size="small">
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ];

    return (
      <Card bordered={false}>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={onCreate}
              size="large"
            >
              新建场景
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadScenes} size="large">
              刷新
            </Button>
          </Space>
          <Typography.Text type="secondary">
            共 {scenes.length} 个场景
          </Typography.Text>
        </div>
        <Table
          dataSource={scenes}
          columns={columns}
          loading={loading}
          rowKey="scene_id"
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>
    );
  }
);

SceneList.displayName = 'SceneList';

export default SceneList;
