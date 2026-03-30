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
  Select,
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
} from "@ant-design/icons";

import { apiInterceptors, getSupportModels } from "@/client/api";
import {
  AppConfig,
  configService,
  LLMProviderConfig,
} from "@/services/config";
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

const BUILTIN_DEFAULT_MODEL_PROVIDERS = new Set([
  "openai",
  "alibaba",
  "anthropic",
]);

function normalizeProviderName(value?: string) {
  const normalized = (value || "").trim().toLowerCase();
  return PROVIDER_ALIASES[normalized] || normalized;
}

function buildSecretReference(secretName?: string) {
  return secretName ? `\${secrets.${secretName}}` : "";
}

function deriveDefaultProviderName(config: AppConfig) {
  const providers = config.agent_llm?.providers || [];
  const defaultBaseUrl = config.default_model?.base_url || "";
  const defaultProvider = normalizeProviderName(
    String(config.default_model?.provider || "")
  );

  const matchedByBaseUrl = providers.find(
    (item) =>
      normalizeProviderName(item.api_base || "") ===
      normalizeProviderName(defaultBaseUrl)
  );
  if (matchedByBaseUrl) {
    return normalizeProviderName(matchedByBaseUrl.provider);
  }

  const matchedByProvider = providers.find(
    (item) => normalizeProviderName(item.provider) === defaultProvider
  );
  if (matchedByProvider) {
    return normalizeProviderName(matchedByProvider.provider);
  }

  return defaultProvider || normalizeProviderName(providers[0]?.provider) || "openai";
}

function buildInitialFormValues(config: AppConfig) {
  const defaultModelId = config.default_model?.model_id || "";
  return {
    default_provider_name: deriveDefaultProviderName(config),
    default_model: {
      model_id: defaultModelId,
    },
    agent_llm: {
      temperature: config.agent_llm?.temperature ?? 0.5,
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
            })) || [],
        })) || [],
    },
  };
}

