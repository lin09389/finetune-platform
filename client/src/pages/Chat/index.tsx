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
  DownloadOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  ImportOutlined,
  SaveOutlined,
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
import type {
  PlaygroundAttachment,
  PlaygroundCandidate,
  PlaygroundPreset,
  PlaygroundSnapshot,
} from '../../types'

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

interface CompareField {
  key: string
  label: string
  value: string
  changed: boolean
}

interface DiffLine {
  type: 'added' | 'removed'
  value: string
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

function buildResponseDiff(baseText: string, nextText: string) {
  const baseLines = baseText.split('\n').map((line) => line.trim()).filter(Boolean)
  const nextLines = nextText.split('\n').map((line) => line.trim()).filter(Boolean)
  const removed = baseLines.filter((line) => !nextLines.includes(line))
  const added = nextLines.filter((line) => !baseLines.includes(line))

  const preview: DiffLine[] = [
    ...removed.slice(0, 3).map((value) => ({ type: 'removed' as const, value })),
    ...added.slice(0, 3).map((value) => ({ type: 'added' as const, value })),
  ]

  return {
    addedCount: added.length,
    removedCount: removed.length,
    preview,
    hasChanges: added.length > 0 || removed.length > 0,
  }
}

function buildCompareFields(snapshot: PlaygroundSnapshot, allSnapshots: PlaygroundSnapshot[]): CompareField[] {
  const fields = [
    { key: 'model', label: 'Model', value: snapshot.experiment_config.modelId || 'Unknown' },
    { key: 'backend', label: 'Backend', value: snapshot.experiment_config.backend },
    { key: 'temperature', label: 'Temperature', value: String(snapshot.experiment_config.temperature) },
    { key: 'topP', label: 'Top P', value: String(snapshot.experiment_config.topP) },
    { key: 'maxTokens', label: 'Max Tokens', value: String(snapshot.experiment_config.maxTokens) },
    {
      key: 'knowledge',
      label: 'Knowledge',
      value: snapshot.experiment_config.useKnowledge ? 'On' : 'Off',
    },
    {
      key: 'memory',
      label: 'Memory',
      value: snapshot.experiment_config.useMemory ? 'On' : 'Off',
    },
    {
      key: 'responseFormat',
      label: 'Format',
      value: snapshot.experiment_config.responseFormat,
    },
  ]

  return fields.map((field) => ({
    ...field,
    changed: allSnapshots.some((candidate) => {
      const candidateFields = {
        model: candidate.experiment_config.modelId || 'Unknown',
        backend: candidate.experiment_config.backend,
        temperature: String(candidate.experiment_config.temperature),
        topP: String(candidate.experiment_config.topP),
        maxTokens: String(candidate.experiment_config.maxTokens),
        knowledge: candidate.experiment_config.useKnowledge ? 'On' : 'Off',
        memory: candidate.experiment_config.useMemory ? 'On' : 'Off',
        responseFormat: candidate.experiment_config.responseFormat,
      }
      return candidateFields[field.key as keyof typeof candidateFields] !== field.value
    }),
  }))
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
  const presetImportRef = useRef<HTMLInputElement | null>(null)

  const {
    sessions,
    currentSessionId,
    messages,
    settings,
    promptDraft,
    attachments,
    activeCandidates,
    selectedCandidateId,
    selectedExperimentId,
    responseView,
    lastRunMetadata,
    experimentSnapshots,
    presets,
    selectedPresetId,
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
    setActiveCandidates,
    clearActiveCandidates,
    addExperimentSnapshot,
    setSelectedCandidateId,
    setSelectedExperimentId,
    setResponseView,
    setLastRunMetadata,
    savePreset,
    deletePreset,
    setSelectedPresetId,
  } = useChatStore()

  const [collections, setCollections] = useState<KnowledgeCollection[]>([])
  const [presetName, setPresetName] = useState('')
  const [compareSnapshotIds, setCompareSnapshotIds] = useState<string[]>([])
  const [compareOnlyDiff, setCompareOnlyDiff] = useState(false)
  const [lastImportSummary, setLastImportSummary] = useState<{
    imported: number
    overwritten: number
    skipped: number
  } | null>(null)
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
    runExperimentCandidates,
    stop: stopStream,
    isStreaming,
    state: streamState,
  } = useChatStream({
    onError: (error) => message.error(error),
  })

