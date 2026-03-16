"use client";

import React, { useState, useEffect } from 'react';
import {
  Card,
  Tabs,
  Button,
  Switch,
  Input,
  Select,
  Slider,
  Form,
  message,
  Spin,
  Space,
  Modal,
  Tooltip,
  Tag,
  Table,
  Popconfirm,
  Divider,
  Alert,
  Typography,
} from 'antd';
import {
  SettingOutlined,
  CodeOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  ToolOutlined,
  SafetyOutlined,
  CloudServerOutlined,
  LoginOutlined,
} from '@ant-design/icons';
import CodeMirror from '@uiw/react-codemirror';
import { json } from '@codemirror/lang-json';
import { configService, toolsService, AppConfig, AgentConfig, ToolInfo } from '@/services/config';
import AgentAuthorizationConfig from '@/components/config/AgentAuthorizationConfig';
import ToolManagementPanel from '@/components/config/ToolManagementPanel';
import OAuth2ConfigSection from '@/components/config/OAuth2ConfigSection';
import type { AuthorizationConfig } from '@/types/authorization';
import type { ToolMetadata } from '@/types/tool';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

export default function ConfigPage() {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [activeTab, setActiveTab] = useState('visual');
  const [jsonValue, setJsonValue] = useState('');
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<AgentConfig | null>(null);
  const [form] = Form.useForm();
  const [sandboxStatus, setSandboxStatus] = useState<{ docker_available: boolean; recommended: string } | null>(null);
  const [authorizationConfig, setAuthorizationConfig] = useState<AuthorizationConfig | undefined>(undefined);
  const [toolMetadata, setToolMetadata] = useState<ToolMetadata[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);

  useEffect(() => {
    loadConfig();
    loadTools();
    loadSandboxStatus();
    loadAuthorizationConfig();
    loadToolMetadata();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await configService.getConfig();
      setConfig(data);
      setJsonValue(JSON.stringify(data, null, 2));
      const agentsData = await configService.getAgents();
      setAgents(agentsData);
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

  const loadSandboxStatus = async () => {
    try {
      const status = await toolsService.getSandboxStatus();
      setSandboxStatus(status);
    } catch (error) {
      console.error('加载沙箱状态失败', error);
    }
  };

  const loadAuthorizationConfig = async () => {
    try {
      const data = await configService.getConfig();
      if (data.authorization) {
        setAuthorizationConfig(data.authorization);
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
      await configService.importConfig({ ...config, authorization: newConfig });
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

  // Agent 相关操作
  const handleEditAgent = (agent: AgentConfig) => {
    setCurrentAgent(agent);
    form.setFieldsValue(agent);
    setEditModalVisible(true);
  };

  const handleCreateAgent = () => {
    setCurrentAgent(null);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      description: '',
      max_steps: 20,
      color: '#4A90E2',
    });
    setEditModalVisible(true);
  };

  const handleSaveAgent = async (values: any) => {
    try {
      if (currentAgent) {
        await configService.updateAgent(currentAgent.name, values);
        message.success('Agent 已更新');
      } else {
        await configService.createAgent(values);
        message.success('Agent 已创建');
      }
      setEditModalVisible(false);
      loadConfig();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleDeleteAgent = async (name: string) => {
    try {
      await configService.deleteAgent(name);
      message.success('Agent 已删除');
      loadConfig();
    } catch (error: any) {
      message.error('删除失败: ' + error.message);
    }
  };

  // 工具表格列定义
  const toolColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      render: (cat: string) => {
        const colors: Record<string, string> = {
          code: 'green',
          file: 'cyan',
          system: 'red',
          network: 'purple',
          search: 'orange',
        };
        return <Tag color={colors[cat] || 'default'}>{cat}</Tag>;
      },
    },
    {
      title: '风险等级',
      dataIndex: 'risk',
      key: 'risk',
      render: (risk: string) => {
        const colors: Record<string, string> = {
          low: 'success',
          medium: 'warning',
          high: 'error',
        };
        return <Tag color={colors[risk] || 'default'}>{risk}</Tag>;
      },
    },
    {
      title: '需要权限',
      dataIndex: 'requires_permission',
      key: 'requires_permission',
      render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <WarningOutlined style={{ color: '#faad14' }} />,
    },
  ];

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
      <Text type="secondary">管理系统配置、Agent、权限和工具</Text>
      
      <div className="mt-4">
        <Space>
          <Button icon={<CheckCircleOutlined />} onClick={handleValidateConfig}>
            验证配置
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReloadConfig}>
            重新加载
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportConfig}>
            导出配置
          </Button>
          <Button icon={<UploadOutlined />} onClick={handleImportConfig}>
            导入配置
          </Button>
        </Space>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="mt-4"
        size="large"
      >
        <TabPane
          tab={<span><SettingOutlined /> 可视化配置</span>}
          key="visual"
        >
          <VisualConfig
            config={config}
            onConfigChange={loadConfig}
            agents={agents}
            onEditAgent={handleEditAgent}
            onCreateAgent={handleCreateAgent}
            onDeleteAgent={handleDeleteAgent}
            sandboxStatus={sandboxStatus}
          />
        </TabPane>

        <TabPane
          tab={<span><CodeOutlined /> JSON 编辑</span>}
          key="json"
        >
          <Card>
            <div className="mb-2 flex justify-between">
              <Text>直接编辑 JSON 配置文件</Text>
              <Button type="primary" onClick={handleSaveConfig}>
                保存配置
              </Button>
            </div>
            <CodeMirror
              value={jsonValue}
              height="500px"
              extensions={[json()]}
              onChange={(value) => setJsonValue(value)}
              theme="light"
            />
          </Card>
        </TabPane>

        <TabPane
          tab={<span><SafetyOutlined /> 授权配置</span>}
          key="authorization"
        >
          <AgentAuthorizationConfig
            value={authorizationConfig}
            onChange={handleAuthorizationConfigChange}
            availableTools={tools.map(t => t.name)}
            showAdvanced={true}
          />
        </TabPane>

        <TabPane
          tab={<span><ToolOutlined /> 工具管理</span>}
          key="tools"
        >
          <ToolManagementPanel
            tools={toolMetadata}
            enabledTools={enabledTools}
            onToolToggle={handleToolToggle}
            allowToggle={true}
            showDetailModal={true}
            loading={loading}
          />
        </TabPane>

        <TabPane
          tab={<span><LoginOutlined /> OAuth2 登录</span>}
          key="oauth2"
        >
          <OAuth2ConfigSection onChange={loadConfig} />
        </TabPane>
      </Tabs>

      {/* Agent 编辑模态框 */}
      <Modal
        title={currentAgent ? '编辑 Agent' : '创建 Agent'}
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSaveAgent}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input disabled={!!currentAgent} placeholder="agent-name" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="max_steps" label="最大执行步骤">
            <Slider min={1} max={50} />
          </Form.Item>
          <Form.Item name="color" label="标识颜色">
            <Input type="color" />
          </Form.Item>
          <Divider>权限配置</Divider>
          <Form.Item name={['permission', 'default_action']} label="默认行为">
            <Select>
              <Select.Option value="allow">允许</Select.Option>
              <Select.Option value="deny">拒绝</Select.Option>
              <Select.Option value="ask">询问</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// 可视化配置组件
function VisualConfig({
  config,
  onConfigChange,
  agents,
  onEditAgent,
  onCreateAgent,
  onDeleteAgent,
  sandboxStatus,
}: {
  config: AppConfig | null;
  onConfigChange: () => void;
  agents: AgentConfig[];
  onEditAgent: (agent: AgentConfig) => void;
  onCreateAgent: () => void;
  onDeleteAgent: (name: string) => void;
  sandboxStatus: { docker_available: boolean; recommended: string } | null;
}) {
  if (!config) return null;

  return (
    <div className="space-y-4">
      {/* 模型配置 */}
      <Card title={<span><CloudServerOutlined /> 模型配置</span>} size="small">
        <ModelConfigSection config={config} onChange={onConfigChange} />
      </Card>

      {/* Agent 配置 */}
      <Card
        title={<span><SafetyOutlined /> Agent 配置</span>}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreateAgent}>
            新建 Agent
          </Button>
        }
        size="small"
      >
        <AgentConfigSection
          agents={agents}
          onEdit={onEditAgent}
          onDelete={onDeleteAgent}
        />
      </Card>

      {/* 沙箱配置 */}
      <Card title={<span><SafetyOutlined /> 沙箱配置</span>} size="small">
        <SandboxConfigSection
          config={config}
          onChange={onConfigChange}
          sandboxStatus={sandboxStatus}
        />
      </Card>
    </div>
  );
}

function ModelConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldsValue(config.default_model);
  }, [config.default_model]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateModelConfig(values);
      message.success('模型配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="inline" onFinish={handleSave}>
      <Form.Item name="provider" label="提供商">
        <Select style={{ width: 120 }}>
          <Select.Option value="openai">OpenAI</Select.Option>
          <Select.Option value="anthropic">Anthropic</Select.Option>
          <Select.Option value="alibaba">Alibaba</Select.Option>
          <Select.Option value="custom">自定义</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item name="model_id" label="模型">
        <Input style={{ width: 150 }} />
      </Form.Item>
      <Form.Item name="temperature" label="温度">
        <Slider min={0} max={2} step={0.1} style={{ width: 100 }} />
      </Form.Item>
      <Form.Item name="max_tokens" label="最大Token">
        <InputNumber style={{ width: 100 }} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" htmlType="submit">
          保存
        </Button>
      </Form.Item>
    </Form>
  );
}

function AgentConfigSection({
  agents,
  onEdit,
  onDelete,
}: {
  agents: AgentConfig[];
  onEdit: (agent: AgentConfig) => void;
  onDelete: (name: string) => void;
}) {
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
    },
    {
      title: '最大步骤',
      dataIndex: 'max_steps',
      key: 'max_steps',
    },
    {
      title: '默认权限',
      dataIndex: ['permission', 'default_action'],
      key: 'default_action',
      render: (action: string) => {
        const colors: Record<string, string> = {
          allow: 'success',
          deny: 'error',
          ask: 'warning',
        };
        return <Tag color={colors[action]}>{action}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: AgentConfig) => (
        <Space>
          <Button size="small" onClick={() => onEdit(record)}>
            编辑
          </Button>
          {record.name !== 'primary' && (
            <Popconfirm title="确定删除?" onConfirm={() => onDelete(record.name)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Table
      dataSource={agents}
      columns={columns}
      rowKey="name"
      pagination={false}
      size="small"
    />
  );
}

function SandboxConfigSection({
  config,
  onChange,
  sandboxStatus,
}: {
  config: AppConfig;
  onChange: () => void;
  sandboxStatus: { docker_available: boolean; recommended: string } | null;
}) {
  const [sandboxConfig, setSandboxConfig] = useState(config.sandbox);

  const handleUpdate = async (key: string, value: any) => {
    try {
      await configService.updateSandboxConfig({ [key]: value });
      message.success('沙箱配置已更新');
      onChange();
    } catch (error: any) {
      message.error('更新失败: ' + error.message);
    }
  };

  return (
    <div>
      {sandboxStatus && (
        <Alert
          type={sandboxStatus.docker_available ? 'success' : 'warning'}
          message={sandboxStatus.docker_available ? 'Docker 可用，建议启用沙箱模式' : 'Docker 不可用，将使用本地沙箱'}
          className="mb-4"
        />
      )}
      
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Text>启用沙箱</Text>
          <Switch
            checked={sandboxConfig.enabled}
            onChange={(checked) => {
              setSandboxConfig({ ...sandboxConfig, enabled: checked });
              handleUpdate('enabled', checked);
            }}
          />
        </div>
        
        <div>
          <Text>Docker 镜像</Text>
          <Input
            value={sandboxConfig.image}
            onChange={(e) => setSandboxConfig({ ...sandboxConfig, image: e.target.value })}
            onBlur={() => handleUpdate('image', sandboxConfig.image)}
            placeholder="python:3.11-slim"
            className="mt-1"
          />
        </div>
        
        <div className="flex gap-4">
          <div className="flex-1">
            <Text>内存限制</Text>
            <Input
              value={sandboxConfig.memory_limit}
              onChange={(e) => setSandboxConfig({ ...sandboxConfig, memory_limit: e.target.value })}
              onBlur={() => handleUpdate('memory_limit', sandboxConfig.memory_limit)}
              className="mt-1"
            />
          </div>
          <div className="flex-1">
            <Text>超时时间 (秒)</Text>
            <Input
              type="number"
              value={sandboxConfig.timeout}
              onChange={(e) => setSandboxConfig({ ...sandboxConfig, timeout: parseInt(e.target.value) })}
              onBlur={() => handleUpdate('timeout', sandboxConfig.timeout)}
              className="mt-1"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

import { InputNumber } from 'antd';