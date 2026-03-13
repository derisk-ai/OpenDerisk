/**
 * Streaming Tool Config Editor
 * 
 * 流式参数配置编辑组件
 * 用于在应用编辑页面配置工具的流式参数
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Select,
  InputNumber,
  Switch,
  Button,
  Table,
  Space,
  Modal,
  Input,
  message,
  Tooltip,
  Tabs,
  Tag,
  Divider,
  Alert,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SettingOutlined,
  CodeOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';

// ============================================================
// Types
// ============================================================

interface ParamConfig {
  param_name: string;
  threshold: number;
  strategy: 'fixed_size' | 'line_based' | 'semantic' | 'adaptive';
  chunk_size: number;
  chunk_by_line: boolean;
  renderer: 'code' | 'text' | 'default';
  enabled: boolean;
  description?: string;
}

interface ToolConfig {
  tool_name: string;
  tool_display_name?: string;
  tool_description?: string;
  param_configs: ParamConfig[];
  global_threshold: number;
  global_strategy: string;
  global_renderer: string;
  enabled: boolean;
  priority: number;
}

interface AvailableTool {
  tool_name: string;
  tool_display_name?: string;
  description?: string;
  parameters: Array<{
    name: string;
    type: string;
    description?: string;
  }>;
  has_streaming_config: boolean;
}

interface StreamingConfigEditorProps {
  appCode: string;
  onConfigChange?: (config: ToolConfig) => void;
}

// ============================================================
// Strategy Options
// ============================================================

const STRATEGY_OPTIONS = [
  {
    value: 'adaptive',
    label: '自适应 (推荐)',
    description: '自动识别内容类型，选择最佳分片策略',
  },
  {
    value: 'line_based',
    label: '按行分片',
    description: '按代码行分片，适合代码内容',
  },
  {
    value: 'semantic',
    label: '语义分片',
    description: '按语义单元（函数/类）分片',
  },
  {
    value: 'fixed_size',
    label: '固定大小',
    description: '按固定字符数分片',
  },
];

const RENDERER_OPTIONS = [
  { value: 'code', label: '代码渲染器', description: '带语法高亮和行号' },
  { value: 'text', label: '文本渲染器', description: '纯文本，支持打字机效果' },
  { value: 'default', label: '默认渲染器', description: '通用渲染器' },
];

// ============================================================
// Param Config Modal
// ============================================================

interface ParamConfigModalProps {
  visible: boolean;
  paramConfig?: ParamConfig;
  availableParams: string[];
  onSave: (config: ParamConfig) => void;
  onCancel: () => void;
}

const ParamConfigModal: React.FC<ParamConfigModalProps> = ({
  visible,
  paramConfig,
  availableParams,
  onSave,
  onCancel,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!paramConfig;

  useEffect(() => {
    if (visible) {
      if (paramConfig) {
        form.setFieldsValue(paramConfig);
      } else {
        form.resetFields();
        form.setFieldsValue({
          threshold: 256,
          strategy: 'adaptive',
          chunk_size: 100,
          chunk_by_line: true,
          renderer: 'default',
          enabled: true,
        });
      }
    }
  }, [visible, paramConfig, form]);

  const handleOk = () => {
    form.validateFields().then((values) => {
      onSave(values);
    });
  };

  return (
    <Modal
      title={isEdit ? '编辑参数配置' : '添加参数配置'}
      open={visible}
      onOk={handleOk}
      onCancel={onCancel}
      width={600}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="param_name"
          label="参数名称"
          rules={[{ required: true, message: '请选择或输入参数名称' }]}
        >
          {availableParams.length > 0 ? (
            <Select
              placeholder="选择参数"
              showSearch
              allowClear
              disabled={isEdit}
            >
              {availableParams.map((p) => (
                <Select.Option key={p} value={p}>
                  {p}
                </Select.Option>
              ))}
            </Select>
          ) : (
            <Input placeholder="输入参数名称" disabled={isEdit} />
          )}
        </Form.Item>

        <Form.Item
          name="enabled"
          label="启用流式"
          valuePropName="checked"
          tooltip="关闭后该参数将不启用流式传输"
        >
          <Switch checkedChildren="开" unCheckedChildren="关" />
        </Form.Item>

        <Form.Item
          name="threshold"
          label="流式阈值 (字符数)"
          tooltip="参数值超过此阈值时启用流式传输"
        >
          <InputNumber min={0} max={100000} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="strategy"
          label="分片策略"
          tooltip="选择适合的分片策略"
        >
          <Select>
            {STRATEGY_OPTIONS.map((opt) => (
              <Select.Option key={opt.value} value={opt.value}>
                <Tooltip title={opt.description}>
                  {opt.label}
                </Tooltip>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          noStyle
          shouldUpdate={(prev, curr) => prev.strategy !== curr.strategy}
        >
          {({ getFieldValue }) =>
            getFieldValue('strategy') === 'fixed_size' ? (
              <Form.Item
                name="chunk_size"
                label="分片大小 (字符)"
              >
                <InputNumber min={50} max={4096} style={{ width: '100%' }} />
              </Form.Item>
            ) : null
          }
        </Form.Item>

        <Form.Item
          name="chunk_by_line"
          label="按行分片"
          valuePropName="checked"
          tooltip="优先在行边界处分片"
        >
          <Switch checkedChildren="开" unCheckedChildren="关" />
        </Form.Item>

        <Form.Item
          name="renderer"
          label="渲染器"
          tooltip="前端渲染组件类型"
        >
          <Select>
            {RENDERER_OPTIONS.map((opt) => (
              <Select.Option key={opt.value} value={opt.value}>
                <Tooltip title={opt.description}>
                  {opt.label}
                </Tooltip>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          name="description"
          label="描述"
        >
          <Input.TextArea rows={2} placeholder="可选：描述此配置" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

// ============================================================
// Main Component
// ============================================================

export const StreamingConfigEditor: React.FC<StreamingConfigEditorProps> = ({
  appCode,
  onConfigChange,
}) => {
  const [loading, setLoading] = useState(false);
  const [availableTools, setAvailableTools] = useState<AvailableTool[]>([]);
  const [configs, setConfigs] = useState<ToolConfig[]>([]);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [paramModalVisible, setParamModalVisible] = useState(false);
  const [editingParam, setEditingParam] = useState<ParamConfig | undefined>();
  const [activeTab, setActiveTab] = useState('list');

  // 加载可用工具
  useEffect(() => {
    loadAvailableTools();
    loadConfigs();
  }, [appCode]);

  const loadAvailableTools = async () => {
    try {
      const response = await fetch(`/api/v1/streaming-config/tools/available?app_code=${appCode}`);
      const data = await response.json();
      setAvailableTools(data.tools || []);
    } catch (error) {
      console.error('Failed to load available tools:', error);
      // 使用内置工具列表作为后备
      setAvailableTools([
        {
          tool_name: 'write',
          tool_display_name: 'Write Tool',
          description: '创建或覆写文件',
          parameters: [
            { name: 'content', type: 'string', description: '文件内容' },
            { name: 'file_path', type: 'string', description: '文件路径' },
          ],
          has_streaming_config: false,
        },
        {
          tool_name: 'edit',
          tool_display_name: 'Edit Tool',
          description: '编辑文件内容',
          parameters: [
            { name: 'newString', type: 'string', description: '新内容' },
            { name: 'oldString', type: 'string', description: '旧内容' },
          ],
          has_streaming_config: false,
        },
        {
          tool_name: 'bash',
          tool_display_name: 'Bash Tool',
          description: '执行命令',
          parameters: [
            { name: 'command', type: 'string', description: '命令内容' },
          ],
          has_streaming_config: false,
        },
      ]);
    }
  };

  const loadConfigs = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/streaming-config/apps/${appCode}`);
      const data = await response.json();
      setConfigs(data.configs || []);
    } catch (error) {
      console.error('Failed to load configs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async (toolName: string, config: ToolConfig) => {
    try {
      const response = await fetch(`/api/v1/streaming-config/apps/${appCode}/tools/${toolName}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (response.ok) {
        message.success('配置已保存');
        loadConfigs();
        onConfigChange?.(config);
      } else {
        message.error('保存失败');
      }
    } catch (error) {
      message.error('保存失败');
    }
  };

  const handleDeleteConfig = async (toolName: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除工具 "${toolName}" 的流式配置吗？`,
      onOk: async () => {
        try {
          await fetch(`/api/v1/streaming-config/apps/${appCode}/tools/${toolName}`, {
            method: 'DELETE',
          });
          message.success('配置已删除');
          loadConfigs();
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  // 参数配置表格列
  const paramColumns = [
    {
      title: '参数名',
      dataIndex: 'param_name',
      key: 'param_name',
      width: 150,
    },
    {
      title: '阈值',
      dataIndex: 'threshold',
      key: 'threshold',
      width: 80,
      render: (v: number) => `${v} 字符`,
    },
    {
      title: '策略',
      dataIndex: 'strategy',
      key: 'strategy',
      width: 100,
      render: (v: string) => {
        const opt = STRATEGY_OPTIONS.find((o) => o.value === v);
        return opt?.label || v;
      },
    },
    {
      title: '渲染器',
      dataIndex: 'renderer',
      key: 'renderer',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (v: boolean) => (
        <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: ParamConfig) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingParam(record);
              setParamModalVisible(true);
            }}
          />
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => {
              // 删除参数配置
              const toolConfig = configs.find((c) => c.tool_name === selectedTool);
              if (toolConfig) {
                const newConfigs = toolConfig.param_configs.filter(
                  (p) => p.param_name !== record.param_name
                );
                handleSaveConfig(selectedTool!, {
                  ...toolConfig,
                  param_configs: newConfigs,
                });
              }
            }}
          />
        </Space>
      ),
    },
  ];

  // 工具列表
  const toolColumns = [
    {
      title: '工具名称',
      dataIndex: 'tool_name',
      key: 'tool_name',
      render: (name: string) => (
        <Space>
          <CodeOutlined />
          {name}
        </Space>
      ),
    },
    {
      title: '显示名称',
      dataIndex: 'tool_display_name',
      key: 'tool_display_name',
    },
    {
      title: '参数数量',
      key: 'param_count',
      render: (_: any, record: ToolConfig) => record.param_configs?.length || 0,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean) => (
        <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: ToolConfig) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setSelectedTool(record.tool_name);
              setActiveTab('edit');
            }}
          >
            配置
          </Button>
          <Button
            type="link"
            size="small"
            danger
            onClick={() => handleDeleteConfig(record.tool_name)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const getCurrentToolConfig = (): ToolConfig | undefined => {
    return configs.find((c) => c.tool_name === selectedTool);
  };

  const getAvailableParams = (): string[] => {
    const tool = availableTools.find((t) => t.tool_name === selectedTool);
    return tool?.parameters?.map((p) => p.name) || [];
  };

  return (
    <div className="streaming-config-editor">
      <Alert
        message="流式参数配置"
        description="配置工具参数的流式传输行为。当参数值超过阈值时，将以流式方式传输到前端，实现实时预览效果。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'list',
            label: '已配置工具',
            children: (
              <Card>
                <div style={{ marginBottom: 16 }}>
                  <Select
                    placeholder="添加新工具配置"
                    style={{ width: 250 }}
                    onChange={(value) => {
                      setSelectedTool(value);
                      // 创建新配置
                      const tool = availableTools.find((t) => t.tool_name === value);
                      if (tool) {
                        const newConfig: ToolConfig = {
                          tool_name: value,
                          tool_display_name: tool.tool_display_name,
                          tool_description: tool.description,
                          param_configs: [],
                          global_threshold: 256,
                          global_strategy: 'adaptive',
                          global_renderer: 'default',
                          enabled: true,
                          priority: 0,
                        };
                        setConfigs([...configs, newConfig]);
                        setActiveTab('edit');
                      }
                    }}
                    value={undefined}
                  >
                    {availableTools
                      .filter((t) => !configs.some((c) => c.tool_name === t.tool_name))
                      .map((tool) => (
                        <Select.Option key={tool.tool_name} value={tool.tool_name}>
                          {tool.tool_display_name || tool.tool_name}
                        </Select.Option>
                      ))}
                  </Select>
                </div>

                <Table
                  columns={toolColumns}
                  dataSource={configs}
                  rowKey="tool_name"
                  loading={loading}
                  pagination={false}
                />
              </Card>
            ),
          },
          {
            key: 'edit',
            label: selectedTool ? `编辑: ${selectedTool}` : '编辑配置',
            disabled: !selectedTool,
            children: selectedTool ? (
              <Card>
                <Form
                  layout="vertical"
                  initialValues={getCurrentToolConfig()}
                  onValuesChange={(_, values) => {
                    const config = configs.find((c) => c.tool_name === selectedTool);
                    if (config) {
                      const updated = { ...config, ...values };
                      setConfigs(configs.map((c) => 
                        c.tool_name === selectedTool ? updated : c
                      ));
                    }
                  }}
                >
                  <Form.Item name="enabled" label="启用流式传输" valuePropName="checked">
                    <Switch />
                  </Form.Item>

                  <Form.Item name="global_threshold" label="全局阈值">
                    <InputNumber min={0} max={100000} addonAfter="字符" />
                  </Form.Item>

                  <Form.Item name="global_strategy" label="全局策略">
                    <Select options={STRATEGY_OPTIONS} />
                  </Form.Item>

                  <Form.Item name="global_renderer" label="全局渲染器">
                    <Select options={RENDERER_OPTIONS} />
                  </Form.Item>
                </Form>

                <Divider>参数配置</Divider>

                <div style={{ marginBottom: 16 }}>
                  <Button
                    type="dashed"
                    icon={<PlusOutlined />}
                    onClick={() => {
                      setEditingParam(undefined);
                      setParamModalVisible(true);
                    }}
                  >
                    添加参数配置
                  </Button>
                </div>

                <Table
                  columns={paramColumns}
                  dataSource={getCurrentToolConfig()?.param_configs || []}
                  rowKey="param_name"
                  pagination={false}
                  size="small"
                />

                <div style={{ marginTop: 24 }}>
                  <Button
                    type="primary"
                    onClick={() => {
                      const config = configs.find((c) => c.tool_name === selectedTool);
                      if (config) {
                        handleSaveConfig(selectedTool, config);
                      }
                    }}
                  >
                    保存配置
                  </Button>
                  <Button style={{ marginLeft: 8 }} onClick={() => setActiveTab('list')}>
                    返回列表
                  </Button>
                </div>
              </Card>
            ) : null,
          },
        ]}
      />

      <ParamConfigModal
        visible={paramModalVisible}
        paramConfig={editingParam}
        availableParams={getAvailableParams()}
        onSave={(paramConfig) => {
          const toolConfig = configs.find((c) => c.tool_name === selectedTool);
          if (toolConfig) {
            const existingIndex = toolConfig.param_configs.findIndex(
              (p) => p.param_name === paramConfig.param_name
            );
            const newParamConfigs = [...toolConfig.param_configs];
            if (existingIndex >= 0) {
              newParamConfigs[existingIndex] = paramConfig;
            } else {
              newParamConfigs.push(paramConfig);
            }
            setConfigs(
              configs.map((c) =>
                c.tool_name === selectedTool
                  ? { ...c, param_configs: newParamConfigs }
                  : c
              )
            );
          }
          setParamModalVisible(false);
          setEditingParam(undefined);
        }}
        onCancel={() => {
          setParamModalVisible(false);
          setEditingParam(undefined);
        }}
      />
    </div>
  );
};

export default StreamingConfigEditor;