  const selectedSnapshot = useMemo(() => {
    if (selectedExperimentId) {
      if (lastRunMetadata?.id === selectedExperimentId) {
        return lastRunMetadata
      }
      return experimentSnapshots.find((snapshot) => snapshot.id === selectedExperimentId) || null
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
  const compareSnapshots = experimentSnapshots.filter((snapshot) =>
    compareSnapshotIds.includes(snapshot.id)
  )
  const selectedPreset = presets.find((preset) => preset.id === selectedPresetId) || null
  const displayedCandidates = activeCandidates.length
    ? activeCandidates
    : selectedSnapshot?.candidates || []
  const primaryCandidate =
    displayedCandidates.find((candidate) => candidate.id === selectedSnapshot?.selectedCandidateId) ||
    displayedCandidates[0] ||
    null
  const selectedCandidate =
    displayedCandidates.find((candidate) => candidate.id === selectedCandidateId) ||
    displayedCandidates.find((candidate) => candidate.id === selectedSnapshot?.selectedCandidateId) ||
    displayedCandidates[0] ||
    null
  const candidateSummary = useMemo(() => {
    const completed = displayedCandidates.filter((candidate) => candidate.status === 'completed').length
    const failed = displayedCandidates.filter((candidate) => candidate.status === 'error').length
    const stopped = displayedCandidates.filter((candidate) => candidate.status === 'stopped').length
    return {
      total: displayedCandidates.length,
      completed,
      failed,
      stopped,
    }
  }, [displayedCandidates])
  const selectedCandidateDiff = useMemo(() => {
    if (!selectedCandidate || !primaryCandidate || selectedCandidate.id === primaryCandidate.id) {
      return null
    }
    return buildResponseDiff(primaryCandidate.content, selectedCandidate.content)
  }, [primaryCandidate, selectedCandidate])

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
    clearActiveCandidates()
    setSelectedExperimentId(null)
    setLastRunMetadata(null)
  }, [
    clearActiveCandidates,
    clearAttachments,
    clearMessages,
    setLastRunMetadata,
    setPromptDraft,
    setSelectedExperimentId,
  ])

  const buildCurrentConfig = useCallback(() => {
    return {
      prompt: promptDraft,
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
      candidateCount: settings.candidateCount,
      attachments,
    }
  }, [attachments, promptDraft, settings])

  const applyConfig = useCallback(
    (config: PlaygroundPreset['config'] | PlaygroundSnapshot['experiment_config']) => {
      setPromptDraft(config.prompt)
      updateSettings({
        systemPrompt: config.systemPrompt,
        responseFormat: config.responseFormat,
        backend: config.backend,
        modelId: config.modelId,
        temperature: config.temperature,
        topP: config.topP,
        maxTokens: config.maxTokens,
        useKnowledge: config.useKnowledge,
        knowledgeCollection: config.knowledgeCollection,
        useMemory: config.useMemory,
        autoRetrieve: config.autoRetrieve,
        candidateCount: config.candidateCount ?? 1,
      })
      setAttachments(config.attachments || [])
    },
    [setAttachments, setPromptDraft, updateSettings]
  )

  const handleSavePreset = useCallback(() => {
    const name = presetName.trim() || promptDraft.trim().slice(0, 32) || 'Untitled preset'
    const timestamp = new Date().toISOString()
    const preset: PlaygroundPreset = {
      id: `preset_${Date.now()}`,
      name,
      createdAt: timestamp,
      updatedAt: timestamp,
      config: buildCurrentConfig(),
    }
    savePreset(preset)
    setSelectedPresetId(preset.id)
    setPresetName('')
    setLastImportSummary(null)
    message.success('Preset saved.')
  }, [buildCurrentConfig, presetName, promptDraft, savePreset, setSelectedPresetId])

  const handleUpdatePreset = useCallback(() => {
    if (!selectedPreset) {
      message.warning('Load a preset first, or save a new one.')
      return
    }

    const updatedPreset: PlaygroundPreset = {
      ...selectedPreset,
      name: presetName.trim() || selectedPreset.name,
      updatedAt: new Date().toISOString(),
      config: buildCurrentConfig(),
    }

    savePreset(updatedPreset)
    setPresetName(updatedPreset.name)
    setLastImportSummary(null)
    message.success('Preset updated.')
  }, [buildCurrentConfig, presetName, savePreset, selectedPreset])

  const handleExportPresets = useCallback(() => {
    const payload = {
      exportedAt: new Date().toISOString(),
      presets,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `playground-presets-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
    message.success('Presets exported.')
  }, [presets])

  const handleImportPresets = useCallback(
    async (file: File | null) => {
      if (!file) return

      try {
        const text = await file.text()
        const parsed = JSON.parse(text) as {
          presets?: PlaygroundPreset[]
        }

        if (!Array.isArray(parsed.presets)) {
          throw new Error('Invalid preset file.')
        }

        const incomingPresets = parsed.presets.filter(
          (preset): preset is PlaygroundPreset => Boolean(preset?.id && preset?.name && preset?.config)
        )
        if (incomingPresets.length === 0) {
          throw new Error('No valid presets found in file.')
        }

        const existingByName = new Map(presets.map((preset) => [preset.name, preset]))
        const conflictingPresets = incomingPresets.filter((preset) => existingByName.has(preset.name))

        let shouldOverwrite = conflictingPresets.length === 0
        if (conflictingPresets.length > 0) {
          shouldOverwrite = await new Promise<boolean>((resolve) => {
            Modal.confirm({
              title: 'Overwrite existing presets?',
              content: `The import file contains ${conflictingPresets.length} preset(s) with names that already exist: ${conflictingPresets
                .map((preset) => preset.name)
                .join(', ')}.`,
              okText: 'Overwrite',
              cancelText: 'Skip duplicates',
              onOk: () => resolve(true),
              onCancel: () => resolve(false),
            })
          })
        }

        let importedCount = 0
        let overwrittenCount = 0
        let skippedCount = 0
        for (const preset of incomingPresets) {
          const existingPreset = existingByName.get(preset.name)
          if (existingPreset && !shouldOverwrite) {
            skippedCount += 1
            continue
          }

          if (existingPreset && shouldOverwrite) {
            overwrittenCount += 1
          }

          savePreset({
            ...preset,
            id: existingPreset && shouldOverwrite ? existingPreset.id : preset.id,
            updatedAt: preset.updatedAt || new Date().toISOString(),
            createdAt: preset.createdAt || new Date().toISOString(),
          })
          importedCount += 1
        }

        if (importedCount === 0) {
          throw new Error('No presets were imported.')
        }

        setLastImportSummary({
          imported: importedCount,
          overwritten: overwrittenCount,
          skipped: skippedCount,
        })

        const overwrittenLabel =
          overwrittenCount > 0 ? ` Overwrote ${overwrittenCount} existing preset(s).` : ''
        const skippedLabel = skippedCount > 0 ? ` Skipped ${skippedCount} duplicate preset(s).` : ''
        message.success(
          `Imported ${importedCount} preset${importedCount > 1 ? 's' : ''}.${overwrittenLabel}${skippedLabel}`
        )
      } catch (error) {
        message.error(error instanceof Error ? error.message : 'Failed to import presets.')
      }
    },
    [presets, savePreset]
  )

  const handleToggleCompare = useCallback((snapshotId: string) => {
    setCompareSnapshotIds((current) => {
      if (current.includes(snapshotId)) {
        return current.filter((id) => id !== snapshotId)
      }
      if (current.length >= 2) {
        return [current[1]!, snapshotId]
      }
      return [...current, snapshotId]
    })
  }, [])

  const getVisibleCompareFields = useCallback(
    (snapshot: PlaygroundSnapshot) => {
      const fields = buildCompareFields(snapshot, compareSnapshots)
      if (!compareOnlyDiff) {
        return fields
      }
      return fields.filter((field) => field.changed)
    },
    [compareOnlyDiff, compareSnapshots]
  )

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

    const candidates = await runExperimentCandidates(
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
          backend: settings.backend,
        },
      },
      settings.candidateCount,
      settings.backend === 'cloud' && cloudAIConfig
        ? {
            provider: cloudAIConfig.provider,
            apiKey: cloudAIConfig.api_key,
            keyId: cloudAIConfig.key_id,
            model: settings.modelId,
            groupId: cloudAIConfig.group_id,
            baseUrl: cloudAIConfig.base_url,
          }
        : undefined
    )

    if (!candidates.length) {
      return
    }

    const selectedCandidate =
      candidates.find((candidate) => candidate.status === 'completed') || candidates[0]

    if (!selectedCandidate) {
      return
    }

    setActiveCandidates(candidates)
    setSelectedCandidateId(selectedCandidate.id)

    const snapshot: PlaygroundSnapshot = {
      id: `experiment_${Date.now()}`,
      createdAt: new Date().toISOString(),
      title: prompt.slice(0, 48) || 'Untitled experiment',
      response: selectedCandidate.content,
      selectedCandidateId: selectedCandidate.id,
      candidates,
      raw_response: selectedCandidate.raw_response,
      knowledge_sources: selectedCandidate.knowledge_sources,
      retrieval_info: selectedCandidate.retrieval_info,
      memory_context: selectedCandidate.memory_context,
      unified_context: selectedCandidate.unified_context,
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
        candidateCount: settings.candidateCount,
        attachments,
      },
      run_metrics: selectedCandidate.run_metrics,
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
    runExperimentCandidates,
    setActiveCandidates,
    setSelectedCandidateId,
    setResponseView,
    settings,
  ])

  const handleLoadSnapshot = useCallback(
    (snapshot: PlaygroundSnapshot) => {
      applyConfig(snapshot.experiment_config)
      setActiveCandidates(snapshot.candidates || [])
      setSelectedCandidateId(snapshot.selectedCandidateId || snapshot.candidates?.[0]?.id || null)
      setSelectedExperimentId(snapshot.id)
      setLastRunMetadata(snapshot)
      setResponseView('response')
    },
    [
      applyConfig,
      setActiveCandidates,
      setLastRunMetadata,
      setResponseView,
      setSelectedCandidateId,
      setSelectedExperimentId,
    ]
  )

  const latestAssistantMessage = [...messages].reverse().find((msg) => msg.role === 'assistant')
  const responseContent =
    (isStreaming ? streamState.content : selectedCandidate?.content || selectedSnapshot?.response) ||
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
          {selectedCandidate?.knowledge_sources?.length ? (
            <Card size="small" title="Knowledge Sources">
              <List
                dataSource={selectedCandidate.knowledge_sources}
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
          {selectedCandidate?.retrieval_info ? (
            <Card size="small" title="Retrieval">
              <Paragraph style={{ marginBottom: 8 }}>Query: {selectedCandidate.retrieval_info.query}</Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>Method: {selectedCandidate.retrieval_info.method}</Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                Results: {selectedCandidate.retrieval_info.total_results} in{' '}
                {selectedCandidate.retrieval_info.retrieval_time}s
              </Paragraph>
            </Card>
          ) : null}
          {selectedCandidate?.memory_context ? (
            <Card size="small" title="Memory Context">
              <Paragraph style={{ marginBottom: 8 }}>
                Retrieved: {selectedCandidate.memory_context.retrieved ? 'Yes' : 'No'}
              </Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>
                Sources: {selectedCandidate.memory_context.sources_count}
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                {selectedCandidate.memory_context.context_preview || 'No preview available.'}
              </Paragraph>
            </Card>
          ) : null}
          {!selectedCandidate?.knowledge_sources?.length &&
          !selectedCandidate?.retrieval_info &&
          !selectedCandidate?.memory_context ? (
            <Empty description="No retrieval or memory sources were returned for this run." />
          ) : null}
        </Space>
      ),
    },
    {
      key: 'metadata',
      label: 'Metadata',
      children: selectedCandidate?.run_metrics ? (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Text>Candidate: #{selectedCandidate.index + 1}</Text>
          <Text>Model: {selectedCandidate.run_metrics.model || selectedSnapshot?.experiment_config.modelId}</Text>
          <Text>Backend: {selectedCandidate.run_metrics.backend || selectedSnapshot?.experiment_config.backend}</Text>
          <Text>Duration: {selectedCandidate.run_metrics.duration_ms ?? 0} ms</Text>
          <Text>Prompt tokens: {selectedCandidate.run_metrics.prompt_tokens ?? 0}</Text>
          <Text>Completion tokens: {selectedCandidate.run_metrics.completion_tokens ?? 0}</Text>
          <Text>Total tokens: {selectedCandidate.run_metrics.total_tokens ?? 0}</Text>
          <Text>Knowledge used: {selectedCandidate.run_metrics.used_knowledge ? 'Yes' : 'No'}</Text>
          <Text>Memory used: {selectedCandidate.run_metrics.used_memory ? 'Yes' : 'No'}</Text>
        </Space>
      ) : (
        <Empty description="Metadata will show up after a completed run." />
      ),
    },
    {
      key: 'raw',
      label: 'Raw',
      children: selectedCandidate?.raw_response ? (
        <pre data-testid="raw-response" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(selectedCandidate.raw_response, null, 2)}
        </pre>
      ) : (
        <Empty description="No raw response payload was returned for this run." />
      ),
    },
  ]

  const handleSetPrimaryCandidate = useCallback(
    (candidate: PlaygroundCandidate) => {
      if (!selectedSnapshot) {
        setSelectedCandidateId(candidate.id)
        return
      }

      const updatedSnapshot: PlaygroundSnapshot = {
        ...selectedSnapshot,
        selectedCandidateId: candidate.id,
        candidates: displayedCandidates.map((item) => (item.id === candidate.id ? candidate : item)),
        response: candidate.content,
        raw_response: candidate.raw_response,
        knowledge_sources: candidate.knowledge_sources,
        retrieval_info: candidate.retrieval_info,
        memory_context: candidate.memory_context,
        unified_context: candidate.unified_context,
        run_metrics: candidate.run_metrics,
      }

      setActiveCandidates(updatedSnapshot.candidates)
      setSelectedCandidateId(candidate.id)
      setLastRunMetadata(updatedSnapshot)
    },
    [
      displayedCandidates,
      selectedSnapshot,
      setActiveCandidates,
      setLastRunMetadata,
      setSelectedCandidateId,
    ]
  )

  const syncCandidatesToSnapshot = useCallback(
    (nextCandidates: PlaygroundCandidate[], nextSelectedCandidateId?: string | null) => {
      setActiveCandidates(nextCandidates)
      const fallbackCandidateId = nextCandidates[0]?.id || null
      const resolvedSelectedCandidateId =
        nextSelectedCandidateId && nextCandidates.some((candidate) => candidate.id === nextSelectedCandidateId)
          ? nextSelectedCandidateId
          : fallbackCandidateId
      setSelectedCandidateId(resolvedSelectedCandidateId)

      if (!selectedSnapshot) {
        return
      }

      const nextPrimary =
        nextCandidates.find(
          (candidate) => candidate.id === (selectedSnapshot.selectedCandidateId || resolvedSelectedCandidateId)
        ) ||
        nextCandidates.find((candidate) => candidate.id === resolvedSelectedCandidateId) ||
        nextCandidates[0]

      setLastRunMetadata({
        ...selectedSnapshot,
        selectedCandidateId: nextPrimary?.id || resolvedSelectedCandidateId || '',
        candidates: nextCandidates,
        response: nextPrimary?.content || '',
        raw_response: nextPrimary?.raw_response,
        knowledge_sources: nextPrimary?.knowledge_sources,
        retrieval_info: nextPrimary?.retrieval_info,
        memory_context: nextPrimary?.memory_context,
        unified_context: nextPrimary?.unified_context,
        run_metrics: nextPrimary?.run_metrics,
      })
    },
    [selectedSnapshot, setActiveCandidates, setLastRunMetadata, setSelectedCandidateId]
  )

  const handleRerunCandidate = useCallback(
    async (candidate: PlaygroundCandidate) => {
      const prompt = promptDraft.trim()
      if (!prompt) {
        message.warning('Enter a prompt before rerunning a candidate.')
        return
      }

      const rerunCandidates = await runExperimentCandidates(
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
            backend: settings.backend,
          },
        },
        1,
        settings.backend === 'cloud' && cloudAIConfig
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: settings.modelId,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined
      )

      const rerun = rerunCandidates[0]
      if (!rerun) {
        return
      }

      const updatedCandidate: PlaygroundCandidate = {
        ...rerun,
        id: candidate.id,
        index: candidate.index,
      }
      const updatedCandidates = displayedCandidates.map((item) =>
        item.id === candidate.id ? updatedCandidate : item
      )
      syncCandidatesToSnapshot(updatedCandidates, updatedCandidate.id)

      message.success(`Candidate ${candidate.index + 1} rerun complete.`)
    },
    [
      attachments,
      cloudAIConfig,
      displayedCandidates,
      promptDraft,
      runExperimentCandidates,
      settings,
      syncCandidatesToSnapshot,
    ]
  )

  const handleKeepOnlyCandidate = useCallback(
    (candidate: PlaygroundCandidate) => {
      syncCandidatesToSnapshot([{ ...candidate, index: 0 }], candidate.id)
      message.success(`Kept candidate ${candidate.index + 1} only.`)
    },
    [syncCandidatesToSnapshot]
  )

  const handleDiscardCandidate = useCallback(
    (candidate: PlaygroundCandidate) => {
      const nextCandidates = displayedCandidates
        .filter((item) => item.id !== candidate.id)
        .map((item, index) => ({ ...item, index }))

      if (!nextCandidates.length) {
        message.warning('At least one candidate needs to remain in the experiment.')
        return
      }

      const nextSelectedCandidateId =
        selectedCandidate?.id === candidate.id ? nextCandidates[0]!.id : selectedCandidate?.id
      syncCandidatesToSnapshot(nextCandidates, nextSelectedCandidateId)
      message.success(`Discarded candidate ${candidate.index + 1}.`)
    },
    [displayedCandidates, selectedCandidate?.id, syncCandidatesToSnapshot]
  )

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

                  <Card
                    size="small"
                    title="Presets"
                    extra={<Tag>{presets.length} saved</Tag>}
                    data-testid="preset-panel"
                  >
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <input
                        ref={presetImportRef}
                        data-testid="preset-import-input"
                        type="file"
                        accept=".json,application/json"
                        style={{ display: 'none' }}
                        onChange={(event) => {
                          handleImportPresets(event.target.files?.[0] || null)
                          event.target.value = ''
                        }}
                      />
                      <Space.Compact style={{ width: '100%' }}>
                        <Input
                          data-testid="preset-name-input"
                          value={presetName}
                          placeholder="Preset name"
                          onChange={(event) => setPresetName(event.target.value)}
                        />
                        <Button
                          icon={<SaveOutlined />}
                          onClick={handleSavePreset}
                          data-testid="save-preset-button"
                        >
                          Save New
                        </Button>
                      </Space.Compact>
                      <Space wrap>
                        <Button
                          onClick={handleUpdatePreset}
                          disabled={!selectedPreset}
                          data-testid="update-preset-button"
                        >
                          Update Current
                        </Button>
                        <Button
                          icon={<DownloadOutlined />}
                          onClick={handleExportPresets}
                          disabled={!presets.length}
                          data-testid="export-presets-button"
                        >
                          Export JSON
                        </Button>
                        <Button
                          icon={<ImportOutlined />}
                          onClick={() => presetImportRef.current?.click()}
                          data-testid="import-presets-button"
                        >
                          Import JSON
                        </Button>
                        {selectedPreset ? (
                          <Text type="secondary">
                            Editing: {selectedPreset.name}
                          </Text>
                        ) : (
                          <Text type="secondary">Load a preset to update it in place.</Text>
                        )}
                      </Space>
                      {lastImportSummary ? (
                        <Alert
                          type="success"
                          showIcon
                          message={`Import summary: ${lastImportSummary.imported} imported, ${lastImportSummary.overwritten} overwritten, ${lastImportSummary.skipped} skipped.`}
                        />
                      ) : null}
                      {presets.length ? (
                        <List
                          data-testid="preset-list"
                          size="small"
                          dataSource={presets}
                          renderItem={(preset) => (
                            <List.Item
                              actions={[
                                <Button
                                  key="load"
                                  type="link"
                                  onClick={() => {
                                    applyConfig(preset.config)
                                    setSelectedPresetId(preset.id)
                                    setPresetName(preset.name)
                                    message.success('Preset loaded.')
                                  }}
                                >
                                  Load
                                </Button>,
                                <Button
                                  key="delete"
                                  type="link"
                                  danger
                                  onClick={() => deletePreset(preset.id)}
                                >
                                  Delete
                                </Button>,
                              ]}
                            >
                              <Space direction="vertical" size={2}>
                                <Space size={8}>
                                  <Text strong>{preset.name}</Text>
                                  {selectedPresetId === preset.id ? <Tag color="blue">Active</Tag> : null}
                                </Space>
                                <Text type="secondary">
                                  {preset.config.backend} · {preset.config.modelId || 'No model'}
                                </Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No presets saved yet." />
                      )}
                    </Space>
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
                        <Text strong>Candidates</Text>
                        <Slider
                          min={1}
                          max={4}
                          step={1}
                          marks={{
                            1: '1',
                            2: '2',
                            3: '3',
                            4: '4',
                          }}
                          value={settings.candidateCount}
                          onChange={(value) => updateSettings({ candidateCount: value })}
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
                      {selectedCandidate?.run_metrics?.duration_ms ? (
                        <Tag>{selectedCandidate.run_metrics.duration_ms} ms</Tag>
                      ) : null}
                      <Tag color="processing">{candidateSummary.total} candidates</Tag>
                      {candidateSummary.completed ? (
                        <Tag color="green">{candidateSummary.completed} completed</Tag>
                      ) : null}
                      {candidateSummary.failed ? <Tag color="red">{candidateSummary.failed} failed</Tag> : null}
                      {candidateSummary.stopped ? (
                        <Tag color="default">{candidateSummary.stopped} stopped</Tag>
                      ) : null}
                      {selectedCandidate?.knowledge_sources?.length ? (
                        <Tag color="green">Knowledge hit</Tag>
                      ) : null}
                      {selectedCandidate?.memory_context?.retrieved ? (
                        <Tag color="gold">Memory hit</Tag>
                      ) : null}
                    </Space>
                    <Paragraph style={{ marginBottom: 0 }} type="secondary">
                      Candidate cards show the parallel runs. Click one to inspect its sources, metadata, and raw payload.
                    </Paragraph>
                  </Space>
                </Card>

                <Card
                  size="small"
                  title="Candidates"
                  data-testid="candidate-grid"
                >
                  {displayedCandidates.length ? (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                        gap: 12,
                      }}
                    >
                      {displayedCandidates.map((candidate) => {
                        const isPrimary = selectedSnapshot?.selectedCandidateId === candidate.id
                        const isActive = selectedCandidate?.id === candidate.id
                        return (
                          <Card
                            key={candidate.id}
                            size="small"
                            hoverable
                            data-testid={`candidate-card-${candidate.index + 1}`}
                            onClick={() => setSelectedCandidateId(candidate.id)}
                            style={{
                              borderRadius: 18,
                              border: isActive
                                ? '1px solid rgba(22, 119, 255, 0.45)'
                                : '1px solid rgba(15, 23, 42, 0.08)',
                              boxShadow: isActive
                                ? '0 12px 28px rgba(22, 119, 255, 0.12)'
                                : '0 8px 20px rgba(15, 23, 42, 0.06)',
                            }}
                            title={
                              <Space wrap size={6}>
                                <Text strong>{`Candidate ${candidate.index + 1}`}</Text>
                                {isPrimary ? <Tag color="blue">Primary</Tag> : null}
                                <Tag>{candidate.status}</Tag>
                              </Space>
                            }
                            extra={<Tag>{candidate.run_metrics?.backend || settings.backend}</Tag>}
                            actions={[
                              <Button
                                key="keep"
                                type="link"
                                size="small"
                                data-testid={`candidate-keep-${candidate.index + 1}`}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handleKeepOnlyCandidate(candidate)
                                }}
                              >
                                Keep Only
                              </Button>,
                              <Button
                                key="discard"
                                type="link"
                                size="small"
                                danger
                                data-testid={`candidate-discard-${candidate.index + 1}`}
                                disabled={displayedCandidates.length <= 1}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handleDiscardCandidate(candidate)
                                }}
                              >
                                Discard
                              </Button>,
                              <Button
                                key="primary"
                                type="link"
                                size="small"
                                data-testid={`candidate-primary-${candidate.index + 1}`}
                                disabled={isPrimary}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handleSetPrimaryCandidate(candidate)
                                }}
                              >
                                Set as Primary
                              </Button>,
                              <Button
                                key="rerun"
                                type="link"
                                size="small"
                                data-testid={`candidate-rerun-${candidate.index + 1}`}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  void handleRerunCandidate(candidate)
                                }}
                              >
                                Rerun
                              </Button>,
                              <Button
                                key="copy"
                                type="link"
                                size="small"
                                onClick={async (event) => {
                                  event.stopPropagation()
                                  await navigator.clipboard.writeText(candidate.content)
                                  message.success('Candidate copied.')
                                }}
                              >
                                Copy
                              </Button>,
                            ]}
                          >
                            <Space direction="vertical" size={8} style={{ width: '100%' }}>
                              <Text type="secondary">
                                {candidate.run_metrics?.model || settings.modelId || 'Unknown model'}
                              </Text>
                              <Paragraph
                                ellipsis={{ rows: 4 }}
                                style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
                              >
                                {candidate.content || candidate.error || 'No content yet.'}
                              </Paragraph>
                              <Space wrap size={6}>
                                {candidate.run_metrics?.duration_ms ? (
                                  <Tag>{candidate.run_metrics.duration_ms} ms</Tag>
                                ) : null}
                                {candidate.knowledge_sources?.length ? <Tag color="green">KB</Tag> : null}
                                {candidate.memory_context?.retrieved ? <Tag color="gold">Memory</Tag> : null}
                              </Space>
                            </Space>
                          </Card>
                        )
                      })}
                    </div>
                  ) : (
                    <Empty description="Run an experiment to generate candidates." />
                  )}
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

                {selectedCandidate && primaryCandidate && selectedCandidateDiff?.hasChanges ? (
                  <Card
                    size="small"
                    title={`Diff vs Primary Candidate ${primaryCandidate.index + 1}`}
                    data-testid="candidate-diff-panel"
                  >
                    <Space direction="vertical" size={10} style={{ width: '100%' }}>
                      <Space wrap size={8}>
                        <Tag color="green">{selectedCandidateDiff.addedCount} added</Tag>
                        <Tag color="red">{selectedCandidateDiff.removedCount} removed</Tag>
                      </Space>
                      {selectedCandidateDiff.preview.map((line, index) => (
                        <div
                          key={`${line.type}-${index}-${line.value}`}
                          data-testid={line.type === 'added' ? 'candidate-diff-added' : 'candidate-diff-removed'}
                          style={{
                            padding: '8px 10px',
                            borderRadius: 12,
                            background:
                              line.type === 'added'
                                ? 'rgba(82, 196, 26, 0.12)'
                                : 'rgba(255, 77, 79, 0.12)',
                            border:
                              line.type === 'added'
                                ? '1px solid rgba(82, 196, 26, 0.32)'
                                : '1px solid rgba(255, 77, 79, 0.28)',
                          }}
                        >
                          <Text strong>{line.type === 'added' ? '+ ' : '- '}</Text>
                          <Text>{line.value}</Text>
                        </div>
                      ))}
                    </Space>
                  </Card>
                ) : null}

                {compareSnapshots.length === 2 ? (
                  <Card
                    size="small"
                    title="Compare Runs"
                    extra={
                      <Space size={12}>
                        <Space size={8}>
                          <Text type="secondary">Only differences</Text>
                          <Switch
                            data-testid="compare-only-diff"
                            checked={compareOnlyDiff}
                            onChange={setCompareOnlyDiff}
                          />
                        </Space>
                        <Button type="link" onClick={() => setCompareSnapshotIds([])}>
                          Clear Compare
                        </Button>
                      </Space>
                    }
                    data-testid="compare-panel"
                  >
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                        gap: 12,
                      }}
                    >
                      {compareSnapshots.map((snapshot) => (
                        <Card
                          key={snapshot.id}
                          size="small"
                          title={snapshot.title}
                          extra={<Tag>{snapshot.experiment_config.backend}</Tag>}
                        >
                          {(() => {
                            const baseline = compareSnapshots[0]
                            const outputDiff = baseline
                              ? buildResponseDiff(baseline.response || '', snapshot.response || '')
                              : null

                            return (
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Text type="secondary">
                                  {new Date(snapshot.createdAt).toLocaleString('zh-CN')}
                                </Text>
                                <Space wrap size={8}>
                                  <Tag>{snapshot.candidates?.length || 1} candidates</Tag>
                                  <Tag color="blue">
                                    Primary #{(snapshot.candidates?.findIndex(
                                      (candidate) => candidate.id === snapshot.selectedCandidateId
                                    ) ?? 0) + 1}
                                  </Tag>
                                  {outputDiff?.hasChanges ? (
                                    <Tag color="purple" data-testid="compare-output-diff">
                                      {outputDiff.addedCount + outputDiff.removedCount} output changes
                                    </Tag>
                                  ) : null}
                                </Space>
                                <div
                                  style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                                    gap: 8,
                                  }}
                                >
                                  {getVisibleCompareFields(snapshot).map((field) => (
                                    <div
                                      key={`${snapshot.id}-${field.key}`}
                                      data-testid={field.changed ? 'compare-diff-field' : 'compare-same-field'}
                                      style={{
                                        padding: '8px 10px',
                                        borderRadius: 12,
                                        background: field.changed
                                          ? 'rgba(250, 173, 20, 0.16)'
                                          : 'rgba(15, 23, 42, 0.04)',
                                        border: field.changed
                                          ? '1px solid rgba(250, 173, 20, 0.45)'
                                          : '1px solid rgba(15, 23, 42, 0.08)',
                                      }}
                                    >
                                      <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                                        {field.label}
                                      </Text>
                                      <Text strong>{field.value}</Text>
                                    </div>
                                  ))}
                                </div>
                                {compareOnlyDiff && !getVisibleCompareFields(snapshot).length ? (
                                  <Empty
                                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                                    description="No parameter differences for this run."
                                  />
                                ) : null}
                                <Paragraph
                                  style={{
                                    marginBottom: 0,
                                    maxHeight: 220,
                                    overflow: 'auto',
                                    whiteSpace: 'pre-wrap',
                                  }}
                                >
                                  {snapshot.response || 'No response content.'}
                                </Paragraph>
                              </Space>
                            )
                          })()}
                        </Card>
                      ))}
                    </div>
                  </Card>
                ) : null}

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
                        const primaryCandidate =
                          displayedCandidates.find(
                            (candidate) =>
                              candidate.id ===
                              (selectedCandidate?.id || selectedSnapshot.selectedCandidateId)
                          ) || selectedCandidate
                        await navigator.clipboard.writeText(
                          primaryCandidate?.content || selectedSnapshot.response
                        )
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
                              key="compare"
                              type="link"
                              onClick={() => handleToggleCompare(snapshot.id)}
                            >
                              {compareSnapshotIds.includes(snapshot.id) ? 'Compared' : 'Compare'}
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
                              <Space wrap size={8}>
                                <Text strong>{snapshot.title}</Text>
                                <Tag>{snapshot.candidates?.length || 1} candidates</Tag>
                              </Space>
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
