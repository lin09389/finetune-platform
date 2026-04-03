import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  List,
  Modal,
  Segmented,
  Select,
  Slider,
  Space,
  Switch,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  ClearOutlined,
  CloudOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import AnimatedLayout from '../../components/shared/AnimatedLayout'
import ChatHistoryDrawer from '../../components/ChatHistoryDrawer'
import MemoryManager from '../../components/MemoryManager'
import APIKeyManager from '../APIKeyManager'
import { useChatStream } from '../../hooks/chat/useChatStream'
import { useChatStore } from '../../store/chatStore'
import { API_BASE_URL, getBackends, getInferenceModels, getOllamaStatus } from '../../services/api'
import type { PlaygroundAttachment, PlaygroundSnapshot } from '../../types'

const { Paragraph, Text, Title } = Typography
const { TextArea } = Input

interface APIKeyConfig {
  provider: string
  api_key?: string
  key_id?: string
  model?: string
  group_id?: string
  base_url?: string
}

interface ModelOption {
  id: string
  name: string
}

interface KnowledgeCollection {
  id: string
  name: string
  count: number
}

const pageStyle: React.CSSProperties = {
  minHeight: 'calc(100vh - 72px)',
  padding: 20,
  background:
    'radial-gradient(circle at top left, rgba(22,119,255,0.10), transparent 28%), linear-gradient(135deg, #f8fbff 0%, #eef4ff 55%, #f5f7fb 100%)',
}

const shellStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateRows: 'auto 1fr',
  gap: 16,
  minHeight: 'calc(100vh - 112px)',
}

const topBarStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 16,
  padding: 16,
  borderRadius: 24,
  background: 'rgba(255,255,255,0.82)',
  border: '1px solid rgba(15, 23, 42, 0.08)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 20px 50px rgba(15, 23, 42, 0.08)',
  flexWrap: 'wrap',
}

const bodyStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(360px, 480px) minmax(0, 1fr)',
  gap: 16,
  minHeight: 0,
}

const panelStyle: React.CSSProperties = {
  borderRadius: 24,
  background: 'rgba(255,255,255,0.88)',
  border: '1px solid rgba(15, 23, 42, 0.08)',
  boxShadow: '0 18px 45px rgba(15, 23, 42, 0.08)',
}

const scrollPanelStyle: React.CSSProperties = {
  ...panelStyle,
  overflow: 'hidden',
  display: 'grid',
  gridTemplateRows: '1fr',
  minHeight: 0,
}

function isJsonLike(text: string) {
  const trimmed = text.trim()
  return trimmed.startsWith('{') || trimmed.startsWith('[')
}

function formatResponseContent(text: string, responseFormat: 'text' | 'json') {
  if (responseFormat !== 'json' && !isJsonLike(text)) {
    return null
  }

  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return null
  }
}

