'use client';

import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Button,
  Select,
  message,
  Row,
  Col,
  Card,
  Divider,
  Space,
  Tag,
  Tooltip,
} from 'antd';
import {
  SaveOutlined,
  CloseOutlined,
  InfoCircleOutlined,
  ToolOutlined,
  TagsOutlined,
  FileTextOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { MDEditor } from './MDEditor';
import { sceneApi, SceneDefinition } from '@/client/api/scene';

interface SceneEditorProps {
  sceneId?: string;
  onSave: () => void;
  onCancel: () => void;
}

/**
 * 场景编辑器组件
 * 支持创建和编辑场景
 */
export const SceneEditor: React.FC<SceneEditorProps> = ({
  sceneId,
  onSave,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const [mdContent, setMdContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (sceneId) {
      loadScene(sceneId);
    } else {
      // 新建时重置表单
      form.resetFields();
      setMdContent('');
    }
  }, [sceneId, form]);

  const loadScene = async (id: string) => {
    setLoading(true);
    try {
      const scene = await sceneApi.get(id);
      form.setFieldsValue(scene);
      setMdContent(scene.md_content || '');
    } catch (error) {
      message.error('加载场景失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values: any) => {
    setSaving(true);
    try {
      const data = {
        ...values,
        md_content: mdContent,
      };

      if (sceneId) {
        await sceneApi.update(sceneId, data);
      } else {
        await sceneApi.create(data);
      }

      onSave();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => {
    form.submit();
  };

  const availableTools = [
    { value: 'read', label: 'read', desc: '读取文件内容' },
    { value: 'write', label: 'write', desc: '写入文件内容' },
    { value: 'edit', label: 'edit', desc: '编辑文件内容' },
    { value: 'grep', label: 'grep', desc: '文本搜索' },
    { value: 'bash', label: 'bash', desc: '执行命令' },
    { value: 'webfetch', label: 'webfetch', desc: '获取网页内容' },
  ];

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSubmit}
      initialValues={{
        trigger_priority: 5,
        trigger_keywords: [],
        scene_tools: [],
      }}
      disabled={loading}
    >
      {/* 顶部操作栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 12,
          marginBottom: 24,
          paddingBottom: 16,
          borderBottom: '1px solid #f0f0f0',
        }}
      >
        <Button size="large" icon={<CloseOutlined />} onClick={onCancel}>
          取消
        </Button>
        <Button
          type="primary"
          size="large"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
        >
          {sceneId ? '保存修改' : '创建场景'}
        </Button>
      </div>

      <Row gutter={32}>
        {/* 左侧：基础信息 */}
        <Col xs={24} lg={10}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* 场景标识 */}
            <Card
              size="small"
              title={
                <Space>
                  <FileTextOutlined />
                  <span>场景标识</span>
                </Space>
              }
              bordered={false}
              style={{ background: '#fafafa' }}
            >
              <Form.Item
                name="scene_id"
                label={
                  <Space>
                    场景 ID
                    <Tooltip title="唯一标识符，只能包含小写字母和下划线">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                }
                rules={[
                  { required: true, message: '请输入场景 ID' },
                  {
                    pattern: /^[a-z_]+$/,
                    message: '只能包含小写字母和下划线',
                  },
                ]}
              >
                <Input
                  placeholder="例如：fault_diagnosis"
                  disabled={!!sceneId}
                  size="large"
                />
              </Form.Item>

              <Form.Item
                name="scene_name"
                label="场景名称"
                rules={[{ required: true, message: '请输入场景名称' }]}
              >
                <Input placeholder="例如：故障诊断" size="large" />
              </Form.Item>

              <Form.Item name="description" label="场景描述">
                <Input.TextArea
                  rows={3}
                  placeholder="详细描述场景用途..."
                  showCount
                  maxLength={500}
                />
              </Form.Item>
            </Card>

            {/* 触发配置 */}
            <Card
              size="small"
              title={
                <Space>
                  <TagsOutlined />
                  <span>触发配置</span>
                </Space>
              }
              bordered={false}
              style={{ background: '#fafafa' }}
            >
              <Form.Item
                name="trigger_keywords"
                label={
                  <Space>
                    触发关键词
                    <Tooltip title="当用户输入包含这些关键词时，会触发此场景">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                }
              >
                <Select
                  mode="tags"
                  placeholder="输入关键词后按回车"
                  tokenSeparators={[',']}
                  style={{ width: '100%' }}
                />
              </Form.Item>

              <Form.Item
                name="trigger_priority"
                label={
                  <Space>
                    优先级
                    <Tooltip title="数值越大优先级越高，范围 1-10">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                }
              >
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </Card>

            {/* 工具配置 */}
            <Card
              size="small"
              title={
                <Space>
                  <ToolOutlined />
                  <span>工具配置</span>
                </Space>
              }
              bordered={false}
              style={{ background: '#fafafa' }}
            >
              <Form.Item
                name="scene_tools"
                label={
                  <Space>
                    场景工具
                    <Tooltip title="此场景可以使用的工具">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                }
              >
                <Select
                  mode="multiple"
                  placeholder="选择或输入工具名称"
                  tokenSeparators={[',']}
                  style={{ width: '100%' }}
                  optionLabelProp="label"
                >
                  {availableTools.map((tool) => (
                    <Select.Option
                      key={tool.value}
                      value={tool.value}
                      label={tool.label}
                    >
                      <div>
                        <Tag color="blue">{tool.label}</Tag>
                        <span style={{ color: '#666', fontSize: 12 }}>
                          {tool.desc}
                        </span>
                      </div>
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              <Form.Item
                name="scene_role_prompt"
                label={
                  <Space>
                    <UserOutlined />
                    角色设定
                    <Tooltip title="定义场景助手的角色和行为方式">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                }
              >
                <Input.TextArea
                  rows={4}
                  placeholder="例如：你是一位专业的故障诊断助手，擅长分析系统日志和定位问题根因..."
                  showCount
                  maxLength={2000}
                />
              </Form.Item>
            </Card>
          </Space>
        </Col>

        {/* 右侧：场景定义 */}
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title={
              <Space>
                <FileTextOutlined />
                <span>场景定义</span>
                <Tag color="default">Markdown</Tag>
              </Space>
            }
            bordered={false}
            style={{ background: '#fafafa', height: '100%' }}
            bodyStyle={{ height: 'calc(100% - 40px)' }}
          >
            <Form.Item style={{ marginBottom: 0, height: '100%' }}>
              <MDEditor
                value={mdContent}
                onChange={setMdContent}
                placeholder={`# 场景定义

## 概述
描述这个场景的目标和用途...

## 触发条件
- 关键词匹配
- 意图识别

## 处理流程
1. 第一步：...
2. 第二步：...

## 输出格式
定义响应格式...`}
                height={500}
              />
            </Form.Item>
          </Card>
        </Col>
      </Row>
    </Form>
  );
};

export default SceneEditor;
