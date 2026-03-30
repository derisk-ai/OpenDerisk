"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  KeyOutlined,
  LinkOutlined,
  PlusOutlined,
  RobotOutlined,
  StarOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";

import { apiInterceptors, getSupportModels } from "@/client/api";
import { AppConfig, configService } from "@/services/config";
import type { SupportModel } from "@/types/model";

const { Text, Title } = Typography;

type LLMKeyItem = {
  provider: string;
  description: string;
  is_configured: boolean;
  builtin?: boolean;
  secret_name?: string;
};

type Props = {
  config: AppConfig;
  onChange: () => void;
};

const BUILTIN_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "alibaba", label: "Alibaba / DashScope" },
  { value: "anthropic", label: "Anthropic / Claude" },
];

const PROVIDER_ALIASES: Record<string, string> = {
  dashscope: "alibaba",
  claude: "anthropic",
};

function normalizeProviderName(value?: string) {
  const normalized = (value || "").trim().toLowerCase();
  return PROVIDER_ALIASES[normalized] || normalized;
}

function buildSecretReference(secretName?: string) {
  return secretName ? `\${secrets.${secretName}}` : "";
}

function buildDefaultSecretName(provider: string) {
  const normalized = (provider || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return `llm_provider_${normalized}_api_key`;
}

export default function LLMSettingsSection({ config, onChange }: Props) {
  const [form] = Form.useForm();
  const [llmKeys, setLLMKeys] = useState<LLMKeyItem[]>([]);
  const [supportedModels, setSupportedModels] = useState<SupportModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [keyModalVisible, setKeyModalVisible] = useState(false);
  const [keyForm] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const configuredProviders =
    Form.useWatch(["agent_llm", "providers"], form) || [];

  useEffect(() => {
    if (!config) return;
    
    form.setFieldsValue({
      agent_llm: {
        temperature: config.agent_llm?.temperature ?? 0.7,
        providers:
          config.agent_llm?.providers?.map((provider) => ({
            provider: normalizeProviderName(provider.provider),
            api_base: provider.api_base,
            api_key_ref: provider.api_key_ref,
            models:
              provider.models?.map((model) => ({
                name: model.name || "",
                temperature: model.temperature ?? 0.7,
                max_new_tokens: model.max_new_tokens ?? 4096,
                is_multimodal: model.is_multimodal ?? false,
                is_default: model.is_default ?? false,
              })) || [],
          })) || [],
      },
    });
  }, [config, form]);

  useEffect(() => {
    loadLLMKeys();
    loadSupportedModels();
  }, []);

  const llmKeyMap = useMemo(() => {
    return llmKeys.reduce<Record<string, LLMKeyItem>>((acc, item) => {
      acc[normalizeProviderName(item.provider)] = item;
      return acc;
    }, {});
  }, [llmKeys]);

  const modelSuggestionsByProvider = useMemo(() => {
    return supportedModels.reduce<Record<string, string[]>>((acc, item) => {
      const provider = normalizeProviderName(item.provider);
      if (!provider) {
        return acc;
      }
      if (!acc[provider]) {
        acc[provider] = [];
      }
      if (!acc[provider].includes(item.model)) {
        acc[provider].push(item.model);
      }
      acc[provider].sort();
      return acc;
    }, {});
  }, [supportedModels]);

  const providerOptions = useMemo(() => {
    const values = new Set<string>();
    BUILTIN_PROVIDER_OPTIONS.forEach((item) => values.add(item.value));
    configuredProviders.forEach((item: any) => {
      if (item?.provider) {
        const normalized = normalizeProviderName(item.provider);
        if (!["openai", "alibaba", "anthropic"].includes(normalized)) {
          values.add(normalized);
        }
      }
    });
    return Array.from(values)
      .filter(Boolean)
      .sort()
      .map((value) => ({
        value,
        label:
          BUILTIN_PROVIDER_OPTIONS.find((item) => item.value === value)?.label ||
          value,
      }));
  }, [configuredProviders]);

  async function loadSupportedModels() {
    setLoadingModels(true);
    try {
      const [, data] = await apiInterceptors(getSupportModels());
      setSupportedModels(data || []);
    } catch (error: any) {
      message.warning("加载 provider 模型列表失败，将允许手动输入模型名");
    } finally {
      setLoadingModels(false);
    }
  }

  async function loadLLMKeys() {
    setLoadingKeys(true);
    try {
      const data = await configService.listLLMKeys();
      setLLMKeys(data);
    } catch (error: any) {
      message.error("加载 LLM Key 状态失败: " + error.message);
    } finally {
      setLoadingKeys(false);
    }
  }

  function getProviderModels(
    providerName?: string,
    inlineModels?: Array<{ name?: string }>
  ) {
    const normalized = normalizeProviderName(providerName);
    const models = new Set<string>(modelSuggestionsByProvider[normalized] || []);
    (inlineModels || []).forEach((item) => {
      if (item?.name) {
        models.add(item.name);
      }
    });
    return Array.from(models).sort();
  }

  async function handleKeySubmit(values: any) {
    const provider = normalizeProviderName(values.provider);
    const apiKey = values.api_key;
    if (!provider || !apiKey) {
      message.error("请填写 Provider 和 API Key");
      return;
    }

    try {
      await configService.setLLMKey(provider, apiKey);
      message.success("API Key 已保存");
      setKeyModalVisible(false);
      loadLLMKeys();
    } catch (error: any) {
      message.error("保存 API Key 失败: " + error.message);
    }
  }

  async function handleDeleteKey(provider: string) {
    try {
      await configService.deleteLLMKey(provider);
      message.success("API Key 已删除");
      loadLLMKeys();
    } catch (error: any) {
      message.error("删除 API Key 失败: " + error.message);
    }
  }

  async function handleSave(values: any) {
    setSaving(true);
    try {
      const providers = (values.agent_llm?.providers || [])
        .map((item: any) => {
          const provider = normalizeProviderName(item?.provider);
          if (!provider) {
            return null;
          }
          const keyInfo = llmKeyMap[provider];
          
          // Ensure only one model is_default per provider
          const models = (item.models || [])
            .filter((model: any) => model?.name)
            .map((model: any, idx: number, arr: any[]) => ({
              name: model.name,
              temperature: model.temperature ?? 0.7,
              max_new_tokens: model.max_new_tokens ?? 4096,
              is_multimodal: model.is_multimodal ?? false,
              is_default: arr.length === 1 ? true : (model.is_default ?? false),
            }));
          
          // If multiple models have is_default=true, only keep the first one
          const defaultCount = models.filter(m => m.is_default).length;
          if (defaultCount > 1) {
            models.forEach((m, idx) => {
              m.is_default = idx === 0;
            });
          }
          
          // If no model is_default, set the first one as default
          if (models.length > 0 && !models.some(m => m.is_default)) {
            models[0].is_default = true;
          }
          
          return {
            provider,
            api_base: item.api_base || "",
            api_key_ref: (() => {
              // 优先使用用户手动输入的值
              if (item.api_key_ref?.trim()) {
                return item.api_key_ref.trim();
              }
              // 如果已配置密钥，使用密钥引用
              if (keyInfo?.secret_name) {
                return buildSecretReference(keyInfo.secret_name);
              }
              // 否则生成默认引用格式（用户需要先配置密钥）
              return buildSecretReference(buildDefaultSecretName(provider));
            })(),
            models,
          };
        })
        .filter(Boolean);

      const nextConfig: AppConfig = {
        ...config,
        agent_llm: {
          ...config.agent_llm,
          temperature:
            values.agent_llm?.temperature ?? config.agent_llm?.temperature ?? 0.5,
          providers,
        },
      };

      await configService.importConfig(nextConfig);
      try {
        await configService.refreshModelCache();
        // 刷新后重新加载模型列表
        await loadSupportedModels();
        message.success("LLM 配置已保存并生效，模型缓存已刷新");
      } catch {
        message.success("LLM 配置已保存并生效");
      }
      
      onChange();
    } catch (error: any) {
      message.error("保存失败: " + error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <RobotOutlined className="text-xl text-blue-500" />
          <Title level={4} className="!mb-0">
            模型提供商配置
          </Title>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setKeyModalVisible(true)}
          >
            管理 API Keys
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        message="新设计：默认模型设置已简化"
        description="在每个 Provider 的模型列表中，直接勾选'设为默认'即可。每个 Provider 只能有一个默认模型。"
        className="mb-4"
      />

      <Form form={form} layout="vertical" onFinish={handleSave}>
        <Form.Item
          name={["agent_llm", "temperature"]}
          label="Agent LLM 全局默认 Temperature"
        >
          <InputNumber style={{ width: "100%" }} min={0} max={2} step={0.1} />
        </Form.Item>

        <Form.List name={["agent_llm", "providers"]}>
          {(fields, { add, remove }) => (
            <div className="space-y-4">
              {fields.length === 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message="当前还没有配置任何 Provider"
                  description="至少添加一个 Provider，才能在系统配置中统一维护模型与密钥。"
                />
              )}

              {fields.map((field) => {
                const providerName = normalizeProviderName(
                  form.getFieldValue([
                    "agent_llm",
                    "providers",
                    field.name,
                    "provider",
                  ])
                );
                const inlineModels =
                  form.getFieldValue([
                    "agent_llm",
                    "providers",
                    field.name,
                    "models",
                  ]) || [];
                const providerKey = llmKeyMap[providerName];
                const modelOptions = getProviderModels(providerName, inlineModels);

                return (
                  <Card
                    key={field.key}
                    className="border border-gray-200"
                    extra={
                      <Popconfirm
                        title="确定删除该 Provider？"
                        onConfirm={() => remove(field.name)}
                      >
                        <Button danger size="small" icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    }
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <Form.Item
                        name={[field.name, "provider"]}
                        label="Provider 名称"
                        rules={[{ required: true, message: "请输入 Provider 名称" }]}
                      >
                        <AutoComplete
                          options={providerOptions}
                          placeholder="如 openai / deepseek / openrouter"
                        />
                      </Form.Item>
                      <Form.Item
                        name={[field.name, "api_base"]}
                        label="API Base URL"
                        rules={[{ required: true, message: "请输入 API Base URL" }]}
                      >
                        <Input placeholder="https://api.openai.com/v1" />
                      </Form.Item>
                    </div>

                    <Form.Item
                      name={[field.name, "api_key_ref"]}
                      label="API Key 引用"
                      tooltip="可以手动输入引用格式如 ${secrets.llm_provider_xxx_api_key}，或保存时自动生成"
                    >
                      <Input placeholder="${secrets.llm_provider_deepseek_api_key}" />
                    </Form.Item>

                    {providerKey && providerKey.is_configured && (
                      <div className="mb-4 flex items-center gap-2">
                        <CheckCircleOutlined className="text-green-500" />
                        <Text type="success">
                          已配置加密 API Key（{providerKey.description || providerKey.secret_name}）
                        </Text>
                        <Text type="secondary" className="text-xs">
                          保存时将自动使用此密钥引用
                        </Text>
                      </div>
                    )}

                    <Form.List name={[field.name, "models"]}>
                      {(modelFields, { add: addModel, remove: removeModel }) => (
                        <div className="space-y-3">
                          <div className="flex items-center justify-between mb-2">
                            <Text strong>模型列表</Text>
                            <Button
                              type="link"
                              size="small"
                              icon={<PlusOutlined />}
                              onClick={() => addModel()}
                            >
                              添加模型
                            </Button>
                          </div>

                          {modelFields.map((modelField) => {
                            const modelName = form.getFieldValue([
                              "agent_llm",
                              "providers",
                              field.name,
                              "models",
                              modelField.name,
                              "name",
                            ]);
                            const isDefault = form.getFieldValue([
                              "agent_llm",
                              "providers",
                              field.name,
                              "models",
                              modelField.name,
                              "is_default",
                            ]);

                            return (
                              <Card
                                key={modelField.key}
                                size="small"
                                className={isDefault ? "border-blue-300 bg-blue-50" : ""}
                                extra={
                                  <Popconfirm
                                    title="确定删除该模型？"
                                    onConfirm={() => removeModel(modelField.name)}
                                  >
                                    <Button
                                      danger
                                      size="small"
                                      icon={<DeleteOutlined />}
                                    />
                                  </Popconfirm>
                                }
                              >
                                <div className="grid grid-cols-3 gap-3">
                                  <Form.Item
                                    name={[modelField.name, "name"]}
                                    label="模型名称"
                                    rules={[{ required: true, message: "请输入模型名称" }]}
                                  >
                                    <AutoComplete
                                      options={modelOptions.map((item) => ({
                                        value: item,
                                      }))}
                                      placeholder={
                                        loadingModels
                                          ? "加载中..."
                                          : "选择或输入模型名"
                                      }
                                    />
                                  </Form.Item>
                                  <Form.Item
                                    name={[modelField.name, "temperature"]}
                                    label="Temperature"
                                  >
                                    <InputNumber
                                      style={{ width: "100%" }}
                                      min={0}
                                      max={2}
                                      step={0.1}
                                    />
                                  </Form.Item>
                                  <Form.Item
                                    name={[modelField.name, "max_new_tokens"]}
                                    label="Max Tokens"
                                    tooltip="请根据模型实际支持的最大token数设置"
                                  >
                                    <InputNumber
                                      style={{ width: "100%" }}
                                      min={1}
                                      placeholder="4096"
                                    />
                                  </Form.Item>
                                </div>
                                <div className="flex items-center gap-4">
                                  <Form.Item
                                    name={[modelField.name, "is_multimodal"]}
                                    valuePropName="checked"
                                    className="!mb-0"
                                  >
                                    <Switch checkedChildren="多模态" unCheckedChildren="文本" />
                                  </Form.Item>
                                  <Form.Item
                                    name={[modelField.name, "is_default"]}
                                    className="!mb-0"
                                  >
                                    <Radio.Group
                                      onChange={(e) => {
                                        // 当设置为默认时，清除其他模型的 is_default
                                        if (e.target.value) {
                                          const currentModels = form.getFieldValue([
                                            "agent_llm",
                                            "providers",
                                            field.name,
                                            "models",
                                          ]);
                                          currentModels.forEach((m: any, idx: number) => {
                                            if (idx !== modelField.name) {
                                              form.setFieldValue([
                                                "agent_llm",
                                                "providers",
                                                field.name,
                                                "models",
                                                idx,
                                                "is_default",
                                              ], false);
                                            }
                                          });
                                        }
                                      }}
                                    >
                                      <Radio value={true}>
                                        <StarOutlined className="text-yellow-500" /> 设为默认
                                      </Radio>
                                      <Radio value={false}>普通模型</Radio>
                                    </Radio.Group>
                                  </Form.Item>
                                </div>
                              </Card>
                            );
                          })}
                        </div>
                      )}
                    </Form.List>
                  </Card>
                );
              })}

              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() =>
                  add({
                    provider: "",
                    api_base: "",
                    api_key_ref: "",
                    models: [{ name: "", temperature: 0.7, max_new_tokens: 4096, is_multimodal: false, is_default: true }],
                  })
                }
                block
              >
                添加新 Provider
              </Button>
            </div>
          )}
        </Form.List>

        <div className="mt-4">
          <Button type="primary" htmlType="submit" loading={saving} size="large">
            保存 LLM 配置
          </Button>
        </div>
      </Form>

      <Modal
        title="管理 API Keys"
        open={keyModalVisible}
        onCancel={() => setKeyModalVisible(false)}
        footer={null}
        width={600}
      >
        <div className="space-y-4">
          <Alert
            type="info"
            showIcon
            message="API Keys 以加密方式存储在 Secrets 中"
          />

          <div className="space-y-2">
            <Text strong>已配置的 Keys：</Text>
            {llmKeys.length === 0 ? (
              <Text type="secondary">暂无配置的 API Key</Text>
            ) : (
              llmKeys.map((item) => (
                <div
                  key={item.provider}
                  className="flex items-center justify-between p-3 border rounded"
                >
                  <div>
                    <Tag color={item.is_configured ? "green" : "orange"}>
                      {item.provider}
                    </Tag>
                    <Text>
                      {item.is_configured
                        ? `已配置（${item.description || item.secret_name}）`
                        : "未配置"}
                    </Text>
                  </div>
                  <Space>
                    {item.is_configured && (
                      <Popconfirm
                        title="确定删除该 Key？"
                        onConfirm={() => handleDeleteKey(item.provider)}
                      >
                        <Button danger size="small" icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                </div>
              ))
            )}
          </div>

          <Form form={keyForm} layout="vertical" onFinish={handleKeySubmit}>
            <Form.Item
              name="provider"
              label="Provider"
              rules={[{ required: true, message: "请选择 Provider" }]}
            >
              <AutoComplete
                options={providerOptions}
                placeholder="选择或输入 provider 名称"
              />
            </Form.Item>
            <Form.Item
              name="api_key"
              label="API Key"
              rules={[{ required: true, message: "请输入 API Key" }]}
            >
              <Input.Password placeholder="输入完整的 API Key" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block>
              保存 Key
            </Button>
          </Form>
        </div>
      </Modal>
    </div>
  );
}