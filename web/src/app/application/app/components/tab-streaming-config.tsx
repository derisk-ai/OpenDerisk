'use client';

import { useState, useEffect, useCallback, useContext } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
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
  Empty,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  CodeOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
} from '@ant-design/icons';

import { AppContext } from '@/contexts';
import {
  getToolsByCategory,
} from '@/client/api/tools/v2';

function getParamsFromSchema(inputSchema: { properties?: Record<string, unknown> } | undefined): string[] {
  if (!inputSchema || !inputSchema.properties) {
    return [];
  }
  return Object.keys(inputSchema.properties);
}

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

function ParamConfigModal({
  visible,
  paramConfig,
  availableParams,
  onSave,
  onCancel,
}: ParamConfigModalProps) {
  const { t } = useTranslation();
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
      title={isEdit ? t('streaming_edit_param') || '编辑参数配置' : t('streaming_add_param') || '添加参数配置'}
      open={visible}
      onOk={handleOk}
      onCancel={onCancel}
      width={600}
      okText={t('save') || '保存'}
      cancelText={t('cancel') || '取消'}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="param_name"
          label={t('streaming_param_name') || '参数名称'}
          rules={[{ required: true, message: t('streaming_param_name_required') || '请选择或输入参数名称' }]}
        >
          {availableParams.length > 0 ? (
            <Select
              placeholder={t('streaming_select_param') || '选择参数'}
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
            <Input placeholder={t('streaming_input_param') || '输入参数名称'} disabled={isEdit} />
          )}
        </Form.Item>

        <Form.Item
          name="enabled"
          label={t('streaming_enabled') || '启用流式'}
          valuePropName="checked"
          tooltip={t('streaming_enabled_tip') || '关闭后该参数将不启用流式传输'}
        >
          <Switch checkedChildren={t('on') || '开'} unCheckedChildren={t('off') || '关'} />
        </Form.Item>

        <Form.Item
          name="threshold"
          label={t('streaming_threshold') || '流式阈值 (字符数)'}
          tooltip={t('streaming_threshold_tip') || '参数值超过此阈值时启用流式传输'}
        >
          <InputNumber min={0} max={100000} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="strategy"
          label={t('streaming_strategy') || '分片策略'}
          tooltip={t('streaming_strategy_tip') || '选择适合的分片策略'}
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
                label={t('streaming_chunk_size') || '分片大小 (字符)'}
              >
                <InputNumber min={50} max={4096} style={{ width: '100%' }} />
              </Form.Item>
            ) : null
          }
        </Form.Item>

        <Form.Item
          name="chunk_by_line"
          label={t('streaming_chunk_by_line') || '按行分片'}
          valuePropName="checked"
          tooltip={t('streaming_chunk_by_line_tip') || '优先在行边界处分片'}
        >
          <Switch checkedChildren={t('on') || '开'} unCheckedChildren={t('off') || '关'} />
        </Form.Item>

        <Form.Item
          name="renderer"
          label={t('streaming_renderer') || '渲染器'}
          tooltip={t('streaming_renderer_tip') || '前端渲染组件类型'}
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
          label={t('streaming_description') || '描述'}
        >
          <Input.TextArea rows={2} placeholder={t('streaming_description_placeholder') || '可选：描述此配置'} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ============================================================
// Main Component
// ============================================================