export default function LLMSettingsSection({ config, onChange }: Props) {
  const [form] = Form.useForm();
  const [llmKeys, setLLMKeys] = useState<LLMKeyItem[]>([]);
  const [supportedModels, setSupportedModels] = useState<SupportModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [keyModalVisible, setKeyModalVisible] = useState(false);
  const [providerEditable, setProviderEditable] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [keyForm] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState<{
    type: "success" | "info" | "warning" | "error";
    text: string;
  } | null>(null);

  const configuredProviders =
    Form.useWatch(["agent_llm", "providers"], form) || [];
  const selectedDefaultProvider = Form.useWatch("default_provider_name", form);
  const selectedDefaultModelId = Form.useWatch(["default_model", "model_id"], form);

  // 只在 config 变化时初始化表单
  useEffect(() => {
    if (!config) return;
    
    const newValues = buildInitialFormValues(config);
    form.setFieldsValue(newValues);
    setInitialized(true);
    
    // 调试日志
    console.log('[LLMSettingsSection] Initialized form with:', {
      default_provider_name: newValues.default_provider_name,
      default_model: newValues.default_model,
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
    llmKeys.forEach((item) => values.add(normalizeProviderName(item.provider)));
    Object.keys(modelSuggestionsByProvider).forEach((item) => values.add(item));
    configuredProviders.forEach((item: LLMProviderConfig) => {
      if (item?.provider) {
        values.add(normalizeProviderName(item.provider));
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
  }, [configuredProviders, llmKeys, modelSuggestionsByProvider]);

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

  function syncDefaultModelFromProvider(providerName?: string) {
    const normalized = normalizeProviderName(providerName);
    const providers = form.getFieldValue(["agent_llm", "providers"]) || [];
    const matchedProvider = providers.find(
      (item: LLMProviderConfig) =>
        normalizeProviderName(item?.provider) === normalized
    );

    const candidateModels = getProviderModels(
      normalized,
      matchedProvider?.models || []
    );
    const currentModel = form.getFieldValue(["default_model", "model_id"]);
    if ((!currentModel || !candidateModels.includes(currentModel)) && candidateModels[0]) {
      form.setFieldValue(["default_model", "model_id"], candidateModels[0]);
    }
    if (currentModel && candidateModels.length === 0) {
      form.setFieldValue(["default_model", "model_id"], undefined);
    }
  }

  function openKeyModal(provider?: string, editable = false) {
    const normalized = normalizeProviderName(provider);
    setEditingProvider(normalized || null);
    setProviderEditable(editable);
    keyForm.resetFields();
    keyForm.setFieldsValue({
      provider: normalized || "",
      api_key: "",
    });
    setKeyModalVisible(true);
  }

  async function handleSaveKey(values: { provider: string; api_key: string }) {
    try {
      await configService.setLLMKey(values.provider, values.api_key);
      message.success(`${values.provider} API Key 已保存`);
      setKeyModalVisible(false);
      await loadLLMKeys();
    } catch (error: any) {
      message.error("保存 API Key 失败: " + error.message);
    }
  }

  async function handleDeleteKey(provider: string) {
    try {
      await configService.deleteLLMKey(provider);
      message.success(`${provider} API Key 已删除`);
      await loadLLMKeys();
    } catch (error: any) {
      message.error("删除 API Key 失败: " + error.message);
    }
  }

  async function handleSave(values: any) {
    console.log('[LLMSettingsSection] handleSave called with values:', {
      default_provider_name: values.default_provider_name,
      default_model: values.default_model,
    });
    
    const providers = (values.agent_llm?.providers || [])
      .map((item: any) => {
        const provider = normalizeProviderName(item?.provider);
        if (!provider) {
          return null;
        }
        const keyInfo = llmKeyMap[provider];
        return {
          provider,
          api_base: item.api_base || "",
          api_key_ref:
            item.api_key_ref || buildSecretReference(keyInfo?.secret_name),
          models: (item.models || [])
            .filter((model: any) => model?.name)
            .map((model: any) => ({
              name: model.name,
              temperature: model.temperature ?? 0.7,
              max_new_tokens: model.max_new_tokens ?? 4096,
              is_multimodal: model.is_multimodal ?? false,
            })),
        };
      })
      .filter(Boolean);

    const selectedProviderName =
      normalizeProviderName(values.default_provider_name) ||
      normalizeProviderName(providers[0]?.provider);
    const selectedProvider = providers.find(
      (item: any) => normalizeProviderName(item.provider) === selectedProviderName
    );
    const selectedKeyInfo = llmKeyMap[selectedProviderName];
    const selectedModelConfig = selectedProvider?.models?.find(
      (item: any) => item.name === values.default_model?.model_id
    );

    if (!selectedProviderName || !selectedProvider) {
      throw new Error("请先选择一个默认 Provider");
    }

    const resolvedModelId =
      selectedModelConfig?.name ||
      values.default_model?.model_id ||
      config.default_model?.model_id ||
      "";
    const resolvedTemperature =
      selectedModelConfig?.temperature ?? config.default_model?.temperature;
    const resolvedMaxTokens =
      selectedModelConfig?.max_new_tokens ?? config.default_model?.max_tokens;

    const nextConfig: AppConfig = {
      ...config,
      default_model: {
        ...config.default_model,
        provider: (
          BUILTIN_DEFAULT_MODEL_PROVIDERS.has(selectedProviderName)
            ? selectedProviderName
            : "custom"
        ) as AppConfig["default_model"]["provider"],
        model_id: resolvedModelId,
        base_url: selectedProvider.api_base || config.default_model?.base_url,
        temperature: resolvedTemperature,
        max_tokens: resolvedMaxTokens,
        api_key:
          buildSecretReference(selectedKeyInfo?.secret_name) ||
          config.default_model?.api_key,
      },
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
      setSaveFeedback({ type: "success", text: "LLM 配置已保存并生效，模型缓存已刷新" });
    } catch {
      setSaveFeedback({ type: "success", text: "LLM 配置已保存并生效" });
    }
    message.success("LLM 配置已保存");
    
    // 重置初始化状态，让下一次 config 加载时重新初始化表单
    setInitialized(false);
    
    onChange();
  }

  async function handleSubmitClick() {
    try {
      setSaveFeedback({ type: "info", text: "正在校验并保存 LLM 配置..." });
      const values = await form.validateFields();
      const providers = values.agent_llm?.providers || [];
      if (!normalizeProviderName(values.default_provider_name) && providers.length === 1) {
        const fallbackDefault = normalizeProviderName(providers[0]?.provider);
        form.setFieldValue("default_provider_name", fallbackDefault);
        values.default_provider_name = fallbackDefault;
      }
      setSaving(true);
      await handleSave(values);
    } catch (error: any) {
      const errorCount = error?.errorFields?.length || 0;
      if (errorCount > 0) {
        setSaveFeedback({
          type: "warning",
          text: `校验未通过：还有 ${errorCount} 个配置项需要修正`,
        });
        message.error(`还有 ${errorCount} 个配置项未填写或格式不正确，请先修正`);
      } else if (error?.message) {
        setSaveFeedback({ type: "error", text: "保存失败: " + error.message });
        message.error("保存失败: " + error.message);
      } else {
        setSaveFeedback({
          type: "error",
          text: "保存失败，请检查网络连接或稍后重试",
        });
        message.error("保存失败，请检查网络连接或稍后重试");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <Alert
        type="info"
        showIcon
        message="统一 LLM 配置"
        description={
          <div>
            <p>1. 这里统一管理默认模型、多 Provider、模型列表与 API Key 状态。</p>
            <p>2. 已知 Provider 会尽量提供候选模型；自定义 Provider 支持手动输入模型名。</p>
            <p>3. API Key 仍然走加密存储，但入口已经并入这里，不再需要在别的页面重复配置。</p>
          </div>
        }
      />
      {saveFeedback && <Alert type={saveFeedback.type} showIcon message={saveFeedback.text} />}

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSave}
        onFinishFailed={(errorInfo) => {
          const errorCount = errorInfo?.errorFields?.length || 0;
          if (errorCount > 0) {
            message.error(`还有 ${errorCount} 个配置项未填写或格式不正确，请先修正`);
          }
        }}
        initialValues={buildInitialFormValues(config)}
        scrollToFirstError
      >
        <Form.Item name="default_provider_name" hidden>
          <Input />
        </Form.Item>
        <Card
          title={
            <span>
              <RobotOutlined /> LLM Provider 配置
            </span>
          }
          extra={
            <Button
              icon={<PlusOutlined />}
              htmlType="button"
              onClick={() => {
                const providers = form.getFieldValue(["agent_llm", "providers"]) || [];
                form.setFieldValue(["agent_llm", "providers"], [
                  ...providers,
                  {
                    provider: "",
                    api_base: "",
                    api_key_ref: "",
                    models: [],
                  },
                ]);
              }}
            >
              添加 Provider
            </Button>
          }
        >
          <div className="grid grid-cols-1 gap-4">
            <Form.Item
              name={["agent_llm", "temperature"]}
              label="Agent LLM 全局默认 Temperature"
            >
              <InputNumber style={{ width: "100%" }} min={0} max={2} step={0.1} />
            </Form.Item>
          </div>

          <Form.List name={["agent_llm", "providers"]}>
            {(fields, { remove }) => (
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
                  const isDefaultProvider =
                    normalizeProviderName(selectedDefaultProvider) === providerName;
                  const defaultModelName = form.getFieldValue([
                    "default_model",
                    "model_id",
                  ]);
                  const defaultModelConfig = inlineModels.find(
                    (item: any) => item?.name === defaultModelName
                  );

                  return (
                    <Card
                      key={field.key}
                      size="small"
                      title={
                        <Space>
                          <Text strong>{providerName || `Provider #${field.name + 1}`}</Text>
                          {providerKey?.is_configured ? (
                            <Tag color="green">Key 已配置</Tag>
                          ) : (
                            <Tag color="orange">Key 未配置</Tag>
                          )}
                          {isDefaultProvider && (
                            <Tag color="blue">当前默认</Tag>
                          )}
                        </Space>
                      }
                      extra={
                        <Space>
                          <Button
                            size="small"
                            icon={<StarOutlined />}
                            htmlType="button"
                            onClick={() => {
                              form.setFieldValue("default_provider_name", providerName);
                              syncDefaultModelFromProvider(providerName);
                            }}
                            disabled={!providerName || isDefaultProvider}
                          >
                            {isDefaultProvider ? "默认 Provider" : "设为默认"}
                          </Button>
                          <Button
                            size="small"
                            icon={<KeyOutlined />}
                            htmlType="button"
                            onClick={() => {
                              openKeyModal(providerName || "", !providerName);
                            }}
                          >
                            {providerKey?.is_configured ? "更新 Key" : "配置 Key"}
                          </Button>
                          {providerKey?.is_configured && providerName && (
                            <Popconfirm
                              title="确定删除该 Provider 的 API Key？"
                              onConfirm={() => handleDeleteKey(providerName)}
                            >
                              <Button
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                htmlType="button"
                              >
                                删除 Key
                              </Button>
                            </Popconfirm>
                          )}
                          <Button
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            htmlType="button"
                            onClick={() => {
                              const allProviders =
                                form.getFieldValue(["agent_llm", "providers"]) || [];
                              if (isDefaultProvider) {
                                const nextProvider = allProviders.find(
                                  (_: any, index: number) => index !== field.name
                                );
                                form.setFieldValue(
                                  "default_provider_name",
                                  normalizeProviderName(nextProvider?.provider)
                                );
                                form.setFieldValue(
                                  ["default_model", "model_id"],
                                  nextProvider?.models?.find((item: any) => item?.name)?.name
                                );
                              }
                              remove(field.name);
                            }}
                          >
                            删除 Provider
                          </Button>
                        </Space>
                      }
                    >
                      <div className="grid grid-cols-2 gap-4">
                        <Form.Item
                          name={[field.name, "provider"]}
                          label="Provider 名称"
                          rules={[
                            { required: true, message: "请输入 Provider 名称" },
                            {
                              pattern: /^[a-zA-Z0-9._\/-]+$/,
                              message:
                                "仅支持字母、数字、点、中划线、下划线和斜杠（如 proxy/tongyi）",
                            },
                          ]}
                        >
                          <AutoComplete
                            options={providerOptions}
                            placeholder="如 openai / deepseek / openrouter"
                            onChange={(value) => {
                              const normalizedValue = normalizeProviderName(value);
                              if (isDefaultProvider) {
                                form.setFieldValue(
                                  "default_provider_name",
                                  normalizedValue
                                );
                                syncDefaultModelFromProvider(normalizedValue);
                              }
                            }}
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
                        tooltip="保存后会自动优先使用加密密钥；这里显示的是引用名而不是明文 Key"
                      >
                        <Input placeholder="${secrets.openai_api_key}" />
                      </Form.Item>

                      {isDefaultProvider && (
                        <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
                          <div className="mb-3 flex items-center gap-2">
                            <StarOutlined />
                            <Text strong>默认模型设置</Text>
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <Form.Item
                              name={["default_model", "model_id"]}
                              label="默认模型"
                              rules={[{ required: true, message: "请选择默认模型" }]}
                            >
                              <AutoComplete
                                options={modelOptions.map((item) => ({
                                  value: item,
                                }))}
                                placeholder={
                                  loadingModels
                                    ? "加载候选模型中..."
                                    : "必须从当前 Provider 的模型列表中选择"
                                }
                                filterOption={(inputValue, option) =>
                                  (option?.value || "")
                                    .toLowerCase()
                                    .includes(inputValue.toLowerCase())
                                }
                              />
                            </Form.Item>
                            <Form.Item label="默认 Provider Key 状态">
                              <Space>
                                {providerKey?.is_configured ? (
                                  <Tag color="green">已配置</Tag>
                                ) : (
                                  <Tag color="orange">未配置</Tag>
                                )}
                                <Button
                                  icon={<KeyOutlined />}
                                  htmlType="button"
                                  onClick={() => {
                                    openKeyModal(providerName || "openai");
                                  }}
                                >
                                  配置 Key
                                </Button>
                              </Space>
                            </Form.Item>
                          </div>
                          <Text type="secondary">
                            默认 Temperature / Max Tokens 继承自下方所选默认模型对应的这一行配置。
                            {defaultModelConfig?.name
                              ? ` 当前默认模型为 ${defaultModelConfig.name}，Temperature=${defaultModelConfig.temperature ?? 0.7}，Max Tokens=${defaultModelConfig.max_new_tokens ?? 4096}${defaultModelConfig.is_multimodal ? '，支持图片输入' : ''}。`
                              : " 请先在下方模型列表中维护模型，再选择默认模型。"}
                          </Text>
                        </div>
                      )}

                      <div className="mb-2 flex items-center justify-between">
                        <Text strong>该 Provider 下的模型</Text>
                        <Button
                          size="small"
                          icon={<PlusOutlined />}
                          htmlType="button"
                          onClick={() => {
                            const models =
                              form.getFieldValue([
                                "agent_llm",
                                "providers",
                                field.name,
                                "models",
                              ]) || [];
                            form.setFieldValue(
                              ["agent_llm", "providers", field.name, "models"],
[
                                 ...models,
                                 {
                                   name: "",
                                   temperature: 0.7,
                                   max_new_tokens: 4096,
                                   is_multimodal: false,
                                 },
                               ]
                            );
                          }}
                        >
                          添加模型
                        </Button>
                      </div>

                      <Form.List name={[field.name, "models"]}>
                        {(modelFields, { remove: removeModel }) => (
                          <div className="space-y-3">
                            {modelFields.map((modelField) => (
                              <div
                                key={modelField.key}
                                className="rounded-lg border border-gray-200 p-3"
                              >
                                <div className="grid grid-cols-5 gap-3">
                                  <Form.Item
                                    name={[modelField.name, "name"]}
                                    label="模型名"
                                  >
                                    <AutoComplete
                                      options={modelOptions.map((item) => ({
                                        value: item,
                                      }))}
                                      placeholder="如 gpt-4o / deepseek-v3"
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
                                  >
                                    <InputNumber
                                      style={{ width: "100%" }}
                                      min={1}
                                      max={128000}
                                    />
                                  </Form.Item>
                                  <Form.Item
                                    name={[modelField.name, "is_multimodal"]}
                                    label="多模态"
                                    tooltip="是否支持图片输入"
                                  >
                                    <Switch
                                      checkedChildren="支持"
                                      unCheckedChildren="不支持"
                                    />
                                  </Form.Item>
                                  <Form.Item label="操作">
                                    <Button
                                      danger
                                      icon={<DeleteOutlined />}
                                      htmlType="button"
                                      onClick={() => {
                                        const currentModelName = form.getFieldValue([
                                          "agent_llm",
                                          "providers",
                                          field.name,
                                          "models",
                                          modelField.name,
                                          "name",
                                        ]);
                                        if (
                                          isDefaultProvider &&
                                          currentModelName &&
                                          currentModelName === defaultModelName
                                        ) {
                                          const siblingModels =
                                            form.getFieldValue([
                                              "agent_llm",
                                              "providers",
                                              field.name,
                                              "models",
                                            ]) || [];
                                          const nextModel = siblingModels.find(
                                            (_: any, index: number) =>
                                              index !== modelField.name &&
                                              siblingModels[index]?.name
                                          );
                                          form.setFieldValue(
                                            ["default_model", "model_id"],
                                            nextModel?.name
                                          );
                                        }
                                        removeModel(modelField.name);
                                      }}
                                    >
                                      删除
                                    </Button>
                                  </Form.Item>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </Form.List>
                    </Card>
                  );
                })}
              </div>
            )}
          </Form.List>
        </Card>

        <Form.Item className="mb-0">
          <Button
            type="primary"
            htmlType="button"
            onClick={handleSubmitClick}
            loading={loadingKeys || loadingModels || saving}
          >
            保存 LLM 配置
          </Button>
        </Form.Item>
      </Form>

      <Modal
        title={
          <span>
            <KeyOutlined />{" "}
            {editingProvider ? `配置 ${editingProvider} 的 API Key` : "配置 API Key"}
          </span>
        }
        open={keyModalVisible}
        onCancel={() => setKeyModalVisible(false)}
        onOk={() => keyForm.submit()}
      >
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message="安全提示"
          description="API Key 将被加密存储。保存后无法回显，只能更新或删除。"
        />
        <Form form={keyForm} layout="vertical" onFinish={handleSaveKey}>
          <Form.Item
            name="provider"
            label="Provider"
            rules={[
              { required: true, message: "请输入 Provider 名称" },
              {
                pattern: /^[a-zA-Z0-9._\/-]+$/,
                message:
                  "仅支持字母、数字、点、中划线、下划线和斜杠（如 proxy/tongyi）",
              },
            ]}
          >
            <Input
              disabled={!providerEditable}
              placeholder="如 openai / deepseek / openrouter"
              prefix={<LinkOutlined />}
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={[
              { required: true, message: "请输入 API Key" },
              { min: 6, message: "API Key 长度不能过短" },
            ]}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
