import {
  CheckCircleOutlined,
  CloudOutlined,
  DeleteOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { Alert, Button, Divider, Input, message, Select, Space } from 'antd';
import { useEffect, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { API_BASE_URL } from '../services/api';

// 云端 AI 配置类型
interface APIKeyConfig {
  provider: string;
  api_key?: string; // 可选，因为可以使用 key_id
  model?: string;
  key_id?: string; // 后端加密存储的 Key ID
  group_id?: string; // Group ID（用于 Minimax）
  base_url?: string; // 自定义 Base URL
}

interface APIKeyInfo {
  id: string;
  provider: string;
  name: string;
  created_at: string;
}

interface APIKeyManagerProps {
  onConfigChange?: (config: APIKeyConfig) => void;
  initialConfig?: APIKeyConfig | null;
}

// 服务商选项（含官网链接和 API 地址）
const PROVIDER_OPTIONS = [
  {
    value: 'minimax-coding',
    label: '💻 Minimax Coding (编程专用)',
    description: '使用 Coding Plan 套餐，代码生成/优化专用',
    officialUrl: 'https://platform.minimaxi.com/',
    apiKeyUrl: 'https://platform.minimaxi.com/user-center/basic-information/interface-key',
    defaultBaseUrl: 'https://api.minimaxi.com/v1',
  },
  {
    value: 'minimax',
    label: '🔵 Minimax (通用)',
    description: '通用场景，中文优化好',
    officialUrl: 'https://platform.minimaxi.com/',
    apiKeyUrl: 'https://platform.minimaxi.com/user-center/basic-information/interface-key',
    defaultBaseUrl: 'https://api.minimaxi.com/v1',
  },
  {
    value: 'glm',
    label: '🟠 智谱 GLM',
    description: '智谱 AI，中文能力强',
    officialUrl: 'https://open.bigmodel.cn/',
    apiKeyUrl: 'https://open.bigmodel.cn/api-keys',
    defaultBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
  },
];

// 模型选项
const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  'minimax-coding': [
    { value: 'MiniMax-M2.5', label: 'MiniMax-M2.5 (Coding Plan 推荐)' },
    { value: 'MiniMax-Text-01', label: 'MiniMax-Text-01' },
    { value: 'abab6.5s-chat', label: 'abab6.5s-chat' },
  ],
  minimax: [
    { value: 'MiniMax-M2.5', label: 'MiniMax-M2.5 (推荐)' },
    { value: 'MiniMax-M2.5-highspeed', label: 'MiniMax-M2.5-highspeed (高速)' },
    { value: 'MiniMax-Text-01', label: 'MiniMax-Text-01' },
    { value: 'abab6.5s-chat', label: 'abab6.5s-chat (快速)' },
    { value: 'abab6.5g-chat', label: 'abab6.5g-chat (通用)' },
  ],
  glm: [
    { value: 'glm-4', label: 'glm-4 (最强)' },
    { value: 'glm-3-turbo', label: 'glm-3-turbo (快速)' },
    { value: 'glm-4v', label: 'glm-4v (多模态)' },
  ],
};

/**
 * API Key 管理组件
 *
 * 用于配置和管理云端 AI 的 API Key
 */
export const APIKeyManager: React.FC<APIKeyManagerProps> = ({ onConfigChange, initialConfig }) => {
  const [provider, setProvider] = useState(initialConfig?.provider || 'minimax-coding');
  const [apiKey, setApiKey] = useState(initialConfig?.api_key || '');
  const [groupId, setGroupId] = useState(initialConfig?.group_id || '');
  const [baseUrl, setBaseUrl] = useState(initialConfig?.base_url || '');
  const [model, setModel] = useState(initialConfig?.model || 'MiniMax-M2.5');
  const [_keyId, setKeyId] = useState(initialConfig?.key_id);
  const [savedKeys, setSavedKeys] = useState<APIKeyInfo[]>([]);
  const [saved, setSaved] = useState(false);

  // 加载保存的 API Keys
  const loadSavedKeys = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`);
      const data = await response.json();
      if (data.keys) {
        setSavedKeys(data.keys);
      }
    } catch (error) {
      console.error('加载 API Keys 失败:', error);
    }
  };

  // 加载保存的配置
  useEffect(() => {
    loadSavedKeys();

    const savedConfig = localStorage.getItem('cloud_ai_config');
    if (savedConfig && !initialConfig) {
      try {
        const config = JSON.parse(savedConfig);
        setProvider(config.provider);
        setApiKey(config.api_key);
        setGroupId(config.group_id || '');
        setBaseUrl(config.base_url || '');
        setModel(config.model || 'mini max2.5');
        setKeyId(config.key_id);
      } catch (e) {
        console.error('加载配置失败:', e);
      }
    }
  }, [initialConfig]);

  // 切换服务商时重置模型
  useEffect(() => {
    const models = MODEL_OPTIONS[provider];
    if (models?.length && !model) {
      const firstModel = models[0]?.value;
      if (firstModel) {
        setModel(firstModel);
      }
    }
  }, [provider]);

  // 保存到后端加密存储
  const handleSave = async () => {
    if (!apiKey.trim()) {
      message.error('请输入 API Key');
      return;
    }

    try {
      // 保存到后端加密存储
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          group_id: groupId || undefined,
          base_url: baseUrl || undefined,
          name: `${provider}-${new Date().toLocaleDateString()}`,
        }),
      });

      if (response.ok) {
        const data = await response.json();

        // 保存配置到本地（只存 key_id，不存明文 key）
        const config: APIKeyConfig = {
          provider,
          api_key: '', // 不存明文
          model,
          key_id: data.key_id,
          group_id: groupId || undefined,
          base_url: baseUrl || undefined,
        };
        localStorage.setItem('cloud_ai_config', JSON.stringify(config));

        setKeyId(data.key_id);
        setSaved(true);
        message.success('API Key 已加密保存');
        onConfigChange?.(config);
        loadSavedKeys();

        setTimeout(() => setSaved(false), 2000);
      } else {
        const error = await response.json();
        message.error(`保存失败：${error.detail}`);
      }
    } catch (error) {
      message.error('保存失败');
    }
  };

  // 清除配置
  const handleClear = () => {
    localStorage.removeItem('cloud_ai_config');
    setApiKey('');
    setKeyId(undefined);
    setSaved(false);
    onConfigChange?.({ provider: '', api_key: '', model: '' });
  };

  // 删除已保存的 Key
  const handleDeleteKey = async (keyId: string) => {
    try {
      await fetch(`${API_BASE_URL}/cloud/api-keys/${keyId}`, {
        method: 'DELETE',
      });
      message.success('已删除');
      loadSavedKeys();
    } catch (error) {
      message.error('删除失败');
    }
  };

  // 获取当前服务商描述
  const currentProvider = PROVIDER_OPTIONS.find((p) => p.value === provider);
  const currentModels = MODEL_OPTIONS[provider] || [];

  return (
    <MotionList style={{ display: 'flex', flexDirection: 'column', gap: 20 }} stagger={0.08}>
      {/* 标题栏 */}
      <MotionItem>
        <div
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 12,
            padding: '20px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <CloudOutlined style={{ fontSize: 20, color: 'var(--text-secondary)' }} />
            <span style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
              ☁️ 云端 AI 配置
            </span>
          </div>
          <Space>
            {saved && (
              <span style={{ color: 'var(--success)', marginRight: 8, fontWeight: 500 }}>
                ✓ 已保存
              </span>
            )}
            <Button onClick={handleClear} size="small">
              清除配置
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>
              保存配置
            </Button>
          </Space>
        </div>
      </MotionItem>

      {/* 已保存的 API Keys */}
      {savedKeys.length > 0 && (
        <MotionItem>
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: 12,
              padding: 20,
            }}
          >
            <div
              style={{
                fontWeight: 600,
                marginBottom: 12,
                color: 'var(--text-primary)',
                fontSize: 15,
              }}
            >
              已保存的 API Keys
            </div>
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              {savedKeys.map((key) => (
                <Space key={key.id} style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space>
                    <CheckCircleOutlined style={{ color: 'var(--success)' }} />
                    <div>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {key.name || key.provider}
                      </span>
                      <br />
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                        {key.provider} · {key.created_at}
                      </span>
                    </div>
                  </Space>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => handleDeleteKey(key.id)}
                  >
                    删除
                  </Button>
                </Space>
              ))}
            </Space>
          </div>
        </MotionItem>
      )}

      {/* 配置区 */}
      <MotionItem>
        <div
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 12,
            padding: 24,
          }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Alert
              message="Minimax Coding Plan"
              description={
                provider === 'minimax-coding'
                  ? '使用你的 Minimax 编程套餐，享受更强的代码生成和优化能力。格式：group_id:api_key'
                  : '切换到 Minimax Coding 可获得更好的编程体验'
              }
              type={provider === 'minimax-coding' ? 'success' : 'info'}
              showIcon
            />

            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text-primary)',
                }}
              >
                服务商
              </div>
              <Select
                value={provider}
                onChange={setProvider}
                options={PROVIDER_OPTIONS}
                style={{ width: '100%' }}
                size="large"
              />
              {currentProvider && (
                <div style={{ marginTop: 8 }}>
                  <span
                    style={{
                      color: 'var(--text-secondary)',
                      fontSize: 12,
                      display: 'block',
                      marginBottom: 4,
                    }}
                  >
                    {currentProvider.description}
                  </span>
                  <Space size="small">
                    <a
                      href={currentProvider.officialUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 12 }}
                    >
                      🏠 官网
                    </a>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>|</span>
                    <a
                      href={currentProvider.apiKeyUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 12 }}
                    >
                      🔑 获取 API Key
                    </a>
                  </Space>
                </div>
              )}
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text-primary)',
                }}
              >
                选择模型
              </div>
              <Select
                value={model}
                onChange={setModel}
                options={currentModels}
                style={{ width: '100%' }}
                size="large"
              />
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text-primary)',
                }}
              >
                Group ID
                <span
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    marginLeft: 8,
                    fontWeight: 400,
                  }}
                >
                  (可选，MiniMax 用户/组织 ID)
                </span>
              </div>
              <Input
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                placeholder="请输入 Group ID（可选）"
                size="large"
              />
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text-primary)',
                }}
              >
                Base URL
                <span
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    marginLeft: 8,
                    fontWeight: 400,
                  }}
                >
                  (API 请求地址)
                </span>
              </div>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={currentProvider?.defaultBaseUrl || '请输入 Base URL'}
                  size="large"
                  style={{ flex: 1 }}
                />
                <Button
                  size="large"
                  onClick={() => setBaseUrl(currentProvider?.defaultBaseUrl || '')}
                  disabled={!currentProvider?.defaultBaseUrl}
                >
                  使用默认
                </Button>
              </Space.Compact>
              {currentProvider?.defaultBaseUrl && (
                <span
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    marginTop: 4,
                    display: 'block',
                  }}
                >
                  默认地址：
                  <code
                    style={{
                      background: 'var(--bg-elevated)',
                      padding: '2px 6px',
                      borderRadius: 4,
                    }}
                  >
                    {currentProvider.defaultBaseUrl}
                  </code>
                </span>
              )}
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text-primary)',
                }}
              >
                API Key
                <span
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    marginLeft: 8,
                    fontWeight: 400,
                  }}
                >
                  (必填)
                </span>
              </div>
              <Input.TextArea
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="请输入 API Key"
                rows={3}
                size="large"
              />
            </div>

            <Alert
              message="如何获取 API Key？"
              description={
                provider.startsWith('minimax') ? (
                  <ol style={{ margin: 0, paddingLeft: 20 }}>
                    <li>
                      访问{' '}
                      <a href="https://platform.minimaxi.com/" target="_blank" rel="noreferrer">
                        Minimax 开放平台
                      </a>
                    </li>
                    <li>注册/登录账号（支持手机号、微信）</li>
                    <li>进入「控制台」→「API Key 管理」</li>
                    <li>点击「创建 API Key」并复制</li>
                    <li>如有 Group ID（用户/组织ID），一并填入</li>
                  </ol>
                ) : provider === 'glm' ? (
                  <ol style={{ margin: 0, paddingLeft: 20 }}>
                    <li>
                      访问{' '}
                      <a href="https://open.bigmodel.cn/" target="_blank" rel="noreferrer">
                        智谱 AI 开放平台
                      </a>
                    </li>
                    <li>注册/登录账号</li>
                    <li>进入「API Keys」页面</li>
                    <li>点击「创建 API Key」并复制</li>
                  </ol>
                ) : (
                  <ol style={{ margin: 0, paddingLeft: 20 }}>
                    <li>访问对应服务商官网注册账号</li>
                    <li>在控制台获取 API Key</li>
                    <li>填入 API Key 和 Base URL</li>
                  </ol>
                )
              }
              type="success"
              showIcon
              icon={<CloudOutlined />}
            />

            <Alert
              message="💰 费用提示"
              description={
                provider.startsWith('minimax') ? (
                  <div>
                    <span>Minimax Coding Plan 套餐内调用免费，超额后约 ¥0.01-0.03/1k tokens。</span>
                    <br />
                    <span style={{ color: 'var(--text-secondary)' }}>
                      建议定期检查剩余额度，设置用量提醒。
                    </span>
                  </div>
                ) : provider === 'glm' ? (
                  <div>
                    <span>智谱 GLM 新用户有免费额度，按量计费约 ¥0.01-0.1/1k tokens。</span>
                    <br />
                    <span style={{ color: 'var(--text-secondary)' }}>
                      GLM-4 价格较高，GLM-3-turbo 性价比更好。
                    </span>
                  </div>
                ) : (
                  <span>请查看对应服务商的定价策略。</span>
                )
              }
              type="warning"
              showIcon
              style={{ marginTop: 8 }}
            />
          </Space>
        </div>
      </MotionItem>
    </MotionList>
  );
};

export default APIKeyManager;
