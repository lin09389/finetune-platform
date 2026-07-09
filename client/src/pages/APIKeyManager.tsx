import {
  CheckCircleOutlined,
  CloudOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Col,
  Form,
  Input,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { useOperation } from '../hooks/useOperation';
import { notify } from '../utils/notify';
import {
  extractApiErrorMessage,
  getSavedCloudProviderData,
  getSavedCloudProviders,
  testCloudProviderStream,
} from '../services/api';
import { deleteCloudApiKey, saveCloudApiKey, testCloudProvider } from '../services/cloudApi';

const { Text } = Typography;

interface APIKeyConfig {
  provider: string;
  api_key?: string;
  model?: string;
  group_id?: string;
  base_url?: string;
}

interface APIKeyInfo {
  id: string;
  provider: string;
  name: string;
  created_at: string;
  masked_key?: string;
  has_group_id?: boolean;
  note?: string;
  official_url?: string;
  interface_format?: string;
  base_url?: string;
  default_model?: string;
  models?: string[];
  streaming_status?: string;
  streaming_supported?: boolean | null;
  streaming_tested_at?: string | null;
  streaming_error?: string;
  streaming_chunks?: number | null;
  streaming_model?: string;
}

interface ProviderFormValues {
  provider: string;
  name?: string;
  note?: string;
  official_url?: string;
  interface_format: string;
  api_key: string;
  base_url?: string;
  default_model?: string;
  models_text?: string;
  group_id?: string;
}

interface APIKeyManagerProps {
  onConfigChange?: (config: APIKeyConfig) => void;
  initialConfig?: APIKeyConfig | null;
}

const interfaceOptions = [
  { value: 'openai-chat-completions', label: 'OpenAI Chat Completions' },
  { value: 'anthropic-messages', label: 'Anthropic Messages' },
  { value: 'minimax-native', label: 'Minimax Native' },
  { value: 'glm-native', label: 'GLM Native' },
];

const defaultValues: ProviderFormValues = {
  provider: '',
  name: '',
  note: '',
  official_url: '',
  interface_format: 'openai-chat-completions',
  api_key: '',
  base_url: '',
  default_model: '',
  models_text: '',
  group_id: '',
};

const streamStatusTag = (key: APIKeyInfo) => {
  if (key.streaming_supported) {
    return <Tag color="processing">流式已验证</Tag>;
  }
  if (key.streaming_status === 'failed' || key.streaming_status === 'unsupported') {
    return <Tag color="warning">流式未通过</Tag>;
  }
  return <Tag color="default">流式未测试</Tag>;
};

const splitModels = (value?: string) =>
  (value || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

const modelsToText = (models?: string[]) => (models || []).join('\n');

const builtinFormatByProvider: Record<string, string> = {
  minimax: 'minimax-native',
  'minimax-coding': 'minimax-native',
  glm: 'glm-native',
};

const loadLocalConfig = (): APIKeyConfig | null => {
  const savedConfig = localStorage.getItem('cloud_ai_config');
  if (!savedConfig) return null;
  try {
    return JSON.parse(savedConfig);
  } catch {
    return null;
  }
};

export const APIKeyManager: React.FC<APIKeyManagerProps> = ({ onConfigChange, initialConfig }) => {
  const [form] = Form.useForm<ProviderFormValues>();
  const [savedKeys, setSavedKeys] = useState<APIKeyInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [streamTestingProvider, setStreamTestingProvider] = useState<string>('');
  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const localConfig = useMemo(() => (initialConfig ? null : loadLocalConfig()), [initialConfig]);
  const operation = useOperation();

  const loadSavedKeys = useCallback(async (): Promise<APIKeyInfo[]> => {
    try {
      const data = await getSavedCloudProviders();
      const keys = data.keys || [];
      setSavedKeys(keys);
      return keys;
    } catch {
      return [];
    }
  }, []);

  const fillFormFromSavedKey = useCallback(async (key: APIKeyInfo) => {
    setSelectedProvider(key.provider);
    try {
      const data = await getSavedCloudProviderData(key.provider);
      form.setFieldsValue({
        provider: key.provider,
        name: data.name || key.name || key.provider,
        note: data.note || key.note || '',
        official_url: data.official_url || key.official_url || '',
        interface_format:
          data.interface_format || key.interface_format || builtinFormatByProvider[key.provider] || 'openai-chat-completions',
        api_key: '',
        base_url: data.base_url || key.base_url || '',
        default_model: data.default_model || key.default_model || '',
        models_text: modelsToText(data.models || key.models),
        group_id: data.group_id || '',
      });
    } catch {
      notify.error('加载配置失败');
    }
  }, [form]);

  useEffect(() => {
    let cancelled = false;

    const initialize = async () => {
      const provider = initialConfig?.provider || localConfig?.provider || '';
      if (provider) {
        setSelectedProvider(provider);
        form.setFieldsValue({
          ...defaultValues,
          provider,
          base_url: initialConfig?.base_url || localConfig?.base_url || '',
          default_model: initialConfig?.model || localConfig?.model || '',
          group_id: initialConfig?.group_id || localConfig?.group_id || '',
          interface_format: builtinFormatByProvider[provider] || 'openai-chat-completions',
        });
      } else {
        form.setFieldsValue(defaultValues);
      }

      const keys = await loadSavedKeys();
      if (cancelled || keys.length === 0) {
        return;
      }

      const matchedKey =
        keys.find((item: APIKeyInfo) => item.provider === provider) ||
        keys.find((item: APIKeyInfo) => item.provider === selectedProvider) ||
        (!provider && !selectedProvider ? keys[0] : null);

      if (matchedKey) {
        await fillFormFromSavedKey(matchedKey);
      }
    };

    void initialize();

    return () => {
      cancelled = true;
    };
  }, [fillFormFromSavedKey, form, initialConfig, loadSavedKeys, localConfig, selectedProvider]);

  const handleSave = async () => {
    let values: ProviderFormValues;
    try {
      values = await form.validateFields();
    } catch {
      notify.warning('请先补齐表单中的必填项');
      return;
    }

    setLoading(true);
    try {
      await operation.run(async () => {
        const models = splitModels(values.models_text);
        const provider = values.provider.trim().toLowerCase();
        try {
          await saveCloudApiKey({
            provider,
            api_key: values.api_key?.trim() || '',
            group_id: values.group_id || undefined,
            base_url: values.base_url || undefined,
            name: values.name || provider,
            note: values.note || undefined,
            official_url: values.official_url || undefined,
            interface_format: values.interface_format,
            default_model: values.default_model || models[0] || undefined,
            models,
          });
        } catch (error) {
          throw new Error(extractApiErrorMessage(error, '保存供应商配置失败'));
        }

        const config: APIKeyConfig = {
          provider,
          api_key: '',
          model: values.default_model || models[0] || '',
          group_id: values.group_id || undefined,
          base_url: values.base_url || undefined,
        };
        localStorage.setItem('cloud_ai_config', JSON.stringify(config));
        onConfigChange?.(config);
        setSelectedProvider(provider);
        form.setFieldsValue({ provider, api_key: '' });
        await loadSavedKeys();
      }, {
        key: 'save-provider',
        successText: '供应商配置已保存',
        errorText: '保存供应商配置',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    const provider = form.getFieldValue('provider');
    const baseUrl = form.getFieldValue('base_url');
    const groupId = form.getFieldValue('group_id');
    if (!provider) {
      notify.warning('请先填写供应商标识');
      return;
    }

    setTesting(true);
    try {
      await operation.run(async () => {
        let data;
        try {
          data = await testCloudProvider(provider, {
            base_url: baseUrl || undefined,
            group_id: groupId || undefined,
          });
        } catch (error) {
          throw new Error(extractApiErrorMessage(error, '连接测试未通过，请先保存 API Key'));
        }
        if (!data.success) {
          throw new Error(data.detail || data.message || '连接测试未通过，请先保存 API Key');
        }
        return data;
      }, {
        key: 'test-provider',
        successText: (data: { message?: string }) => data.message || '连接测试成功',
        errorText: '连接测试',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleTestStream = async (providerOverride?: string) => {
    const provider = providerOverride || form.getFieldValue('provider');
    const savedKey = providerOverride ? savedKeys.find((item) => item.provider === providerOverride) : undefined;
    const baseUrl = providerOverride ? savedKey?.base_url : form.getFieldValue('base_url');
    const groupId = providerOverride ? undefined : form.getFieldValue('group_id');
    if (!provider) {
      notify.warning('请先填写供应商标识');
      return;
    }

    setStreamTestingProvider(provider);
    try {
      await operation.run(async () => {
        const data = await testCloudProviderStream(provider, {
          base_url: baseUrl || undefined,
          group_id: groupId || undefined,
        });
        if (!data?.streaming_supported) {
          throw new Error(data?.message || '流式测试未通过');
        }
        await loadSavedKeys();
        return data;
      }, {
        key: `stream-test:${provider}`,
        successText: (data: { streaming_chunks?: number }) =>
          `流式测试通过，收到 ${data.streaming_chunks || 0} 个增量片段`,
        errorText: '流式测试',
      });
    } finally {
      setStreamTestingProvider('');
    }
  };

  const handleDeleteKey = async (provider: string) => {
    await operation.run(async () => {
      await deleteCloudApiKey(provider);
      if (selectedProvider === provider) {
        setSelectedProvider('');
        form.setFieldsValue(defaultValues);
      }
      await loadSavedKeys();
    }, {
      key: `delete-provider:${provider}`,
      successText: '已删除供应商配置',
      errorText: '删除供应商配置',
      confirm: {
        title: '删除这个供应商配置？',
        content: '删除后需要重新填写 API Key 才能继续使用该供应商。',
        okText: '删除',
        tone: 'danger',
      },
    });
  };

  const handleSelectSaved = async (key: APIKeyInfo) => {
    await fillFormFromSavedKey(key);
  };

  const handleClear = () => {
    setSelectedProvider('');
    localStorage.removeItem('cloud_ai_config');
    form.setFieldsValue(defaultValues);
    onConfigChange?.({ provider: '', api_key: '', model: '' });
  };

  return (
    <MotionList style={{ display: 'flex', flexDirection: 'column', gap: 20 }} stagger={0.08}>
      <MotionItem>
        <div
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 8,
            padding: '20px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <Space>
            <CloudOutlined style={{ fontSize: 20, color: 'var(--text-secondary)' }} />
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
                云端供应商配置
              </div>
              <Text type="secondary">自由添加 OpenAI Compatible 或内置云端模型供应商。</Text>
            </div>
          </Space>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void loadSavedKeys()}>
              刷新
            </Button>
            <Button icon={<ExperimentOutlined />} loading={testing} onClick={handleTest}>
              测试连接
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={Boolean(streamTestingProvider && streamTestingProvider === form.getFieldValue('provider'))}
              onClick={() => void handleTestStream()}
            >
              测试流式
            </Button>
            <Button onClick={handleClear}>清空表单</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={loading} onClick={handleSave}>
              保存配置
            </Button>
          </Space>
        </div>
      </MotionItem>

      <MotionItem>
        <Row gutter={[20, 20]} align="top">
          <Col xs={24} xl={7}>
            <div
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 8,
                padding: 16,
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>
                已保存供应商
              </div>
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {savedKeys.length === 0 && <Text type="secondary">暂无配置，先在右侧添加一个供应商。</Text>}
                {savedKeys.map((key) => (
                  <div
                    key={key.id}
                    role="button"
                    tabIndex={0}
                    aria-current={selectedProvider === key.provider ? 'true' : undefined}
                    aria-label={`选择 API 配置 ${key.name || key.provider}`}
                    style={{
                      border: selectedProvider === key.provider ? '1px solid var(--accent-primary)' : '1px solid var(--border-color)',
                      borderRadius: 8,
                      padding: 12,
                      cursor: 'pointer',
                      background: 'var(--bg-primary)',
                    }}
                    onClick={() => void handleSelectSaved(key)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        void handleSelectSaved(key);
                      }
                    }}
                  >
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                          {key.name || key.provider}
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {key.provider}
                        </Text>
                      </div>
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDeleteKey(key.provider);
                        }}
                      />
                    </Space>
                    <div style={{ marginTop: 8 }}>
                      <Tag>{key.interface_format || 'native'}</Tag>
                      {key.masked_key && <Tag color="success">{key.masked_key}</Tag>}
                      {streamStatusTag(key)}
                    </div>
                    {(key.streaming_error || key.streaming_tested_at || key.streaming_chunks != null) && (
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {key.streaming_supported
                            ? `最近流式测试：${key.streaming_chunks || 0} 个片段`
                            : key.streaming_error || '尚未验证真实流式输出'}
                        </Text>
                      </div>
                    )}
                    <Button
                      size="small"
                      style={{ marginTop: 8 }}
                      loading={streamTestingProvider === key.provider}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleTestStream(key.provider);
                      }}
                    >
                      测试流式
                    </Button>
                  </div>
                ))}
              </Space>
            </div>
          </Col>

          <Col xs={24} xl={17}>
            <div
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 8,
                padding: 24,
              }}
            >
              <Alert
                message="自定义供应商"
                description="供应商标识会作为配置中的唯一 ID。OpenAI Chat Completions 会调用 Base URL + /chat/completions；Anthropic Messages 会调用 Base URL + /messages。"
                type="info"
                showIcon
                style={{ marginBottom: 20 }}
              />

              <Form form={form} layout="vertical" initialValues={defaultValues}>
                <Form.Item
                  name="provider"
                  label="供应商标识"
                  rules={[
                    { required: true, message: '请输入供应商标识' },
                    {
                      transform: (value) => (typeof value === 'string' ? value.trim().toLowerCase() : value),
                      pattern: /^[a-z0-9-]+$/,
                      message: '只能使用小写字母、数字和连字符',
                    },
                  ]}
                  extra="配置文件中的唯一标识符，只能使用小写字母、数字和连字符"
                >
                  <Input
                    placeholder="my-provider"
                    size="large"
                    onBlur={() => {
                      const provider = form.getFieldValue('provider');
                      if (provider) {
                        form.setFieldValue('provider', provider.trim().toLowerCase());
                      }
                    }}
                  />
                </Form.Item>

                <Row gutter={20}>
                  <Col xs={24} md={12}>
                    <Form.Item name="name" label="供应商名称">
                      <Input placeholder="例如：Claude 官方" size="large" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="note" label="备注">
                      <Input placeholder="例如：公司专用账号" size="large" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item name="official_url" label="官网链接">
                  <Input placeholder="https://example.com（可选）" size="large" />
                </Form.Item>

                <Form.Item
                  name="interface_format"
                  label="接口格式"
                  rules={[{ required: true, message: '请选择接口格式' }]}
                  extra="选择 AI 服务的 API 接口格式"
                >
                  <Select options={interfaceOptions} size="large" />
                </Form.Item>

                <Form.Item
                  name="api_key"
                  label="API Key"
                  rules={[
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        const provider = getFieldValue('provider')?.trim().toLowerCase();
                        const hasSavedKey =
                          selectedProvider === provider || savedKeys.some((key) => key.provider === provider);
                        if (hasSavedKey || value?.trim()) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error('新增供应商时必须填写 API Key'));
                      },
                    }),
                  ]}
                  extra="新增供应商必填；编辑已有供应商时留空会保留原 API Key"
                >
                  <Input.Password
                    placeholder="新增时填写；编辑已有配置可留空"
                    size="large"
                    autoComplete="off"
                  />
                </Form.Item>

                <Form.Item
                  name="base_url"
                  label="Base URL"
                  rules={[
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (
                          !['openai-chat-completions', 'openai-compatible', 'anthropic-messages'].includes(
                            getFieldValue('interface_format'),
                          ) ||
                          value
                        ) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error('该接口格式需要填写 Base URL'));
                      },
                    }),
                  ]}
                  extra="自定义 API 端点地址"
                >
                  <Input placeholder="https://api.example.com/v1" size="large" />
                </Form.Item>

                <Row gutter={20}>
                  <Col xs={24} md={12}>
                    <Form.Item name="default_model" label="默认模型">
                      <Input placeholder="例如：gpt-4o-mini / claude-3-5-sonnet-latest" size="large" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="group_id" label="组织 / 项目 ID">
                      <Input placeholder="可选，例如 group_id / project_id" size="large" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item
                  name="models_text"
                  label="可选模型列表"
                  extra="一行一个模型，或用英文逗号分隔；用于页面选择和默认模型提示"
                >
                  <Input.TextArea
                    rows={4}
                    placeholder={'gpt-4o-mini\ngpt-4.1\nclaude-3-5-sonnet-latest'}
                  />
                </Form.Item>

                <Alert
                  message="保存后如何使用"
                  description="保存后，聊天等模块可以使用这个供应商标识作为 provider。API Key 会进入后端加密存储，localStorage 只保存 provider 和默认模型等非密钥信息。"
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                />
              </Form>
            </div>
          </Col>
        </Row>
      </MotionItem>
    </MotionList>
  );
};

export default APIKeyManager;