async function readAttachment(file: File): Promise<PlaygroundAttachment> {
  const id = `attachment_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

  if (file.type.startsWith('image/')) {
    const previewUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error(`Failed to read file: ${file.name}`))
      reader.readAsDataURL(file)
    })

    return {
      id,
      name: file.name,
      type: 'image',
      mimeType: file.type,
      size: file.size,
      previewUrl,
      content: previewUrl,
    }
  }

  const content = await file.text()
  return {
    id,
    name: file.name,
    type: 'text',
    mimeType: file.type || 'text/plain',
    size: file.size,
    content,
  }
}

const ChatPage: React.FC = () => {
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const {
    sessions,
    currentSessionId,
    messages,
    settings,
    promptDraft,
    attachments,
    selectedExperimentId,
    responseView,
    lastRunMetadata,
    experimentSnapshots,
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    clearMessages,
    updateSettings,
    setPromptDraft,
    setAttachments,
    removeAttachment,
    clearAttachments,
    addExperimentSnapshot,
    setSelectedExperimentId,
    setResponseView,
    setLastRunMetadata,
  } = useChatStore()

  const [collections, setCollections] = useState<KnowledgeCollection[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [localModels, setLocalModels] = useState<Record<'ollama' | 'huggingface', ModelOption[]>>({
    ollama: [],
    huggingface: [],
  })
  const [cloudModels] = useState<ModelOption[]>([
    { id: 'MiniMax-M2.5', name: 'MiniMax-M2.5' },
    { id: 'MiniMax-M2.5-highspeed', name: 'MiniMax-M2.5 Highspeed' },
    { id: 'glm-4', name: 'GLM-4' },
    { id: 'glm-4v', name: 'GLM-4V' },
  ])
  const [availableBackends, setAvailableBackends] = useState<
    Array<{ id: 'ollama' | 'huggingface'; name: string; available: boolean }>
  >([])
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null)

  const {
    sendMessage,
    sendCloudMessage,
    stop: stopStream,
    isStreaming,
    state: streamState,
  } = useChatStream({
    onError: (error) => message.error(error),
  })

  const selectedSnapshot = useMemo(() => {
    if (selectedExperimentId) {
      return (
        experimentSnapshots.find((snapshot) => snapshot.id === selectedExperimentId) || lastRunMetadata
      )
    }
    return lastRunMetadata
  }, [experimentSnapshots, lastRunMetadata, selectedExperimentId])

  const currentModelOptions = useMemo(() => {
    if (settings.backend === 'cloud') {
      return cloudModels
    }

    return localModels[settings.backend] || []
  }, [cloudModels, localModels, settings.backend])

  const canUseImageAttachments =
    settings.backend === 'cloud' &&
    cloudAIConfig?.provider === 'glm' &&
    (settings.modelId || cloudAIConfig?.model) === 'glm-4v'

  const loadCollections = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections`)
      if (!response.ok) {
        throw new Error('Failed to load knowledge collections.')
      }

      const data = await response.json()
      const nextCollections = (data.collections || []).map((collection: { name: string; count?: number }) => ({
        id: collection.name,
        name: collection.name,
        count: collection.count || 0,
      }))

      setCollections(nextCollections)
      if (!settings.knowledgeCollection && nextCollections.length > 0) {
        updateSettings({ knowledgeCollection: nextCollections[0].id })
      }
    } catch (error) {
      console.error('Failed to load knowledge collections:', error)
    }
  }, [settings.knowledgeCollection, updateSettings])

  const loadCloudAIConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`)
      if (!response.ok) {
        throw new Error('Failed to load cloud API keys.')
      }

      const data = await response.json()
      const firstKey = data.keys?.[0]
      if (!firstKey) {
        return
      }

      const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${firstKey.id}/data`)
        .then((res) => res.json())
        .catch(() => ({}))

      const nextConfig: APIKeyConfig = {
        provider: firstKey.provider,
        api_key: '',
        key_id: firstKey.id,
        model: firstKey.provider === 'glm' ? 'glm-4' : 'MiniMax-M2.5',
        group_id: keyData.group_id || '',
        base_url: keyData.base_url || '',
      }

      setCloudAIConfig(nextConfig)
      if (settings.backend === 'cloud' && !settings.modelId) {
        updateSettings({ modelId: nextConfig.model || 'MiniMax-M2.5' })
      }
    } catch (error) {
      console.log('No saved cloud AI config found.', error)
    }
  }, [settings.backend, settings.modelId, updateSettings])

  const loadBackends = useCallback(async () => {
    try {
      const backendsData = await getBackends()
      const nextBackends = (backendsData.backends || []).filter(
        (backend: { id: string }) => backend.id === 'ollama' || backend.id === 'huggingface'
      )
      setAvailableBackends(nextBackends)

      const [ollamaStatus, huggingfaceModels] = await Promise.allSettled([
        getOllamaStatus(),
        getInferenceModels(),
      ])

      const nextLocalModels: Record<'ollama' | 'huggingface', ModelOption[]> = {
        ollama:
          ollamaStatus.status === 'fulfilled'
            ? (ollamaStatus.value.models || []).map((model: { name: string }) => ({
                id: model.name,
                name: model.name,
              }))
            : [],
        huggingface:
          huggingfaceModels.status === 'fulfilled'
            ? (huggingfaceModels.value || []).map((model: { id: string; name?: string }) => ({
                id: model.id,
                name: model.name || model.id,
              }))
            : [],
      }

      setLocalModels(nextLocalModels)

      if (!settings.modelId || settings.backend === 'cloud') {
        return
      }

      const currentBackendModels = nextLocalModels[settings.backend]
      if (currentBackendModels.length > 0) {
        updateSettings({ modelId: currentBackendModels[0]!.id })
      }
    } catch (error) {
      console.error('Failed to load backends:', error)
    }
  }, [settings.backend, settings.modelId, updateSettings])

  useEffect(() => {
    Promise.allSettled([loadBackends(), loadSessions(), loadCloudAIConfig(), loadCollections()])
  }, [loadBackends, loadCloudAIConfig, loadCollections, loadSessions])

  useEffect(() => {
    if (!settings.modelId && currentModelOptions.length > 0) {
      updateSettings({ modelId: currentModelOptions[0]!.id })
    }
  }, [currentModelOptions, settings.modelId, updateSettings])

  const handleAttachFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return

      try {
        const nextAttachments = await Promise.all(Array.from(files).map((file) => readAttachment(file)))
        const hasUnsupportedImage = nextAttachments.some(
          (attachment) => attachment.type === 'image' && !canUseImageAttachments
        )

        if (hasUnsupportedImage) {
          message.warning('Image attachments currently require cloud mode with GLM-4V.')
        }

        setAttachments([
          ...attachments,
          ...nextAttachments.filter(
            (attachment) => attachment.type === 'text' || canUseImageAttachments
          ),
        ])
      } catch (error) {
        message.error(error instanceof Error ? error.message : 'Failed to attach files.')
      }
    },
    [attachments, canUseImageAttachments, setAttachments]
  )

  const handleNewExperiment = useCallback(() => {
    clearMessages()
    setPromptDraft('')
    clearAttachments()
    setSelectedExperimentId(null)
    setLastRunMetadata(null)
  }, [clearAttachments, clearMessages, setLastRunMetadata, setPromptDraft, setSelectedExperimentId])

  const handleRun = useCallback(async () => {
    const prompt = promptDraft.trim()
    if (!prompt) {
      message.warning('Enter a prompt before running the experiment.')
      return
    }

    if (!settings.modelId) {
      message.warning('Choose a model first.')
      return
    }

    if (attachments.some((attachment) => attachment.type === 'image') && !canUseImageAttachments) {
      message.error('Image attachments are only available for cloud mode with GLM-4V right now.')
      return
    }

    if (settings.backend === 'cloud' && !cloudAIConfig) {
      setConfigModalOpen(true)
      return
    }

    const result =
      settings.backend === 'cloud' && cloudAIConfig
        ? await sendCloudMessage(
            {
              prompt,
              systemPrompt: settings.systemPrompt,
              responseFormat: settings.responseFormat,
              attachments,
              parameterOverrides: {
                temperature: settings.temperature,
                topP: settings.topP,
                maxTokens: settings.maxTokens,
                modelId: settings.modelId,
              },
            },
            {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: settings.modelId,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          )
        : await sendMessage({
            prompt,
            systemPrompt: settings.systemPrompt,
            responseFormat: settings.responseFormat,
            attachments,
            parameterOverrides: {
              temperature: settings.temperature,
              topP: settings.topP,
              maxTokens: settings.maxTokens,
              modelId: settings.modelId,
              backend: settings.backend,
            },
          })

    if (!result) {
      return
    }

    const snapshot: PlaygroundSnapshot = {
      id: `experiment_${Date.now()}`,
      createdAt: new Date().toISOString(),
      title: prompt.slice(0, 48) || 'Untitled experiment',
      response: result.content,
      raw_response: result.metadata?.rawResponse,
      knowledge_sources: result.metadata?.knowledgeSources,
      retrieval_info: result.metadata?.retrievalInfo,
      memory_context: result.metadata?.memoryContext,
      unified_context: result.metadata?.unifiedContext,
      experiment_config: {
        prompt,
        systemPrompt: settings.systemPrompt,
        responseFormat: settings.responseFormat,
        modelId: settings.modelId,
        backend: settings.backend,
        temperature: settings.temperature,
        topP: settings.topP,
        maxTokens: settings.maxTokens,
        useKnowledge: settings.useKnowledge,
        knowledgeCollection: settings.knowledgeCollection,
        useMemory: settings.useMemory,
        autoRetrieve: settings.autoRetrieve,
        attachments,
      },
      run_metrics: result.metadata?.runMetrics,
    }

    addExperimentSnapshot(snapshot)
    setResponseView('response')

    if (!currentSessionId) {
      await createSession(snapshot.title, settings.modelId)
    }
  }, [
    addExperimentSnapshot,
    attachments,
    canUseImageAttachments,
    cloudAIConfig,
    createSession,
    currentSessionId,
    promptDraft,
    sendCloudMessage,
    sendMessage,
    setResponseView,
    settings,
  ])

  const handleLoadSnapshot = useCallback(
    (snapshot: PlaygroundSnapshot) => {
      setPromptDraft(snapshot.experiment_config.prompt)
      updateSettings({
        systemPrompt: snapshot.experiment_config.systemPrompt,
        responseFormat: snapshot.experiment_config.responseFormat,
        backend: snapshot.experiment_config.backend,
        modelId: snapshot.experiment_config.modelId,
        temperature: snapshot.experiment_config.temperature,
        topP: snapshot.experiment_config.topP,
        maxTokens: snapshot.experiment_config.maxTokens,
        useKnowledge: snapshot.experiment_config.useKnowledge,
        knowledgeCollection: snapshot.experiment_config.knowledgeCollection,
        useMemory: snapshot.experiment_config.useMemory,
        autoRetrieve: snapshot.experiment_config.autoRetrieve,
      })
      setAttachments(snapshot.experiment_config.attachments || [])
      setSelectedExperimentId(snapshot.id)
      setLastRunMetadata(snapshot)
      setResponseView('response')
    },
    [setAttachments, setLastRunMetadata, setPromptDraft, setResponseView, setSelectedExperimentId, updateSettings]
  )

  const latestAssistantMessage = [...messages].reverse().find((msg) => msg.role === 'assistant')
  const responseContent =
    (isStreaming ? streamState.content : selectedSnapshot?.response) ||
    latestAssistantMessage?.content ||
    ''
  const formattedJson = formatResponseContent(
    responseContent,
    selectedSnapshot?.experiment_config.responseFormat || settings.responseFormat
  )

  const responseTabs = [
    {
      key: 'response',
      label: 'Response',
      children: responseContent ? (
        formattedJson ? (
          <pre data-testid="response-json" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
            {formattedJson}
          </pre>
        ) : (
          <div data-testid="response-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{responseContent}</ReactMarkdown>
          </div>
        )
      ) : (
        <Empty description="Run an experiment to see the model response." />
      ),
    },
    {
      key: 'sources',
      label: 'Sources',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {selectedSnapshot?.knowledge_sources?.length ? (
            <Card size="small" title="Knowledge Sources">
              <List
                dataSource={selectedSnapshot.knowledge_sources}
                renderItem={(source) => (
                  <List.Item>
                    <Space direction="vertical" size={4}>
                      <Text strong>{source.source}</Text>
                      <Text type="secondary">Score: {source.score?.toFixed?.(3) ?? source.score}</Text>
                      <Text>{source.content_preview}</Text>
                    </Space>
                  </List.Item>
                )}
              />
            </Card>
          ) : null}
          {selectedSnapshot?.retrieval_info ? (
            <Card size="small" title="Retrieval">
              <Paragraph style={{ marginBottom: 8 }}>Query: {selectedSnapshot.retrieval_info.query}</Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>Method: {selectedSnapshot.retrieval_info.method}</Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                Results: {selectedSnapshot.retrieval_info.total_results} in{' '}
                {selectedSnapshot.retrieval_info.retrieval_time}s
              </Paragraph>
            </Card>
          ) : null}
          {selectedSnapshot?.memory_context ? (
            <Card size="small" title="Memory Context">
              <Paragraph style={{ marginBottom: 8 }}>
                Retrieved: {selectedSnapshot.memory_context.retrieved ? 'Yes' : 'No'}
              </Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>
                Sources: {selectedSnapshot.memory_context.sources_count}
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                {selectedSnapshot.memory_context.context_preview || 'No preview available.'}
              </Paragraph>
            </Card>
          ) : null}
          {!selectedSnapshot?.knowledge_sources?.length &&
          !selectedSnapshot?.retrieval_info &&
          !selectedSnapshot?.memory_context ? (
            <Empty description="No retrieval or memory sources were returned for this run." />
          ) : null}
        </Space>
      ),
    },
    {
      key: 'metadata',
      label: 'Metadata',
      children: selectedSnapshot?.run_metrics ? (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Text>Model: {selectedSnapshot.run_metrics.model || selectedSnapshot.experiment_config.modelId}</Text>
          <Text>Backend: {selectedSnapshot.run_metrics.backend || selectedSnapshot.experiment_config.backend}</Text>
          <Text>Duration: {selectedSnapshot.run_metrics.duration_ms ?? 0} ms</Text>
          <Text>Prompt tokens: {selectedSnapshot.run_metrics.prompt_tokens ?? 0}</Text>
          <Text>Completion tokens: {selectedSnapshot.run_metrics.completion_tokens ?? 0}</Text>
          <Text>Total tokens: {selectedSnapshot.run_metrics.total_tokens ?? 0}</Text>
          <Text>Knowledge used: {selectedSnapshot.run_metrics.used_knowledge ? 'Yes' : 'No'}</Text>
          <Text>Memory used: {selectedSnapshot.run_metrics.used_memory ? 'Yes' : 'No'}</Text>
        </Space>
      ) : (
        <Empty description="Metadata will show up after a completed run." />
      ),
    },
    {
      key: 'raw',
      label: 'Raw',
      children: selectedSnapshot?.raw_response ? (
        <pre data-testid="raw-response" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(selectedSnapshot.raw_response, null, 2)}
        </pre>
      ) : (
        <Empty description="No raw response payload was returned for this run." />
      ),
    },
  ]

  return (
    <AnimatedLayout animationKey="chat-playground">
      <div style={pageStyle}>
        <div style={shellStyle}>
          <div style={topBarStyle} data-testid="playground-topbar">
            <Space size={12} wrap>
              <Tag color="blue" icon={<ExperimentOutlined />}>
                Playground
              </Tag>
              <Segmented
                data-testid="backend-switch"
                value={settings.backend}
                options={[
                  { label: 'Ollama', value: 'ollama' },
                  { label: 'HuggingFace', value: 'huggingface' },
                  { label: 'Cloud', value: 'cloud', icon: <CloudOutlined /> },
                ]}
                onChange={(value) => {
                  const backend = value as 'ollama' | 'huggingface' | 'cloud'
                  const nextModel =
                    backend === 'cloud'
                      ? cloudAIConfig?.model || 'MiniMax-M2.5'
                      : localModels[backend]?.[0]?.id || ''
                  updateSettings({ backend, modelId: nextModel })
                }}
              />
              <Select
                data-testid="model-select"
                style={{ minWidth: 220 }}
                value={settings.modelId || undefined}
                placeholder="Select model"
                options={currentModelOptions.map((option) => ({
                  label: option.name,
                  value: option.id,
                }))}
                onChange={(value) => updateSettings({ modelId: value })}
              />
              {settings.backend === 'cloud' ? (
                <Button icon={<SettingOutlined />} onClick={() => setConfigModalOpen(true)}>
                  Cloud Config
                </Button>
              ) : null}
              {availableBackends.map((backend) => (
                <Tag key={backend.id} color={backend.available ? 'green' : 'default'}>
                  {backend.name}: {backend.available ? 'ready' : 'unavailable'}
                </Tag>
              ))}
            </Space>

            <Space size={8} wrap>
              <Tag color={isStreaming ? 'processing' : 'default'}>
                {isStreaming ? 'Running' : 'Idle'}
              </Tag>
              <Button icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
                Sessions
              </Button>
              <Button icon={<DatabaseOutlined />} onClick={() => setMemoryManagerOpen(true)}>
                Memory
              </Button>
              <Button icon={<ClearOutlined />} onClick={handleNewExperiment}>
                New Experiment
              </Button>
            </Space>
          </div>

          <div style={bodyStyle}>
            <div style={{ ...scrollPanelStyle, padding: 18 }} data-testid="playground-left-panel">
              <div style={{ overflowY: 'auto', paddingRight: 4 }}>
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  <div>
                    <Title level={3} style={{ marginTop: 0, marginBottom: 4 }}>
                      Build
                    </Title>
                    <Text type="secondary">
                      Tune the prompt, choose context sources, and run a single experiment.
                    </Text>
                  </div>

                  <Card size="small" title="System Prompt">
                    <TextArea
                      data-testid="system-prompt-input"
                      value={settings.systemPrompt}
                      rows={5}
                      placeholder="Add instructions for the assistant..."
                      onChange={(event) => updateSettings({ systemPrompt: event.target.value })}
                    />
                  </Card>

                  <Card size="small" title="Prompt">
                    <TextArea
                      data-testid="prompt-input"
                      value={promptDraft}
                      rows={10}
                      placeholder="Describe the task, ask a question, or paste a prompt template..."
                      onChange={(event) => setPromptDraft(event.target.value)}
                    />
                  </Card>

                  <Card size="small" title="Attachments">
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <input
                        ref={fileInputRef}
                        data-testid="attachment-input"
                        type="file"
                        multiple
                        accept=".txt,.md,.json,.csv,.yaml,.yml,.png,.jpg,.jpeg,.webp"
                        style={{ display: 'none' }}
                        onChange={(event) => {
                          handleAttachFiles(event.target.files)
                          event.target.value = ''
                        }}
                      />
                      <Space wrap>
                        <Button onClick={() => fileInputRef.current?.click()}>Add Files</Button>
                        <Button icon={<DeleteOutlined />} onClick={clearAttachments} disabled={!attachments.length}>
                          Clear Files
                        </Button>
                      </Space>
                      {canUseImageAttachments ? null : (
                        <Alert
                          type="info"
                          showIcon
                          message="Text attachments are always supported. Images currently require cloud mode with GLM-4V."
                        />
                      )}
                      {attachments.length ? (
                        <List
                          data-testid="attachment-list"
                          size="small"
                          dataSource={attachments}
                          renderItem={(attachment) => (
                            <List.Item
                              actions={[
                                <Button
                                  key="remove"
                                  type="link"
                                  danger
                                  onClick={() => removeAttachment(attachment.id)}
                                >
                                  Remove
                                </Button>,
                              ]}
                            >
                              <Space direction="vertical" size={2}>
                                <Text strong>{attachment.name}</Text>
                                <Text type="secondary">
                                  {attachment.type} · {Math.max(1, Math.round(attachment.size / 1024))} KB
                                </Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No attachments added." />
                      )}
                    </Space>
                  </Card>

                  <Card size="small" title="Parameters" data-testid="parameter-panel">
                    <Space direction="vertical" size={16} style={{ width: '100%' }}>
                      <div>
                        <Text strong>Temperature</Text>
                        <Slider
                          min={0}
                          max={2}
                          step={0.1}
                          value={settings.temperature}
                          onChange={(value) => updateSettings({ temperature: value })}
                        />
                      </div>
                      <div>
                        <Text strong>Top P</Text>
                        <Slider
                          min={0.1}
                          max={1}
                          step={0.05}
                          value={settings.topP}
                          onChange={(value) => updateSettings({ topP: value })}
                        />
                      </div>
                      <div>
                        <Text strong>Max Tokens</Text>
                        <Slider
                          min={256}
                          max={8192}
                          step={256}
                          value={settings.maxTokens}
                          onChange={(value) => updateSettings({ maxTokens: value })}
                        />
                      </div>
                      <div>
                        <Text strong>Response Format</Text>
                        <Select
                          style={{ width: '100%', marginTop: 8 }}
                          value={settings.responseFormat}
                          options={[
                            { label: 'Text', value: 'text' },
                            { label: 'JSON', value: 'json' },
                          ]}
                          onChange={(value) =>
                            updateSettings({ responseFormat: value as 'text' | 'json' })
                          }
                        />
                      </div>
                    </Space>
                  </Card>

                  <Card size="small" title="Context">
                    <Space direction="vertical" size={16} style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong>Knowledge Base</Text>
                          <div>
                            <Text type="secondary">Inject retrieved knowledge into the run.</Text>
                          </div>
                        </div>
                        <Switch
                          checked={settings.useKnowledge}
                          onChange={(checked) =>
                            updateSettings({
                              useKnowledge: checked,
                              knowledgeCollection: settings.knowledgeCollection || collections[0]?.id,
                            })
                          }
                        />
                      </div>
                      <Select
                        data-testid="knowledge-select"
                        value={settings.knowledgeCollection}
                        placeholder="Select a collection"
                        options={collections.map((collection) => ({
                          label: `${collection.name} (${collection.count})`,
                          value: collection.id,
                        }))}
                        onChange={(value) => updateSettings({ knowledgeCollection: value })}
                      />
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong>Memory</Text>
                          <div>
                            <Text type="secondary">Recall relevant memory before generation.</Text>
                          </div>
                        </div>
                        <Switch
                          checked={settings.useMemory}
                          onChange={(checked) => updateSettings({ useMemory: checked })}
                        />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong>Auto Retrieve</Text>
                          <div>
                            <Text type="secondary">Automatically run retrieval when knowledge is enabled.</Text>
                          </div>
                        </div>
                        <Switch
                          checked={settings.autoRetrieve}
                          onChange={(checked) => updateSettings({ autoRetrieve: checked })}
                        />
                      </div>
                    </Space>
                  </Card>

                  <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                    <Button
                      size="large"
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      onClick={handleRun}
                      loading={isStreaming}
                      data-testid="run-button"
                    >
                      Run Experiment
                    </Button>
                    <Space wrap>
                      <Button onClick={stopStream} disabled={!isStreaming}>
                        Stop
                      </Button>
                      <Button icon={<ReloadOutlined />} onClick={handleNewExperiment}>
                        Reset
                      </Button>
                    </Space>
                  </Space>
                </Space>
              </div>
            </div>

            <div style={{ ...scrollPanelStyle, padding: 18 }} data-testid="playground-right-panel">
              <div style={{ overflowY: 'auto', paddingRight: 4, display: 'grid', gap: 16 }}>
                <Card size="small" style={panelStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space wrap>
                      <Tag icon={<RobotOutlined />} color="geekblue">
                        {settings.modelId || 'No model selected'}
                      </Tag>
                      <Tag>{settings.backend}</Tag>
                      {selectedSnapshot?.run_metrics?.duration_ms ? (
                        <Tag>{selectedSnapshot.run_metrics.duration_ms} ms</Tag>
                      ) : null}
                      {selectedSnapshot?.knowledge_sources?.length ? (
                        <Tag color="green">Knowledge hit</Tag>
                      ) : null}
                      {selectedSnapshot?.memory_context?.retrieved ? (
                        <Tag color="gold">Memory hit</Tag>
                      ) : null}
                    </Space>
                    <Paragraph style={{ marginBottom: 0 }} type="secondary">
                      Playground output, retrieval signals, and raw payloads all stay in one place.
                    </Paragraph>
                  </Space>
                </Card>

                <Card size="small" style={panelStyle}>
                  <Tabs
                    data-testid="response-tabs"
                    activeKey={responseView}
                    items={responseTabs}
                    onChange={(value) =>
                      setResponseView(value as 'response' | 'sources' | 'metadata' | 'raw')
                    }
                  />
                </Card>

                <Card
                  size="small"
                  title="Experiment History"
                  extra={
                    <Button
                      type="link"
                      icon={<CopyOutlined />}
                      disabled={!selectedSnapshot}
                      onClick={async () => {
                        if (!selectedSnapshot) return
                        await navigator.clipboard.writeText(selectedSnapshot.response)
                        message.success('Response copied.')
                      }}
                    >
                      Copy Response
                    </Button>
                  }
                >
                  {experimentSnapshots.length ? (
                    <List
                      data-testid="experiment-history"
                      dataSource={experimentSnapshots}
                      renderItem={(snapshot) => (
                        <List.Item
                          actions={[
                            <Button
                              key="load"
                              type="link"
                              onClick={() => handleLoadSnapshot(snapshot)}
                            >
                              Load
                            </Button>,
                            <Button
                              key="copy-prompt"
                              type="link"
                              onClick={async () => {
                                await navigator.clipboard.writeText(snapshot.experiment_config.prompt)
                                message.success('Prompt copied.')
                              }}
                            >
                              Copy Prompt
                            </Button>,
                          ]}
                        >
                          <div style={{ width: '100%' }}>
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              <Text strong>{snapshot.title}</Text>
                              <Text type="secondary">
                                {new Date(snapshot.createdAt).toLocaleString('zh-CN')}
                              </Text>
                              <Text ellipsis>{snapshot.response.slice(0, 120) || 'No response content.'}</Text>
                            </Space>
                          </div>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No experiments yet." />
                  )}
                </Card>
              </div>
            </div>
          </div>
        </div>

        <ChatHistoryDrawer
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          sessions={sessions.map((session) => ({
            id: session.id,
            title: session.title,
            created_at: session.createdAt,
            updated_at: session.updatedAt,
            message_count: session.messageCount,
          }))}
          onLoadSession={(id) => loadSession(id)}
          onDeleteSession={(id) => deleteSession(id)}
        />

        <MemoryManager open={memoryManagerOpen} onClose={() => setMemoryManagerOpen(false)} />

        <Modal
          open={configModalOpen}
          onCancel={() => setConfigModalOpen(false)}
          footer={null}
          width={640}
        >
          <APIKeyManager
            onConfigChange={(config: APIKeyConfig) => {
              setCloudAIConfig(config)
              updateSettings({
                backend: 'cloud',
                modelId: config.model || (config.provider === 'glm' ? 'glm-4' : 'MiniMax-M2.5'),
              })
            }}
            initialConfig={cloudAIConfig}
          />
        </Modal>
      </div>
    </AnimatedLayout>
  )
}

export default ChatPage