export default function TabStreamingConfig() {
  const { t } = useTranslation();
  const { appInfo } = useContext(AppContext);
  
  const [loading, setLoading] = useState(false);
  const [availableTools, setAvailableTools] = useState<AvailableTool[]>([]);
  const [configs, setConfigs] = useState<ToolConfig[]>([]);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [paramModalVisible, setParamModalVisible] = useState(false);
  const [editingParam, setEditingParam] = useState<ParamConfig | undefined>();
  const [activeTab, setActiveTab] = useState('list');

  const appCode = appInfo?.app_code;

  // 加载可用工具
  const { run: loadAvailableTools } = useRequest(
    async () => {
      try {
        const res = await getToolsByCategory({ include_empty: false });
        
        if (res.success && res.categories) {
          const tools: AvailableTool[] = [];
          res.categories.forEach(category => {
            category.tools.forEach(tool => {
              const inputSchema = tool.input_schema as { properties?: Record<string, unknown> } | undefined;
              const paramNames = getParamsFromSchema(inputSchema);
              
              const parameters = paramNames.length > 0 
                ? paramNames.map(name => ({
                    name,
                    type: (inputSchema?.properties as Record<string, { type?: string }>)?.[name]?.type || 'string',
                    description: (inputSchema?.properties as Record<string, { description?: string }>)?.[name]?.description,
                  }))
                : [];
              
              tools.push({
                tool_name: tool.name,
                tool_display_name: tool.display_name,
                description: tool.description,
                parameters,
                has_streaming_config: false,
              });
            });
          });
          
          console.log('[StreamingConfig] Loaded tools with parameters:', tools.map(t => ({ name: t.tool_name, params: t.parameters.map(p => p.name) })));
          setAvailableTools(tools);
          return;
        }
      } catch (error) {
        console.error('Failed to load tools:', error);
      }
      
      setAvailableTools([]);
    },
    {
      manual: true,
    }
  );

  // 加载配置
  const { run: loadConfigs, loading: configLoading } = useRequest(
    async () => {
      if (!appCode) return;
      setLoading(true);
      try {
        const response = await fetch(`/api/v1/streaming-config/apps/${appCode}`);
        
        if (!response.ok) {
          console.warn('[StreamingConfig] API returned', response.status);
          setConfigs([]);
          return;
        }
        
        const data: { configs?: ToolConfig[] } = await response.json();
        
        if (data.configs) {
          setConfigs(data.configs.map((cfg) => ({
            ...cfg,
            param_configs: cfg.param_configs || [],
          })));
        } else {
          setConfigs([]);
        }
      } catch (error) {
        console.error('Failed to load configs:', error);
        setConfigs([]);
      } finally {
        setLoading(false);
      }
    },
    {
      manual: true,
    }
  );

  useEffect(() => {
    if (appCode) {
      loadAvailableTools();
      loadConfigs();
    }
  }, [appCode, loadAvailableTools, loadConfigs]);

  // 保存配置
  const handleSaveConfig = useCallback(async (toolName: string, config: ToolConfig) => {
    if (!appCode) {
      message.error(t('builder_no_app_selected') || '未选择应用');
      return;
    }
    if (!toolName) {
      message.error(t('streaming_no_tool_selected') || '未选择工具');
      return;
    }
    try {
      const response = await fetch(`/api/v1/streaming-config/apps/${appCode}/tools/${toolName}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('[StreamingConfig] Save response:', data);
        setConfigs(prev => {
          const existing = prev.findIndex(c => c.tool_name === toolName);
          if (existing >= 0) {
            const next = [...prev];
            next[existing] = config;
            return next;
          }
          return [...prev, config];
        });
        message.success(t('streaming_save_success') || 'Configuration saved');
      } else {
        const errorText = await response.text();
        console.error('[StreamingConfig] Save failed:', response.status, errorText);
        message.error(t('streaming_save_failed') || 'Save failed');
      }
    } catch (error) {
      console.error('Failed to save config:', error);
      message.error(t('streaming_save_failed') || 'Save failed');
    }
  }, [appCode, t]);

  // 删除配置
  const handleDeleteConfig = useCallback(async (toolName: string) => {
    Modal.confirm({
      title: t('streaming_delete_confirm') || 'Confirm Delete',
      content: t('streaming_delete_content', { tool: toolName }) || `Are you sure you want to delete streaming config for tool "${toolName}"?`,
      okText: t('delete') || 'Delete',
      cancelText: t('cancel') || 'Cancel',
      onOk: async () => {
        try {
          const response = await fetch(`/api/v1/streaming-config/apps/${appCode}/tools/${toolName}`, {
            method: 'DELETE',
          });
          
          if (response.ok) {
            setConfigs(prev => prev.filter(c => c.tool_name !== toolName));
            message.success(t('streaming_delete_success') || 'Configuration deleted');
          } else {
            message.error(t('streaming_delete_failed') || 'Delete failed');
          }
        } catch (error) {
          message.error(t('streaming_delete_failed') || 'Delete failed');
        }
      },
    });
  }, [appCode, t]);

  // 参数配置表格列
  const paramColumns = [
    {
      title: t('streaming_param_name') || '参数名',
      dataIndex: 'param_name',
      key: 'param_name',
      width: 150,
    },
    {
      title: t('streaming_threshold') || '阈值',
      dataIndex: 'threshold',
      key: 'threshold',
      width: 80,
      render: (v: number) => `${v} ${t('chars') || '字符'}`,
    },
    {
      title: t('streaming_strategy') || '策略',
      dataIndex: 'strategy',
      key: 'strategy',
      width: 100,
      render: (v: string) => {
        const opt = STRATEGY_OPTIONS.find((o) => o.value === v);
        return opt?.label || v;
      },
    },
    {
      title: t('streaming_renderer') || '渲染器',
      dataIndex: 'renderer',
      key: 'renderer',
      width: 100,
    },
    {
      title: t('status') || '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (v: boolean) => (
        <Tag color={v ? 'green' : 'default'}>{v ? t('enabled') || '启用' : t('disabled') || '禁用'}</Tag>
      ),
    },
    {
      title: t('actions') || '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: ParamConfig) => (
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

  // 工具列表表格列
  const toolColumns = [
    {
      title: t('streaming_tool_name') || '工具名称',
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
      title: t('streaming_tool_display_name') || '显示名称',
      dataIndex: 'tool_display_name',
      key: 'tool_display_name',
    },
    {
      title: t('streaming_param_count') || '参数数量',
      key: 'param_count',
      render: (_: unknown, record: ToolConfig) => record.param_configs?.length || 0,
    },
    {
      title: t('status') || '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean) => (
        <Tag color={v ? 'green' : 'default'}>{v ? t('enabled') || '启用' : t('disabled') || '禁用'}</Tag>
      ),
    },
    {
      title: t('actions') || '操作',
      key: 'actions',
      render: (_: unknown, record: ToolConfig) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setSelectedTool(record.tool_name);
              setActiveTab('edit');
            }}
          >
            {t('config') || '配置'}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            onClick={() => handleDeleteConfig(record.tool_name)}
          >
            {t('delete') || '删除'}
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
    const params = tool?.parameters?.map((p) => p.name) || [];
    console.log('[StreamingConfig] getAvailableParams for', selectedTool, ':', params, 'tool found:', !!tool);
    return params;
  };

  if (!appCode) {
    return (
      <div className="flex items-center justify-center h-64">
        <Alert
          message={t('builder_no_app_selected') || '未选择应用'}
          description={t('builder_please_select_app') || '请先选择或创建一个应用'}
          type="info"
          showIcon
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 头部 */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <ThunderboltOutlined className="text-blue-500" />
            {t('streaming_config_title') || '流式参数配置'}
          </h3>
          <Tooltip title={t('refresh') || '刷新'}>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                loadConfigs();
                loadAvailableTools();
              }}
              loading={configLoading}
              size="small"
            />
          </Tooltip>
        </div>

        <Alert
          message={t('streaming_config_info') || '配置工具参数的流式传输行为'}
          description={
            t('streaming_config_desc') ||
            '当参数值超过阈值时，将以流式方式传输到前端，实现实时预览效果。配置后，代码/命令等大内容将实时显示。'
          }
          type="info"
          showIcon
          className="rounded-lg"
        />
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-4">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'list',
              label: t('streaming_configured_tools') || '已配置工具',
              children: (
                <Card bordered={false} className="shadow-sm">
                  <div className="mb-4">
                    <Select
                      placeholder={t('streaming_add_tool') || '添加新工具配置'}
                      style={{ width: 250 }}
                      onChange={(value) => {
                        setSelectedTool(value);
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
                    locale={{
                      emptyText: (
                        <Empty
                          description={t('streaming_no_config') || '暂无配置，请添加工具'}
                        />
                      ),
                    }}
                  />
                </Card>
              ),
            },
            {
              key: 'edit',
              label: selectedTool
                ? `${t('streaming_edit') || '编辑'}: ${selectedTool}`
                : t('streaming_edit_config') || '编辑配置',
              disabled: !selectedTool,
              children: selectedTool ? (
                <Card bordered={false} className="shadow-sm">
                  <Form
                    layout="vertical"
                    initialValues={getCurrentToolConfig()}
                    onValuesChange={(_, values) => {
                      const config = configs.find((c) => c.tool_name === selectedTool);
                      if (config) {
                        const updated = { ...config, ...values };
                        setConfigs(
                          configs.map((c) =>
                            c.tool_name === selectedTool ? updated : c
                          )
                        );
                      }
                    }}
                  >
                    <Form.Item name="enabled" label={t('streaming_enabled') || '启用流式传输'} valuePropName="checked">
                      <Switch />
                    </Form.Item>

                    <Form.Item name="global_threshold" label={t('streaming_global_threshold') || '全局阈值'}>
                      <InputNumber min={0} max={100000} addonAfter={t('chars') || '字符'} />
                    </Form.Item>

                    <Form.Item name="global_strategy" label={t('streaming_global_strategy') || '全局策略'}>
                      <Select options={STRATEGY_OPTIONS} />
                    </Form.Item>

                    <Form.Item name="global_renderer" label={t('streaming_global_renderer') || '全局渲染器'}>
                      <Select options={RENDERER_OPTIONS} />
                    </Form.Item>
                  </Form>

                  <Divider>{t('streaming_param_configs') || '参数配置'}</Divider>

                  <div className="mb-4">
                    <Button
                      type="dashed"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setEditingParam(undefined);
                        setParamModalVisible(true);
                      }}
                    >
                      {t('streaming_add_param') || '添加参数配置'}
                    </Button>
                  </div>

                  <Table
                    columns={paramColumns}
                    dataSource={getCurrentToolConfig()?.param_configs || []}
                    rowKey="param_name"
                    pagination={false}
                    size="small"
                    locale={{
                      emptyText: (
                        <Empty
                          description={t('streaming_no_params') || '暂无参数配置'}
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                        />
                      ),
                    }}
                  />

                  <div className="mt-6">
                    <Button
                      type="primary"
                      onClick={() => {
                        if (!selectedTool) {
                          message.error(t('streaming_no_tool_selected') || '未选择工具');
                          return;
                        }
                        const config = configs.find((c) => c.tool_name === selectedTool);
                        if (config) {
                          handleSaveConfig(selectedTool, config);
                        } else {
                          message.error(t('streaming_config_not_found') || '配置不存在，请重新选择工具');
                        }
                      }}
                    >
                      {t('save') || '保存配置'}
                    </Button>
                    <Button className="ml-2" onClick={() => setActiveTab('list')}>
                      {t('streaming_back_to_list') || '返回列表'}
                    </Button>
                  </div>
                </Card>
              ) : null,
            },
          ]}
        />
      </div>

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
}