"use client";

import React, { useState, useEffect } from 'react';
import {
  Card,
  Tabs,
  Button,
  Switch,
  Input,
  Select,
  Form,
  message,
  Spin,
  Space,
  Modal,
  Tag,
  Table,
  Popconfirm,
  Divider,
  Alert,
  Typography,
  Segmented,
  Collapse,
  InputNumber,
  Descriptions,
  Slider,
} from 'antd';
import {
  SettingOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  SafetyOutlined,
  CloudServerOutlined,
  LoginOutlined,
  EyeOutlined,
  EditOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  ApiOutlined,
  FolderOutlined,
  KeyOutlined,
  TeamOutlined,
  LockOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import CodeMirror from '@uiw/react-codemirror';
import { json } from '@codemirror/lang-json';
import {
  configService,
  toolsService,
  AppConfig,
  AgentConfig,
  ToolInfo,
  SecretConfig,
  FileServiceConfig,
} from '@/services/config';
import AgentAuthorizationConfig from '@/components/config/AgentAuthorizationConfig';
import ToolManagementPanel from '@/components/config/ToolManagementPanel';
import OAuth2ConfigSection from '@/components/config/OAuth2ConfigSection';
import type { AuthorizationConfig } from '@/types/authorization';
import type { ToolMetadata } from '@/types/tool';

const { Title, Text } = Typography;

export default function ConfigPage() {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [activeTab, setActiveTab] = useState('system');
  const [editMode, setEditMode] = useState<'visual' | 'json'>('visual');
  const [jsonValue, setJsonValue] = useState('');
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [authorizationConfig, setAuthorizationConfig] = useState<AuthorizationConfig | undefined>(undefined);
  const [toolMetadata, setToolMetadata] = useState<ToolMetadata[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);

  useEffect(() => {
    loadConfig();
    loadTools();
    loadAuthorizationConfig();
    loadToolMetadata();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await configService.getConfig();
      setConfig(data);
      setJsonValue(JSON.stringify(data, null, 2));
    } catch (error: any) {
      message.error('加载配置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const loadTools = async () => {
    try {
      const data = await toolsService.listTools();
      setTools(data);
    } catch (error) {
      console.error('加载工具列表失败', error);
    }
  };

  const loadAuthorizationConfig = async () => {
    try {
      const data = await configService.getConfig();
      if ((data as any).authorization) {
        setAuthorizationConfig((data as any).authorization);
      }
    } catch (error) {
      console.error('加载授权配置失败', error);
    }
  };

  const loadToolMetadata = async () => {
    try {
      const data = await toolsService.listTools();
      const metadata: ToolMetadata[] = data.map((tool: ToolInfo) => ({
        id: tool.name,
        name: tool.name,
        version: '1.0.0',
        description: tool.description,
        category: tool.category || 'CODE',
        authorization: {
          requires_authorization: tool.requires_permission || false,
          risk_level: tool.risk || 'LOW',
          risk_categories: [],
        },
        parameters: [],
        tags: [],
      }));
      setToolMetadata(metadata);
      setEnabledTools(data.map((t: ToolInfo) => t.name));
    } catch (error) {
      console.error('加载工具元数据失败', error);
    }
  };

  const handleAuthorizationConfigChange = async (newConfig: AuthorizationConfig) => {
    setAuthorizationConfig(newConfig);
    try {
      await configService.importConfig({ ...config, authorization: newConfig } as any);
      message.success('授权配置已保存');
    } catch (error: any) {
      message.error('保存授权配置失败: ' + error.message);
    }
  };

  const handleToolToggle = async (toolName: string, enabled: boolean) => {
    if (enabled) {
      setEnabledTools([...enabledTools, toolName]);
    } else {
      setEnabledTools(enabledTools.filter(t => t !== toolName));
    }
  };

  const handleSaveConfig = async () => {
    try {
      const newConfig = JSON.parse(jsonValue);
      await configService.importConfig(newConfig);
      message.success('配置已保存');
      loadConfig();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleValidateConfig = async () => {
    try {
      const result = await configService.validateConfig();
      if (result.valid) {
        message.success('配置验证通过');
      } else {
        Modal.warning({
          title: '配置验证警告',
          content: (
            <div>
              {result.warnings.map((w, i) => (
                <Alert key={i} type={w.level === 'error' ? 'error' : 'warning'} message={w.message} style={{ marginBottom: 8 }} />
              ))}
            </div>
          ),
        });
      }
    } catch (error: any) {
      message.error('验证失败: ' + error.message);
    }
  };

  const handleReloadConfig = async () => {
    try {
      await configService.reloadConfig();
      message.success('配置已重新加载');
      loadConfig();
    } catch (error: any) {
      message.error('重新加载失败: ' + error.message);
    }
  };

  const handleExportConfig = () => {
    const blob = new Blob([jsonValue], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'derisk-config.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportConfig = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const text = await file.text();
        setJsonValue(text);
      }
    };
    input.click();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="p-6 h-full overflow-auto">
      <Title level={3}>系统配置管理</Title>
      <Text type="secondary">管理系统配置、Agent、密钥和工具</Text>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="mt-4"
        size="large"
        items={[
          {
            key: 'system',
            label: <span><SettingOutlined /> 系统配置</span>,
            children: (
              <>
                <div className="mb-4 flex justify-between items-center">
                  <Segmented
                    value={editMode}
                    onChange={(value) => setEditMode(value as 'visual' | 'json')}
                    options={[
                      {
                        value: 'visual',
                        label: <span><EyeOutlined style={{ marginRight: 4 }} />可视化模式</span>,
                      },
                      {
                        value: 'json',
                        label: <span><EditOutlined style={{ marginRight: 4 }} />JSON模式</span>,
                      },
                    ]}
                  />
                  <Space>
                    <Button icon={<CheckCircleOutlined />} onClick={handleValidateConfig}>验证配置</Button>
                    <Button icon={<ReloadOutlined />} onClick={handleReloadConfig}>重新加载</Button>
                    <Button icon={<DownloadOutlined />} onClick={handleExportConfig}>导出配置</Button>
                    <Button icon={<UploadOutlined />} onClick={handleImportConfig}>导入配置</Button>
                  </Space>
                </div>

                {editMode === 'visual' ? (
                  <VisualConfig config={config} onConfigChange={loadConfig} />
                ) : (
                  <Card>
                    <div className="mb-2 flex justify-between">
                      <Text>直接编辑 JSON 配置文件</Text>
                      <Button type="primary" onClick={handleSaveConfig}>保存配置</Button>
                    </div>
                    <CodeMirror
                      value={jsonValue}
                      height="500px"
                      extensions={[json()]}
                      onChange={(value) => setJsonValue(value)}
                      theme="light"
                    />
                  </Card>
                )}
              </>
            ),
          },
          {
            key: 'agents',
            label: <span><TeamOutlined /> Agent配置</span>,
            children: <AgentsConfigSection config={config} onChange={loadConfig} />,
          },
          {
            key: 'secrets',
            label: <span><KeyOutlined /> 密钥管理</span>,
            children: <SecretsConfigSection onChange={loadConfig} />,
          },
          {
            key: 'authorization',
            label: <span><SafetyOutlined /> 授权配置</span>,
            children: (
              <AgentAuthorizationConfig
                value={authorizationConfig}
                onChange={handleAuthorizationConfigChange}
                availableTools={tools.map(t => t.name)}
                showAdvanced={true}
              />
            ),
          },
          {
            key: 'tools',
            label: <span><SettingOutlined /> 工具管理</span>,
            children: (
              <ToolManagementPanel
                tools={toolMetadata}
                enabledTools={enabledTools}
                onToolToggle={handleToolToggle}
                allowToggle={true}
                showDetailModal={true}
                loading={loading}
              />
            ),
          },
          {
            key: 'oauth2',
            label: <span><LoginOutlined /> OAuth2 登录</span>,
            children: <OAuth2ConfigSection onChange={loadConfig} />,
          },
          {
            key: 'llm-keys',
            label: <span><RobotOutlined /> LLM Key 配置</span>,
            children: <LLMKeyConfigSection onChange={loadConfig} />,
          },
        ]}
      />
    </div>
  );
}

function VisualConfig({
  config,
  onConfigChange,
}: {
  config: AppConfig | null;
  onConfigChange: () => void;
}) {
  if (!config) return null;

  return (
    <div className="space-y-4">
      <Collapse
        defaultActiveKey={['system', 'web', 'model', 'agents', 'file-service', 'sandbox']}
        ghost
        items={[
          {
            key: 'system',
            label: <span className="font-semibold"><GlobalOutlined /> 系统设置</span>,
            children: <SystemConfigSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'web',
            label: <span className="font-semibold"><CloudServerOutlined /> Web服务配置</span>,
            children: <WebServiceConfigSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'model',
            label: <span className="font-semibold"><ApiOutlined /> 默认模型配置</span>,
            children: <DefaultModelConfigSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'agents',
            label: <span className="font-semibold"><TeamOutlined /> Agent配置</span>,
            children: <VisualAgentsSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'file-service',
            label: <span className="font-semibold"><FolderOutlined /> 文件服务配置</span>,
            children: <FileServiceConfigSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'sandbox',
            label: <span className="font-semibold"><SafetyOutlined /> 沙箱配置</span>,
            children: <SandboxConfigSection config={config} onChange={onConfigChange} />,
          },
        ]}
      />
    </div>
  );
}

function SystemConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (config.system) {
      form.setFieldsValue(config.system);
    }
  }, [config.system]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateSystemConfig(values);
      message.success('系统配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="language" label="语言">
          <Select>
            <Select.Option value="zh">中文</Select.Option>
            <Select.Option value="en">English</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="log_level" label="日志级别">
          <Select>
            <Select.Option value="DEBUG">DEBUG</Select.Option>
            <Select.Option value="INFO">INFO</Select.Option>
            <Select.Option value="WARNING">WARNING</Select.Option>
            <Select.Option value="ERROR">ERROR</Select.Option>
          </Select>
        </Form.Item>
      </div>
      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
  );
}

function WebServiceConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (config.web) {
      form.setFieldsValue({
        host: config.web.host,
        port: config.web.port,
        model_storage: config.web.model_storage,
        web_url: config.web.web_url,
        db_type: config.web.database?.type,
        db_path: config.web.database?.path,
      });
    }
  }, [config.web]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateWebConfig({
        host: values.host,
        port: values.port,
        model_storage: values.model_storage,
        web_url: values.web_url,
      });
      message.success('Web服务配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <Divider orientation="left" plain>服务设置</Divider>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="host" label="主机地址">
          <Input placeholder="0.0.0.0" />
        </Form.Item>
        <Form.Item name="port" label="端口">
          <InputNumber style={{ width: '100%' }} min={1} max={65535} />
        </Form.Item>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="model_storage" label="模型存储">
          <Select>
            <Select.Option value="database">Database</Select.Option>
            <Select.Option value="file">File</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="web_url" label="Web URL">
          <Input placeholder="http://localhost:7777" />
        </Form.Item>
      </div>

      <Divider orientation="left" plain>数据库设置</Divider>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="db_type" label="数据库类型">
          <Select>
            <Select.Option value="sqlite">SQLite</Select.Option>
            <Select.Option value="mysql">MySQL</Select.Option>
            <Select.Option value="postgresql">PostgreSQL</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="db_path" label="数据库路径">
          <Input placeholder="pilot/meta_data/derisk.db" />
        </Form.Item>
      </div>

      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
  );
}

function DefaultModelConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (config.default_model) {
      form.setFieldsValue(config.default_model);
    }
  }, [config.default_model]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateModelConfig(values);
      message.success('默认模型配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="provider" label="Provider">
          <Select>
            <Select.Option value="openai">OpenAI</Select.Option>
            <Select.Option value="anthropic">Anthropic</Select.Option>
            <Select.Option value="alibaba">Alibaba/DashScope</Select.Option>
            <Select.Option value="custom">自定义</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="model_id" label="模型ID">
          <Input placeholder="gpt-4" />
        </Form.Item>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="base_url" label="API Base URL">
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>
        <Form.Item name="api_key" label="API Key">
          <Input.Password placeholder="sk-..." />
        </Form.Item>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="temperature" label="Temperature">
          <Slider min={0} max={2} step={0.1} />
        </Form.Item>
        <Form.Item name="max_tokens" label="Max Tokens">
          <InputNumber style={{ width: '100%' }} min={1} max={128000} />
        </Form.Item>
      </div>
      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
  );
}

function VisualAgentsSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);

  useEffect(() => {
    if (config.agents) {
      setAgents(Object.values(config.agents));
    }
  }, [config.agents]);

  const handleEditAgent = (name: string) => {
    message.info(`编辑 Agent: ${name}`);
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: AgentConfig) => (
        <Tag color={record.color}>{name}</Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '最大步数',
      dataIndex: 'max_steps',
      key: 'max_steps',
    },
    {
      title: '工具',
      dataIndex: 'tools',
      key: 'tools',
      render: (tools: string[]) => (
        <div className="flex flex-wrap gap-1">
          {tools?.slice(0, 3).map((t, i) => <Tag key={i}>{t}</Tag>)}
          {tools?.length > 3 && <Tag>+{tools.length - 3}</Tag>}
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: AgentConfig) => (
        <Button size="small" onClick={() => handleEditAgent(record.name)}>编辑</Button>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4">
        <Text type="secondary">
          系统预设的 Agent 配置。可在 "Agent配置" 标签页进行详细管理。
        </Text>
      </div>
      <Table
        dataSource={agents}
        columns={columns}
        rowKey="name"
        pagination={false}
        size="small"
      />
    </div>
  );
}

function FileServiceConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();
  const [fileService, setFileService] = useState<FileServiceConfig | null>(null);

  useEffect(() => {
    if (config.file_service) {
      setFileService(config.file_service);
      form.setFieldsValue({
        enabled: config.file_service.enabled,
        default_backend: config.file_service.default_backend,
      });
    }
  }, [config.file_service]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateFileServiceConfig({
        enabled: values.enabled,
        default_backend: values.default_backend,
      });
      message.success('文件服务配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  if (!fileService) return null;

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="enabled" label="启用文件服务" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="default_backend" label="默认后端">
          <Select>
            <Select.Option value="local">本地存储</Select.Option>
            <Select.Option value="oss">阿里云OSS</Select.Option>
            <Select.Option value="s3">AWS S3</Select.Option>
          </Select>
        </Form.Item>
      </div>

      <Divider orientation="left" plain>存储后端配置</Divider>
      {fileService.backends?.map((backend, index) => (
        <Card key={index} size="small" className="mb-2" title={`后端 #${index + 1}: ${backend.type}`}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="类型">{backend.type}</Descriptions.Item>
            <Descriptions.Item label="Bucket">{backend.bucket}</Descriptions.Item>
            {backend.type !== 'local' && (
              <>
                <Descriptions.Item label="Endpoint">{backend.endpoint}</Descriptions.Item>
                <Descriptions.Item label="Region">{backend.region}</Descriptions.Item>
              </>
            )}
            {backend.type === 'local' && (
              <Descriptions.Item label="存储路径">{backend.storage_path}</Descriptions.Item>
            )}
          </Descriptions>
        </Card>
      ))}

      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
  );
}

function SandboxConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (config.sandbox) {
      form.setFieldsValue(config.sandbox);
    }
  }, [config.sandbox]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateSandboxConfig(values);
      message.success('沙箱配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <Divider orientation="left" plain>基础设置</Divider>
      <div className="grid grid-cols-3 gap-4">
        <Form.Item name="enabled" label="启用沙箱" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="type" label="沙箱类型">
          <Select>
            <Select.Option value="local">Local</Select.Option>
            <Select.Option value="docker">Docker</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="timeout" label="超时时间(秒)">
          <InputNumber style={{ width: '100%' }} min={10} max={3600} />
        </Form.Item>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="work_dir" label="工作目录">
          <Input placeholder="/home/user/workspace" />
        </Form.Item>
        <Form.Item name="memory_limit" label="内存限制">
          <Input placeholder="512m" />
        </Form.Item>
      </div>

      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
  );
}

function AgentsConfigSection({
  config,
  onChange,
}: {
  config: AppConfig | null;
  onChange: () => void;
}) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    if (config?.agents) {
      setAgents(Object.values(config.agents));
    }
  }, [config?.agents]);

  const handleAddAgent = () => {
    setEditingAgent(null);
    form.resetFields();
    form.setFieldsValue({
      max_steps: 30,
      color: '#4A90E2',
      tools: [],
    });
    setModalVisible(true);
  };

  const handleEditAgent = (agent: AgentConfig) => {
    setEditingAgent(agent.name);
    form.setFieldsValue(agent);
    setModalVisible(true);
  };

  const handleDeleteAgent = async (name: string) => {
    try {
      await configService.deleteAgent(name);
      message.success('Agent已删除');
      onChange();
    } catch (error: any) {
      message.error('删除失败: ' + error.message);
    }
  };

  const handleSaveAgent = async (values: any) => {
    try {
      if (editingAgent) {
        await configService.updateAgent(editingAgent, values);
        message.success('Agent已更新');
      } else {
        await configService.createAgent(values);
        message.success('Agent已创建');
      }
      setModalVisible(false);
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: AgentConfig) => (
        <Tag color={record.color}>{name}</Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '最大步数',
      dataIndex: 'max_steps',
      key: 'max_steps',
    },
    {
      title: '工具',
      dataIndex: 'tools',
      key: 'tools',
      render: (tools: string[]) => (
        <div className="flex flex-wrap gap-1">
          {tools?.slice(0, 3).map((t, i) => <Tag key={i}>{t}</Tag>)}
          {tools?.length > 3 && <Tag>+{tools.length - 3}</Tag>}
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: AgentConfig) => (
        <Space>
          <Button size="small" onClick={() => handleEditAgent(record)}>编辑</Button>
          {record.name !== 'primary' && (
            <Popconfirm title="确定删除?" onConfirm={() => handleDeleteAgent(record.name)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4">
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAddAgent}>
          添加 Agent
        </Button>
      </div>
      <Table
        dataSource={agents}
        columns={columns}
        rowKey="name"
        pagination={false}
        size="small"
      />

      <Modal
        title={editingAgent ? '编辑 Agent' : '添加 Agent'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical">
          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input disabled={!!editingAgent} />
            </Form.Item>
            <Form.Item name="color" label="颜色">
              <Input type="color" />
            </Form.Item>
          </div>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="max_steps" label="最大步数">
              <InputNumber style={{ width: '100%' }} min={1} max={100} />
            </Form.Item>
            <Form.Item name="tools" label="工具列表">
              <Select mode="tags" placeholder="输入工具名称" />
            </Form.Item>
          </div>
          <Form.Item name="system_prompt" label="系统提示词">
            <Input.TextArea rows={3} placeholder="Agent的系统提示词..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function SecretsConfigSection({
  onChange,
}: {
  onChange: () => void;
}) {
  const [secrets, setSecrets] = useState<Array<{ name: string; description: string; has_value: boolean }>>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingSecret, setEditingSecret] = useState<string | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    loadSecrets();
  }, []);

  const loadSecrets = async () => {
    try {
      const data = await configService.listSecrets();
      setSecrets(data);
    } catch (error: any) {
      message.error('加载密钥列表失败: ' + error.message);
    }
  };

  const handleEditSecret = (name: string) => {
    setEditingSecret(name);
    const secret = secrets.find(s => s.name === name);
    form.setFieldsValue({
      name,
      description: secret?.description || '',
      value: '',
    });
    setModalVisible(true);
  };

  const handleSaveSecret = async (values: any) => {
    try {
      await configService.setSecret(values.name, values.value, values.description);
      message.success('密钥已保存');
      setModalVisible(false);
      loadSecrets();
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleDeleteSecret = async (name: string) => {
    try {
      await configService.deleteSecret(name);
      message.success('密钥已删除');
      loadSecrets();
    } catch (error: any) {
      message.error('删除失败: ' + error.message);
    }
  };

  const columns = [
    {
      title: '密钥名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Text code>{name}</Text>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '状态',
      dataIndex: 'has_value',
      key: 'has_value',
      render: (hasValue: boolean) => (
        <Tag color={hasValue ? 'green' : 'orange'}>
          {hasValue ? '已设置' : '未设置'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEditSecret(record.name)}>
            {record.has_value ? '更新' : '设置'}
          </Button>
          <Popconfirm title="确定删除此密钥?" onConfirm={() => handleDeleteSecret(record.name)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="密钥安全说明"
        description="密钥值在导出JSON时会被隐藏。请在可视化模式下设置敏感信息，不要在JSON模式下直接编辑密钥值。"
        className="mb-4"
      />
      <Table
        dataSource={secrets}
        columns={columns}
        rowKey="name"
        pagination={false}
        size="small"
      />

      <Modal
        title={<span><LockOutlined /> {editingSecret ? '更新密钥' : '设置密钥'}</span>}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Alert
          type="warning"
          message="安全提示"
          description="请确保在安全环境下输入密钥值。密钥将被加密存储。"
          className="mb-4"
        />
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="密钥名称">
            <Input disabled />
          </Form.Item>
          <Form.Item name="value" label="密钥值" rules={[{ required: true }]}>
            <Input.Password placeholder="输入密钥值" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="密钥用途说明" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function LLMKeyConfigSection({
  onChange,
}: {
  onChange: () => void;
}) {
  const [llmKeys, setLLMKeys] = useState<Array<{
    provider: string;
    description: string;
    is_configured: boolean;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    loadLLMKeys();
  }, []);

  const loadLLMKeys = async () => {
    setLoading(true);
    try {
      const data = await configService.listLLMKeys();
      setLLMKeys(data);
    } catch (error: any) {
      message.error('加载 LLM Key 配置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSetKey = (provider: string) => {
    setEditingProvider(provider);
    form.resetFields();
    form.setFieldsValue({
      provider,
      api_key: '',
    });
    setModalVisible(true);
  };

  const handleSaveKey = async (values: any) => {
    try {
      await configService.setLLMKey(values.provider, values.api_key);
      message.success(`${values.provider} API Key 已保存`);
      setModalVisible(false);
      loadLLMKeys();
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleDeleteKey = async (provider: string) => {
    try {
      await configService.deleteLLMKey(provider);
      message.success(`${provider} API Key 已删除`);
      loadLLMKeys();
      onChange();
    } catch (error: any) {
      message.error('删除失败: ' + error.message);
    }
  };

  const getProviderLabel = (provider: string) => {
    const labels: Record<string, string> = {
      'openai': 'OpenAI',
      'alibaba': '阿里云 DashScope',
      'anthropic': 'Anthropic',
      'dashscope': 'DashScope',
      'custom': '自定义模型',
    };
    return labels[provider] || provider;
  };

  const getProviderIcon = (provider: string) => {
    const icons: Record<string, string> = {
      'openai': '🤖',
      'alibaba': '🇨🇳',
      'anthropic': '🧠',
      'dashscope': '☁️',
      'custom': '🔧',
    };
    return icons[provider] || '🔑';
  };

  const columns = [
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string) => (
        <Space>
          <span style={{ fontSize: '1.2em' }}>{getProviderIcon(provider)}</span>
          <Text strong>{getProviderLabel(provider)}</Text>
        </Space>
      ),
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '状态',
      dataIndex: 'is_configured',
      key: 'is_configured',
      render: (isConfigured: boolean, record: any) => (
        <Tag color={isConfigured ? 'green' : 'orange'}>
          {isConfigured ? '已配置' : '未配置'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            type={record.is_configured ? 'default' : 'primary'}
            icon={<KeyOutlined />}
            onClick={() => handleSetKey(record.provider)}
          >
            {record.is_configured ? '更新' : '配置'}
          </Button>
          {record.is_configured && (
            <Popconfirm
              title="确定删除此 API Key?"
              description="删除后将使用配置文件中的 API Key"
              onConfirm={() => handleDeleteKey(record.provider)}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="LLM API Key 配置说明"
        description={
          <div>
            <p>1. 在此配置的 API Key 将被加密存储，配置后立即生效</p>
            <p>2. 优先级：系统设置 {'>'} 配置文件 {'>'} 环境变量</p>
            <p>3. 配置后无法查看已保存的 Key，只能更新或删除</p>
          </div>
        }
        className="mb-4"
      />

      <Card className="mb-4" size="small">
        <div className="flex justify-between items-center">
          <div>
            <Title level={5} style={{ margin: 0 }}>快速配置</Title>
            <Text type="secondary">选择 LLM Provider 配置 API Key</Text>
          </div>
          <Space>
            <Button
              icon={<CloudServerOutlined />}
              type="primary"
              onClick={() => handleSetKey('alibaba')}
            >
              配置阿里云 DashScope
            </Button>
            <Button
              icon={<RobotOutlined />}
              onClick={() => handleSetKey('openai')}
            >
              配置 OpenAI
            </Button>
          </Space>
        </div>
      </Card>

      <Table
        dataSource={llmKeys}
        columns={columns}
        rowKey="provider"
        loading={loading}
        pagination={false}
        size="middle"
      />

      <Modal
        title={
          <span>
            <RobotOutlined /> {editingProvider ? `配置 ${getProviderLabel(editingProvider)} API Key` : '配置 API Key'}
          </span>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={500}
      >
        <Alert
          type="warning"
          showIcon
          message="安全提示"
          description="API Key 将被加密存储。出于安全考虑，保存后无法查看，只能更新。"
          className="mb-4"
        />
        <Form form={form} layout="vertical" onFinish={handleSaveKey}>
          <Form.Item name="provider" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={[
              { required: true, message: '请输入 API Key' },
              { min: 10, message: 'API Key 长度不能少于 10 个字符' },
            ]}
          >
            <Input.Password
              placeholder="sk-..."
              size="large"
            />
          </Form.Item>
          <Form.Item>
            <Text type="secondary">
              支持的格式：sk-xxx (OpenAI)、sk-xxx (DashScope) 等
            </Text>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}