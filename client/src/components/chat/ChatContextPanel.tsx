import {
  ApiOutlined,
  BookOutlined,
  CloudOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Segmented, Select, Switch, Tooltip, Typography } from 'antd';
import React from 'react';
import styles from './ChatContextPanel.module.css';

const { Text } = Typography;

type AutonomyMode = 'safe_auto' | 'confirm_all' | 'read_only';
type RoutingMode = 'auto' | 'chat' | 'agent';

interface BackendInfo {
  id: string;
  name: string;
  available: boolean;
}

interface ChatContextPanelProps {
  mobile?: boolean;
  currentBackend: string;
  backends: BackendInfo[];
  onBackendChange: (backend: string) => void;
  currentModel?: string;
  models: { id: string; name: string }[];
  onModelChange: (model: string) => void;
  useCloudAI: boolean;
  onToggleCloudAI: () => void;
  cloudAIConfigured: boolean;
  onOpenCloudAIConfig: () => void;
  currentCloudProvider?: string;
  cloudProviders: { id: string; name: string }[];
  onCloudProviderChange: (provider: string) => void;
  currentCloudModel?: string;
  cloudModels: { id: string; name: string }[];
  onCloudModelChange: (model: string) => void;
  useKnowledge: boolean;
  onToggleKnowledge: () => void;
  collectionsCount: number;
  currentKnowledgeCollection?: string;
  knowledgeCollections: { id: string; name: string; count: number }[];
  onKnowledgeCollectionChange: (collectionId: string) => void;
  useMemory: boolean;
  onToggleMemory: () => void;
  agentModeAvailable: boolean;
  agentOptions: { value: string; label: string }[];
  selectedAgent: string;
  onAgentChange: (agentId: string) => void;
  routingMode: RoutingMode;
  onRoutingModeChange: (mode: RoutingMode) => void;
  routing: boolean;
  autonomyMode: AutonomyMode;
  onAutonomyModeChange: (mode: AutonomyMode) => void;
  workflowTemplateOptions: { value: string; label: string }[];
  selectedWorkflowTemplate: string;
  onWorkflowTemplateChange: (templateId: string) => void;
  creatingWorkflow: boolean;
  isLoading: boolean;
  isStreaming: boolean;
}

const autonomyLabels: Record<AutonomyMode, string> = {
  safe_auto: '安全自动',
  confirm_all: '确认',
  read_only: '只读',
};

const routingHints: Record<RoutingMode, string> = {
  auto: '普通问题走对话，开发任务自动交给 Agent。',
  chat: '只进行普通对话，不触发 Agent。',
  agent: '直接按项目任务进入 Agent。',
};

