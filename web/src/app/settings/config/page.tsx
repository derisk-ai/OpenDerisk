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
} from 'antd';
import {
  SettingOutlined,
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
  GlobalOutlined,
  ApiOutlined,
  FolderOutlined,
  KeyOutlined,
  LockOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import CodeMirror from '@uiw/react-codemirror';
import { json } from '@codemirror/lang-json';
import {
  configService,
  toolsService,
  AppConfig,
  ToolInfo,
  FileServiceConfig,
  FileBackendConfig,
} from '@/services/config';
import AgentAuthorizationConfig from '@/components/config/AgentAuthorizationConfig';
import ToolManagementPanel from '@/components/config/ToolManagementPanel';
import OAuth2ConfigSection from '@/components/config/OAuth2ConfigSection';
import LLMSettingsSection from '@/components/config/LLMSettingsSection';
import type { AuthorizationConfig } from '@/types/authorization';
import type { ToolMetadata } from '@/types/tool';

const { Title, Text } = Typography;

const OSS_REGION_ENDPOINT_MAP: Record<string, string> = {
  'oss-cn-hangzhou': 'https://oss-cn-hangzhou.aliyuncs.com',
  'oss-cn-shanghai': 'https://oss-cn-shanghai.aliyuncs.com',
  'oss-cn-beijing': 'https://oss-cn-beijing.aliyuncs.com',
  'oss-cn-shenzhen': 'https://oss-cn-shenzhen.aliyuncs.com',
  'oss-cn-qingdao': 'https://oss-cn-qingdao.aliyuncs.com',
  'oss-cn-hongkong': 'https://oss-cn-hongkong.aliyuncs.com',
  'oss-ap-southeast-1': 'https://oss-ap-southeast-1.aliyuncs.com',
  'oss-ap-southeast-3': 'https://oss-ap-southeast-3.aliyuncs.com',
  'oss-ap-southeast-5': 'https://oss-ap-southeast-5.aliyuncs.com',
  'oss-ap-northeast-1': 'https://oss-ap-northeast-1.aliyuncs.com',
  'oss-eu-west-1': 'https://oss-eu-west-1.aliyuncs.com',
  'oss-us-west-1': 'https://oss-us-west-1.aliyuncs.com',
  'oss-us-east-1': 'https://oss-us-east-1.aliyuncs.com',
};

const S3_REGION_ENDPOINT_MAP: Record<string, string> = {
  'us-east-1': 'https://s3.us-east-1.amazonaws.com',
  'us-east-2': 'https://s3.us-east-2.amazonaws.com',
  'us-west-1': 'https://s3.us-west-1.amazonaws.com',
  'us-west-2': 'https://s3.us-west-2.amazonaws.com',
  'eu-west-1': 'https://s3.eu-west-1.amazonaws.com',
  'eu-west-2': 'https://s3.eu-west-2.amazonaws.com',
  'eu-west-3': 'https://s3.eu-west-3.amazonaws.com',
  'eu-central-1': 'https://s3.eu-central-1.amazonaws.com',
  'ap-northeast-1': 'https://s3.ap-northeast-1.amazonaws.com',
  'ap-northeast-2': 'https://s3.ap-northeast-2.amazonaws.com',
  'ap-northeast-3': 'https://s3.ap-northeast-3.amazonaws.com',
  'ap-southeast-1': 'https://s3.ap-southeast-1.amazonaws.com',
  'ap-southeast-2': 'https://s3.ap-southeast-2.amazonaws.com',
  'ap-south-1': 'https://s3.ap-south-1.amazonaws.com',
  'sa-east-1': 'https://s3.sa-east-1.amazonaws.com',
  'ca-central-1': 'https://s3.ca-central-1.amazonaws.com',
};

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
                  <VisualConfig
                    config={config}
                    onConfigChange={loadConfig}
                  />
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
            label: <span className="font-semibold"><ApiOutlined /> LLM 配置</span>,
            children: (
              <DefaultModelConfigSection
                config={config}
                onChange={onConfigChange}
              />
            ),
          },
          
          {
            key: 'file-service',
            label: <span className="font-semibold"><FolderOutlined /> 文件服务配置</span>,
            children: <FileServiceConfigSection config={config} onChange={onConfigChange} />,
          },
          {
            key: 'datasource',
            label: <span className="font-semibold"><DatabaseOutlined /> 数据源配置</span>,
            children: <DatasourceConfigSection config={config} onChange={onConfigChange} />,
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

function DatasourceConfigSection({
  config,
  onChange,
}: {
  config: AppConfig;
  onChange: () => void;
}) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (config.datasource) {
      form.setFieldsValue(config.datasource);
    }
  }, [config.datasource]);

  const handleSave = async (values: any) => {
    try {
      await configService.updateDatasourceConfig(values);
      message.success('数据源配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item
          name="learning_worker_concurrency"
          label="Schema Learning 并发度"
          tooltip="单节点 schema learning 的并发 worker 线程数，越大学习速度越快，但占用更多数据库连接"
        >
          <InputNumber min={1} max={20} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="learning_subtask_timeout"
          label="子任务超时时间（秒）"
          tooltip="worker 领取子任务后如果超过此时间未完成，会被回收重新分配"
        >
          <InputNumber min={60} max={3600} step={60} style={{ width: '100%' }} />
        </Form.Item>
      </div>

      {/* Oracle Thick Mode Configuration */}
      <div className="mt-6 mb-2 border-b pb-2">
        <span className="font-semibold text-gray-600">Oracle Thick Mode 配置（用于 Oracle 11g）</span>
      </div>
      <div className="mb-4 text-gray-500 text-sm">
        Oracle 11g 及更早版本需要启用 thick mode。启用后需安装 Oracle Instant Client 并重启服务。
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item
          name="oracle_enable_thick_mode"
          label="启用 Oracle Thick Mode"
          tooltip="启用后所有 Oracle 连接将使用 thick mode。需要安装 Oracle Instant Client。修改后需重启服务生效。"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
        <Form.Item
          name="oracle_instant_client_path"
          label="Instant Client 路径"
          tooltip="Oracle Instant Client 安装路径。不设置则自动检测（ORACLE_INSTANT_CLIENT_HOME 环境变量或常见路径）"
        >
          <Input placeholder="/opt/oracle/instantclient_11_2" />
        </Form.Item>
      </div>

      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
        <span className="ml-4 text-gray-500 text-sm">* Oracle 配置修改后需要重启服务生效</span>
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
  return <LLMSettingsSection config={config} onChange={onChange} />;
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
  const [secrets, setSecrets] = useState<Array<{ name: string; has_value: boolean }>>([]);

  useEffect(() => {
    if (config.file_service) {
      setFileService(config.file_service);
      const defaultBackend = config.file_service.default_backend;
      const backend = config.file_service.backends?.find(b => b.type === defaultBackend);
      form.setFieldsValue({
        enabled: config.file_service.enabled,
        default_backend: defaultBackend,
        bucket: backend?.bucket,
        endpoint: backend?.endpoint,
        region: backend?.region,
        storage_path: backend?.storage_path,
        access_key_ref: backend?.access_key_ref,
        access_secret_ref: backend?.access_secret_ref,
      });
    }
  }, [config.file_service]);

  useEffect(() => {
    loadSecrets();
  }, []);

  const loadSecrets = async () => {
    try {
      const data = await configService.listSecrets();
      setSecrets(data);
    } catch (error) {
      console.error('加载密钥列表失败', error);
    }
  };

  const handleSave = async (values: any) => {
    const backendType = values.default_backend;
    const backends = [...(fileService?.backends || [])];
    
    if (backendType === 'local') {
      const existingLocalIndex = backends.findIndex(b => b.type === 'local');
      const localBackend: FileBackendConfig = {
        type: 'local',
        storage_path: values.storage_path || '',
        bucket: '',
        endpoint: '',
        region: '',
        access_key_ref: '',
        access_secret_ref: '',
      };
      if (existingLocalIndex >= 0) {
        backends[existingLocalIndex] = localBackend;
      } else {
        backends.push(localBackend);
      }
    } else if (backendType === 'oss' || backendType === 's3') {
      const existingIndex = backends.findIndex(b => b.type === backendType);
      const cloudBackend: FileBackendConfig = {
        type: backendType,
        bucket: values.bucket || '',
        endpoint: values.endpoint || '',
        region: values.region || '',
        storage_path: '',
        access_key_ref: values.access_key_ref || '',
        access_secret_ref: values.access_secret_ref || '',
      };
      if (existingIndex >= 0) {
        backends[existingIndex] = cloudBackend;
      } else {
        backends.push(cloudBackend);
      }
    }

    try {
      await configService.updateFileServiceConfig({
        enabled: values.enabled,
        default_backend: values.default_backend,
        backends,
      });
      message.success('文件服务配置已保存');
      onChange();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave}>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="enabled" label="启用文件服务" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item 
          name="default_backend" 
          label="存储类型"
          rules={[{ required: true, message: '请选择存储类型' }]}
        >
          <Select onChange={() => {
            form.setFieldsValue({
              bucket: undefined,
              endpoint: undefined,
              region: undefined,
              storage_path: undefined,
              access_key_ref: undefined,
              access_secret_ref: undefined,
            });
          }}>
            <Select.Option value="local">本地存储</Select.Option>
            <Select.Option value="oss">阿里云OSS</Select.Option>
            <Select.Option value="s3">AWS S3</Select.Option>
            <Select.Option value="custom">自定义OSS/S3服务</Select.Option>
          </Select>
        </Form.Item>
      </div>

      <Form.Item shouldUpdate={(prev, curr) => prev.default_backend !== curr.default_backend}>
        {({ getFieldValue }) => {
          const backendType = getFieldValue('default_backend');
          
          if (!backendType) return null;
          
          if (backendType === 'local') {
            return (
              <Card size="small" title="本地存储配置" className="mb-4">
                <Form.Item name="storage_path" label="存储路径" rules={[{ required: true, message: '请输入存储路径' }]}>
                  <Input placeholder="/data/files" />
                </Form.Item>
              </Card>
            );
          }
          
          const isOSS = backendType === 'oss';
          const isS3 = backendType === 's3';
          const isCustom = backendType === 'custom';
          
          const getCardTitle = () => {
            if (isCustom) return '自定义对象存储配置';
            if (isOSS) return '阿里云OSS配置';
            return 'AWS S3配置';
          };
          
          const getRegionPlaceholder = () => {
            if (isCustom) return '自定义 Region，如: cn-hangzhou';
            if (isOSS) return '选择或输入 Region';
            return '选择或输入 Region';
          };
          
          const getEndpointPlaceholder = () => {
            if (isCustom) return '自定义 Endpoint，如: https://minio.example.com';
            if (isOSS) return '选择或输入 Endpoint';
            return '选择或输入 Endpoint';
          };
          
          return (
            <Card size="small" title={getCardTitle()} className="mb-4">
              {isCustom && (
                <Alert 
                  type="info" 
                  message="自定义服务配置说明" 
                  description="适用于 MinIO、腾讯 COS、华为 OBS 等兼容 S3/OSS 协议的对象存储服务，请根据服务商文档填写 Region 和 Endpoint" 
                  className="mb-4" 
                />
              )}
              <Alert 
                type="info" 
                message="密钥配置说明" 
                description="可从下拉列表选择已有密钥，或直接输入新的密钥名称（需先在「密钥管理」标签页设置对应的密钥值）" 
                className="mb-4" 
              />
              <div className="grid grid-cols-2 gap-4">
                <Form.Item name="bucket" label="Bucket 名称" rules={[{ required: true, message: '请输入Bucket名称' }]}>
                  <Input placeholder="my-bucket" />
                </Form.Item>
                <Form.Item name="region" label="Region" rules={[{ required: true, message: '请输入或选择Region' }]}>
                  <Select 
                    placeholder={getRegionPlaceholder()} 
                    showSearch 
                    allowClear
                    mode="combobox"
                    filterOption={(input, option) => 
                      (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
                    }
                    onChange={(value) => {
                      if (value && (isOSS || isS3)) {
                        const endpointMap = isOSS ? OSS_REGION_ENDPOINT_MAP : S3_REGION_ENDPOINT_MAP;
                        const endpoint = endpointMap[value as string];
                        if (endpoint) {
                          form.setFieldsValue({ endpoint });
                        }
                      }
                    }}
                  >
                    {isOSS && (
                      <>
                        <Select.Option value="oss-cn-hangzhou">cn-hangzhou (杭州)</Select.Option>
                        <Select.Option value="oss-cn-shanghai">cn-shanghai (上海)</Select.Option>
                        <Select.Option value="oss-cn-beijing">cn-beijing (北京)</Select.Option>
                        <Select.Option value="oss-cn-shenzhen">cn-shenzhen (深圳)</Select.Option>
                        <Select.Option value="oss-cn-qingdao">cn-qingdao (青岛)</Select.Option>
                        <Select.Option value="oss-cn-hongkong">cn-hongkong (香港)</Select.Option>
                        <Select.Option value="oss-ap-southeast-1">ap-southeast-1 (新加坡)</Select.Option>
                        <Select.Option value="oss-ap-southeast-3">ap-southeast-3 (马来西亚)</Select.Option>
                        <Select.Option value="oss-ap-southeast-5">ap-southeast-5 (印尼)</Select.Option>
                        <Select.Option value="oss-ap-northeast-1">ap-northeast-1 (日本)</Select.Option>
                        <Select.Option value="oss-eu-west-1">eu-west-1 (伦敦)</Select.Option>
                        <Select.Option value="oss-us-west-1">us-west-1 (硅谷)</Select.Option>
                        <Select.Option value="oss-us-east-1">us-east-1 (弗吉尼亚)</Select.Option>
                      </>
                    )}
                    {isS3 && (
                      <>
                        <Select.Option value="us-east-1">us-east-1 (弗吉尼亚北部)</Select.Option>
                        <Select.Option value="us-east-2">us-east-2 (俄亥俄)</Select.Option>
                        <Select.Option value="us-west-1">us-west-1 (加利福尼亚北部)</Select.Option>
                        <Select.Option value="us-west-2">us-west-2 (俄勒冈)</Select.Option>
                        <Select.Option value="eu-west-1">eu-west-1 (爱尔兰)</Select.Option>
                        <Select.Option value="eu-west-2">eu-west-2 (伦敦)</Select.Option>
                        <Select.Option value="eu-west-3">eu-west-3 (巴黎)</Select.Option>
                        <Select.Option value="eu-central-1">eu-central-1 (法兰克福)</Select.Option>
                        <Select.Option value="ap-northeast-1">ap-northeast-1 (东京)</Select.Option>
                        <Select.Option value="ap-northeast-2">ap-northeast-2 (首尔)</Select.Option>
                        <Select.Option value="ap-northeast-3">ap-northeast-3 (大阪)</Select.Option>
                        <Select.Option value="ap-southeast-1">ap-southeast-1 (新加坡)</Select.Option>
                        <Select.Option value="ap-southeast-2">ap-southeast-2 (悉尼)</Select.Option>
                        <Select.Option value="ap-south-1">ap-south-1 (孟买)</Select.Option>
                        <Select.Option value="sa-east-1">sa-east-1 (圣保罗)</Select.Option>
                        <Select.Option value="ca-central-1">ca-central-1 (加拿大中部)</Select.Option>
                      </>
                    )}
                  </Select>
                </Form.Item>
              </div>
              <Form.Item name="endpoint" label="Endpoint" rules={[{ required: true, message: '请输入或选择Endpoint' }]}>
                <Select 
                  placeholder={getEndpointPlaceholder()} 
                  showSearch 
                  allowClear
                  mode="combobox"
                  filterOption={(input, option) => 
                    (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
                  }
                >
                  {isOSS && (
                    <>
                      <Select.Option value="https://oss-cn-hangzhou.aliyuncs.com">https://oss-cn-hangzhou.aliyuncs.com (杭州)</Select.Option>
                      <Select.Option value="https://oss-cn-shanghai.aliyuncs.com">https://oss-cn-shanghai.aliyuncs.com (上海)</Select.Option>
                      <Select.Option value="https://oss-cn-beijing.aliyuncs.com">https://oss-cn-beijing.aliyuncs.com (北京)</Select.Option>
                      <Select.Option value="https://oss-cn-shenzhen.aliyuncs.com">https://oss-cn-shenzhen.aliyuncs.com (深圳)</Select.Option>
                      <Select.Option value="https://oss-cn-qingdao.aliyuncs.com">https://oss-cn-qingdao.aliyuncs.com (青岛)</Select.Option>
                      <Select.Option value="https://oss-cn-hongkong.aliyuncs.com">https://oss-cn-hongkong.aliyuncs.com (香港)</Select.Option>
                      <Select.Option value="https://oss-ap-southeast-1.aliyuncs.com">https://oss-ap-southeast-1.aliyuncs.com (新加坡)</Select.Option>
                      <Select.Option value="https://oss-ap-southeast-3.aliyuncs.com">https://oss-ap-southeast-3.aliyuncs.com (马来西亚)</Select.Option>
                      <Select.Option value="https://oss-ap-southeast-5.aliyuncs.com">https://oss-ap-southeast-5.aliyuncs.com (印尼)</Select.Option>
                      <Select.Option value="https://oss-ap-northeast-1.aliyuncs.com">https://oss-ap-northeast-1.aliyuncs.com (日本)</Select.Option>
                      <Select.Option value="https://oss-eu-west-1.aliyuncs.com">https://oss-eu-west-1.aliyuncs.com (伦敦)</Select.Option>
                      <Select.Option value="https://oss-us-west-1.aliyuncs.com">https://oss-us-west-1.aliyuncs.com (硅谷)</Select.Option>
                      <Select.Option value="https://oss-us-east-1.aliyuncs.com">https://oss-us-east-1.aliyuncs.com (弗吉尼亚)</Select.Option>
                    </>
                  )}
                  {isS3 && (
                    <>
                      <Select.Option value="https://s3.us-east-1.amazonaws.com">https://s3.us-east-1.amazonaws.com (弗吉尼亚北部)</Select.Option>
                      <Select.Option value="https://s3.us-east-2.amazonaws.com">https://s3.us-east-2.amazonaws.com (俄亥俄)</Select.Option>
                      <Select.Option value="https://s3.us-west-1.amazonaws.com">https://s3.us-west-1.amazonaws.com (加利福尼亚北部)</Select.Option>
                      <Select.Option value="https://s3.us-west-2.amazonaws.com">https://s3.us-west-2.amazonaws.com (俄勒冈)</Select.Option>
                      <Select.Option value="https://s3.eu-west-1.amazonaws.com">https://s3.eu-west-1.amazonaws.com (爱尔兰)</Select.Option>
                      <Select.Option value="https://s3.eu-west-2.amazonaws.com">https://s3.eu-west-2.amazonaws.com (伦敦)</Select.Option>
                      <Select.Option value="https://s3.eu-west-3.amazonaws.com">https://s3.eu-west-3.amazonaws.com (巴黎)</Select.Option>
                      <Select.Option value="https://s3.eu-central-1.amazonaws.com">https://s3.eu-central-1.amazonaws.com (法兰克福)</Select.Option>
                      <Select.Option value="https://s3.ap-northeast-1.amazonaws.com">https://s3.ap-northeast-1.amazonaws.com (东京)</Select.Option>
                      <Select.Option value="https://s3.ap-northeast-2.amazonaws.com">https://s3.ap-northeast-2.amazonaws.com (首尔)</Select.Option>
                      <Select.Option value="https://s3.ap-northeast-3.amazonaws.com">https://s3.ap-northeast-3.amazonaws.com (大阪)</Select.Option>
                      <Select.Option value="https://s3.ap-southeast-1.amazonaws.com">https://s3.ap-southeast-1.amazonaws.com (新加坡)</Select.Option>
                      <Select.Option value="https://s3.ap-southeast-2.amazonaws.com">https://s3.ap-southeast-2.amazonaws.com (悉尼)</Select.Option>
                      <Select.Option value="https://s3.ap-south-1.amazonaws.com">https://s3.ap-south-1.amazonaws.com (孟买)</Select.Option>
                      <Select.Option value="https://s3.sa-east-1.amazonaws.com">https://s3.sa-east-1.amazonaws.com (圣保罗)</Select.Option>
                      <Select.Option value="https://s3.ca-central-1.amazonaws.com">https://s3.ca-central-1.amazonaws.com (加拿大中部)</Select.Option>
                    </>
                  )}
                </Select>
              </Form.Item>
              <div className="grid grid-cols-2 gap-4">
                <Form.Item 
                  name="access_key_ref" 
                  label="Access Key 密钥名称" 
                  rules={[{ required: true, message: '请输入或选择密钥名称' }]}
                >
                  <Select 
                    placeholder={isOSS ? 'OSS_ACCESS_KEY' : isS3 ? 'S3_ACCESS_KEY' : 'ACCESS_KEY'}
                    showSearch
                    allowClear
                    mode="combobox"
                    filterOption={(input, option) => 
                      (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
                    }
                  >
                    {secrets.map(s => (
                      <Select.Option key={s.name} value={s.name}>
                        <Space>
                          {s.name}
                          <Tag color={s.has_value ? 'green' : 'orange'} style={{ marginLeft: 4 }}>
                            {s.has_value ? '已设置' : '未设置'}
                          </Tag>
                        </Space>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item 
                  name="access_secret_ref" 
                  label="Access Secret 密钥名称" 
                  rules={[{ required: true, message: '请输入或选择密钥名称' }]}
                >
                  <Select 
                    placeholder={isOSS ? 'OSS_ACCESS_SECRET' : isS3 ? 'S3_ACCESS_SECRET' : 'ACCESS_SECRET'}
                    showSearch
                    allowClear
                    mode="combobox"
                    filterOption={(input, option) => 
                      (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
                    }
                  >
                    {secrets.map(s => (
                      <Select.Option key={s.name} value={s.name}>
                        <Space>
                          {s.name}
                          <Tag color={s.has_value ? 'green' : 'orange'} style={{ marginLeft: 4 }}>
                            {s.has_value ? '已设置' : '未设置'}
                          </Tag>
                        </Space>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
              </div>
            </Card>
          );
        }}
      </Form.Item>

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
        <Form.Item name="work_dir" label="工作目录" extra="为空时使用系统默认路径 (pilot/data/workspace)">
          <Input placeholder="pilot/data/workspace" />
        </Form.Item>
        <Form.Item name="memory_limit" label="内存限制">
          <Input placeholder="512m" />
        </Form.Item>
      </div>

      <Divider orientation="left" plain>GitHub 仓库配置</Divider>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="repo_url" label="仓库URL">
          <Input placeholder="https://github.com/user/repo.git" />
        </Form.Item>
        <Form.Item name="enable_git_sync" label="启用Git同步" valuePropName="checked">
          <Switch />
        </Form.Item>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Form.Item name="skill_dir" label="技能目录">
          <Input placeholder="pilot/data/skill" />
        </Form.Item>
      </div>

      <Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form.Item>
    </Form>
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