const ChatContextPanel: React.FC<ChatContextPanelProps> = ({
  mobile = false,
  currentBackend,
  backends,
  onBackendChange,
  currentModel,
  models,
  onModelChange,
  useCloudAI,
  onToggleCloudAI,
  cloudAIConfigured,
  onOpenCloudAIConfig,
  currentCloudProvider,
  cloudProviders,
  onCloudProviderChange,
  currentCloudModel,
  cloudModels,
  onCloudModelChange,
  useKnowledge,
  onToggleKnowledge,
  collectionsCount,
  currentKnowledgeCollection,
  knowledgeCollections,
  onKnowledgeCollectionChange,
  useMemory,
  onToggleMemory,
  agentModeAvailable,
  agentOptions,
  selectedAgent,
  onAgentChange,
  routingMode,
  onRoutingModeChange,
  routing,
  autonomyMode,
  onAutonomyModeChange,
  workflowTemplateOptions,
  selectedWorkflowTemplate,
  onWorkflowTemplateChange,
  creatingWorkflow,
  isLoading,
  isStreaming,
}) => {
  const busy = isLoading || isStreaming || creatingWorkflow || routing;
  const backendOptions = backends.map((backend) => ({
    value: backend.id,
    label: backend.available ? backend.name : `${backend.name} (不可用)`,
    disabled: !backend.available,
  }));
  const modelOptions = models.map((model) => ({ value: model.id, label: model.name }));
  const cloudProviderOptions = cloudProviders.map((provider) => ({
    value: provider.id,
    label: provider.name,
  }));
  const cloudModelOptions = cloudModels.map((model) => ({ value: model.id, label: model.name }));
  const knowledgeCollectionOptions = knowledgeCollections.map((collection) => ({
    value: collection.id,
    label: `${collection.name} (${collection.count})`,
  }));

  const handleCloudToggle = () => {
    if (!cloudAIConfigured) {
      onOpenCloudAIConfig();
      return;
    }
    onToggleCloudAI();
  };

  return (
    <aside className={`${styles.panel} ${mobile ? styles.mobilePanel : ''}`} aria-label="对话上下文设置">
      <div className={styles.panelInner}>
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <RobotOutlined />
              运行模型
            </div>
            <span className={styles.modePill}>
              <span className={`${styles.modeDot} ${useCloudAI ? styles.modeDotCloud : ''}`} />
              {useCloudAI ? '云端' : '本地'}
            </span>
          </div>

          <div className={styles.statusLine}>
            <span>云端 AI</span>
            <Switch size="small" checked={useCloudAI} onChange={handleCloudToggle} />
          </div>

          {useCloudAI ? (
            <>
              <div className={styles.field}>
                <span className={styles.label}>服务商</span>
                <Select
                  className={styles.select}
                  value={currentCloudProvider}
                  options={cloudProviderOptions}
                  onChange={onCloudProviderChange}
                  placeholder="选择云端服务商"
                  disabled={busy || cloudProviderOptions.length === 0}
                />
              </div>
              <div className={styles.field}>
                <span className={styles.label}>云端模型</span>
                <Select
                  className={styles.select}
                  value={currentCloudModel}
                  options={cloudModelOptions}
                  onChange={onCloudModelChange}
                  placeholder="选择云端模型"
                  disabled={busy || cloudModelOptions.length === 0}
                />
              </div>
              <Button icon={<SettingOutlined />} onClick={onOpenCloudAIConfig}>
                管理 API Key
              </Button>
            </>
          ) : (
            <>
              <div className={styles.field}>
                <span className={styles.label}>推理后端</span>
                <Select
                  className={styles.select}
                  value={currentBackend}
                  options={backendOptions}
                  onChange={onBackendChange}
                  disabled={busy}
                />
              </div>
              <div className={styles.field}>
                <span className={styles.label}>模型</span>
                <Select
                  className={styles.select}
                  value={currentModel}
                  options={modelOptions}
                  onChange={onModelChange}
                  placeholder={currentBackend === 'ollama' ? '选择 Ollama 模型' : '选择模型'}
                  disabled={busy}
                  loading={models.length === 0}
                />
              </div>
            </>
          )}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <BookOutlined />
              知识与记忆
            </div>
          </div>

          <Tooltip title={collectionsCount === 0 ? '请先在知识库页面上传文档' : undefined}>
            <div className={styles.statusLine}>
              <span>知识库检索</span>
              <Switch
                size="small"
                checked={useKnowledge}
                onChange={onToggleKnowledge}
                disabled={collectionsCount === 0}
              />
            </div>
          </Tooltip>

          {useKnowledge && collectionsCount > 0 && (
            <div className={styles.field}>
              <span className={styles.label}>知识集合</span>
              <Select
                className={styles.select}
                value={currentKnowledgeCollection}
                options={knowledgeCollectionOptions}
                onChange={onKnowledgeCollectionChange}
                placeholder="选择知识集合"
              />
            </div>
          )}

          <div className={styles.statusLine}>
            <span>记忆系统</span>
            <Switch size="small" checked={useMemory} onChange={onToggleMemory} />
          </div>

          <Text className={styles.muted}>
            当前可用知识集合 {collectionsCount} 个，记忆{useMemory ? '已开启' : '未开启'}。
          </Text>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <ApiOutlined />
              Agent 路由
            </div>
            <span className={styles.sectionHint}>{routing ? '判断中' : autonomyLabels[autonomyMode]}</span>
          </div>

          <Segmented
            className={styles.segmented}
            value={routingMode}
            options={[
              { label: '自动', value: 'auto' },
              { label: '对话', value: 'chat' },
              { label: 'Agent', value: 'agent' },
            ]}
            onChange={(mode) => onRoutingModeChange(mode as RoutingMode)}
            disabled={busy}
          />
          <Text className={styles.muted}>{routingHints[routingMode]}</Text>

          {agentModeAvailable && (
            <div className={styles.field}>
              <span className={styles.label}>主 Agent</span>
              <Select
                className={styles.select}
                value={selectedAgent}
                options={agentOptions}
                onChange={onAgentChange}
                disabled={busy}
              />
            </div>
          )}

          {routingMode !== 'chat' && (
            <Segmented
              className={styles.segmented}
              value={autonomyMode}
              options={[
                { label: '安全自动', value: 'safe_auto' },
                { label: '确认', value: 'confirm_all' },
                { label: '只读', value: 'read_only' },
              ]}
              onChange={(mode) => onAutonomyModeChange(mode as AutonomyMode)}
              disabled={busy}
            />
          )}

          {workflowTemplateOptions.length > 1 && (
            <div className={styles.field}>
              <span className={styles.label}>Agent 任务模板</span>
              <Select
                className={styles.select}
                value={selectedWorkflowTemplate}
                options={workflowTemplateOptions}
                onChange={onWorkflowTemplateChange}
                disabled={busy}
              />
            </div>
          )}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionTitle}>
            <CloudOutlined />
            当前摘要
          </div>
          <div className={styles.statusLine}>
            <span>模式</span>
            <span className={styles.statusValue}>{useCloudAI ? '云端 AI' : currentBackend}</span>
          </div>
          <div className={styles.statusLine}>
            <span>模型</span>
            <span className={styles.statusValue}>{useCloudAI ? currentCloudModel || '未选择' : currentModel || '未选择'}</span>
          </div>
          <div className={styles.statusLine}>
            <span>路由</span>
            <span className={styles.statusValue}>{routingMode === 'auto' ? '自动' : routingMode === 'chat' ? '普通对话' : 'Agent 工作'}</span>
          </div>
        </section>
      </div>
    </aside>
  );
};

export default ChatContextPanel;
