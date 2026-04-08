import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Collapse,
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
  BranchesOutlined,
  ClearOutlined,
  CloudOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  StarFilled,
  StarOutlined,
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
import ChatBranchManager from '../../components/ChatBranchManager'
import ChatHistoryDrawer from '../../components/ChatHistoryDrawer'
import MemoryManager from '../../components/MemoryManager'
import APIKeyManager from '../APIKeyManager'
import { useChatStream } from '../../hooks/chat/useChatStream'
import {
  type ConversationBranchSummary,
  type ConversationTreeNode,
  createConversationBranch,
  fetchConversationTreeState,
  saveConversationMessage,
  switchConversationBranch,
  switchConversationToMainTimeline,
} from '../../services/conversationTreeApi'
import { updateChatSessionMetadata } from '../../services/chatSessionApi'
import { useChatStore } from '../../store/chatStore'
import { API_BASE_URL, getBackends, getInferenceModels, getOllamaStatus } from '../../services/api'
import type {
  AgentTimelineEvent,
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

interface AgentTaskHistoryItem {
  id: string
  title: string
  status: string
  summary: string
  toolName?: string
  createdAt: string
}

interface AgentOutcomeItem {
  id: string
  title: string
  summary: string
  createdAt: string
}

interface AutomationTraceItem {
  id: string
  type: 'auto_continue' | 'auto_recover'
  title: string
  reason: string
  createdAt: string
  status: string
  attempt: number
}

interface AgentStepGroup {
  key: string
  label: string
  status: string
  events: AgentTimelineEvent[]
}

interface PatchDraft {
  content: string
  fileHints: string[]
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

function extractPatchDraft(text: string): PatchDraft | null {
  const fencedMatch = text.match(/```(?:diff|patch)?\s*\n([\s\S]*?)```/i)
  const candidate = fencedMatch?.[1]?.trim() || text.trim()

  if (
    !candidate ||
    (!candidate.includes('diff --git') &&
      !(candidate.includes('--- ') && candidate.includes('+++ ')) &&
      !candidate.includes('@@'))
  ) {
    return null
  }

  const fileHints = Array.from(
    new Set(
      [...candidate.matchAll(/(?:\+\+\+|---)\s+(?:a\/|b\/)?([^\n\r\t ]+)/g)].map((match) => match[1]!).filter(Boolean)
    )
  )

  return {
    content: candidate,
    fileHints,
  }
}

function buildAutomationMarkdownReport(options: {
  scope: 'all' | 'auto_continue' | 'auto_recover'
  limit: number
  items: AutomationTraceItem[]
  recommendedNextStep: string
}) {
  const scopeLabel =
    options.scope === 'all'
      ? 'All automation events'
      : options.scope === 'auto_continue'
        ? 'Auto-continue events'
        : 'Auto-recover events'
  const selected = options.items.slice(0, Math.max(1, options.limit))
  const failed = selected.filter((item) => item.status === 'failed')
  const lines: string[] = [
    '# Automation Failure Chain Report',
    '',
    `- Generated at: ${new Date().toLocaleString('zh-CN')}`,
    `- Scope: ${scopeLabel}`,
    `- Included events: ${selected.length}`,
    `- Failed events: ${failed.length}`,
    '',
    '## Recent Events',
  ]

  if (!selected.length) {
    lines.push('', 'No automation events in the selected scope.')
  } else {
    selected.forEach((item, index) => {
      lines.push(
        '',
        `### ${index + 1}. ${item.title}`,
        `- Type: ${item.type === 'auto_recover' ? 'Auto Recover' : 'Auto Continue'}`,
        `- Status: ${item.status}`,
        `- Attempt: ${item.attempt}`,
        `- Time: ${new Date(item.createdAt).toLocaleString('zh-CN')}`,
        `- Reason: ${item.reason}`
      )
    })
  }

  lines.push(
    '',
    '## Recommended Next Step',
    '',
    options.recommendedNextStep.trim()
      ? options.recommendedNextStep.trim()
      : 'Review the latest failed automation step and resume from that event.'
  )

  return lines.join('\n')
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
    agentMode,
    agentTaskStatus,
    agentTimeline,
    pendingAgentConfirmation,
    agentWorkspaceRoot,
    autoApproveSafeTools,
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
    setAgentMode,
    setAgentTaskStatus,
    clearAgentTimeline,
    setPendingAgentConfirmation,
    setAgentWorkspaceRoot,
    setAutoApproveSafeTools,
    updateSettings,
    setPromptDraft,
    setAttachments,
    removeAttachment,
    clearAttachments,
    setActiveCandidates,
    clearActiveCandidates,
    addExperimentSnapshot,
    updateExperimentSnapshot,
    setSelectedCandidateId,
    setSelectedExperimentId,
    setResponseView,
    setLastRunMetadata,
    savePreset,
    deletePreset,
    setSelectedPresetId,
    updateSessionMetadata,
  } = useChatStore()

  const [collections, setCollections] = useState<KnowledgeCollection[]>([])
  const [presetName, setPresetName] = useState('')
  const [compareSnapshotIds, setCompareSnapshotIds] = useState<string[]>([])
  const [compareOnlyDiff, setCompareOnlyDiff] = useState(false)
  const [historySearch, setHistorySearch] = useState('')
  const [historyBackendFilter, setHistoryBackendFilter] = useState<string>('all')
  const [historyModelFilter, setHistoryModelFilter] = useState<string>('all')
  const [historyFavoritesOnly, setHistoryFavoritesOnly] = useState(false)
  const [historySort, setHistorySort] = useState<'newest' | 'recent' | 'favorites'>('newest')
  const [branchManagerOpen, setBranchManagerOpen] = useState(false)
  const [branchNodes, setBranchNodes] = useState<Record<string, ConversationTreeNode>>({})
  const [branchRootId, setBranchRootId] = useState<string | null>(null)
  const [branchSummaries, setBranchSummaries] = useState<ConversationBranchSummary[]>([])
  const [currentBranchId, setCurrentBranchId] = useState<string | null>(null)
  const [replyAnchorId, setReplyAnchorId] = useState<string | null>(null)
  const [selectedConversationNodeId, setSelectedConversationNodeId] = useState<string | null>(null)
  const [showActivePathOnly, setShowActivePathOnly] = useState(false)
  const [lastImportSummary, setLastImportSummary] = useState<{
    imported: number
    overwritten: number
    skipped: number
  } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [selectedTaskOutcomeId, setSelectedTaskOutcomeId] = useState<string | null>(null)
  const [automationTraceFilter, setAutomationTraceFilter] = useState<
    'all' | 'auto_continue' | 'auto_recover'
  >('all')
  const [automationReportLimit, setAutomationReportLimit] = useState(8)
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
    runAgentTask,
    resumeAgentTask,
    resumeAgentFromEvent,
    confirmAgentAction,
    applyPatchDraft,
    cancelAgentAction,
    stop: stopStream,
    isStreaming,
    state: streamState,
  } = useChatStream({
    onError: (error) => message.error(error),
  })

  const refreshBranchState = useCallback(
    async (sessionId: string) => {
      try {
        const state = await fetchConversationTreeState(sessionId)
        setBranchNodes(state.tree.nodes || {})
        setBranchRootId(state.tree.root_id || null)
        setCurrentBranchId(state.tree.current_branch_id || null)
        setBranchSummaries(state.branches || [])
      } catch (error) {
        console.error('Failed to refresh branch state:', error)
        setBranchNodes({})
        setBranchRootId(null)
        setCurrentBranchId(null)
        setBranchSummaries([])
      }
    },
    []
  )

  const selectedSnapshot = useMemo(() => {
    if (selectedExperimentId) {
      if (lastRunMetadata?.id === selectedExperimentId) {
        return lastRunMetadata
      }
      return experimentSnapshots.find((snapshot) => snapshot.id === selectedExperimentId) || null
    }
    return lastRunMetadata
  }, [experimentSnapshots, lastRunMetadata, selectedExperimentId])

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) || null,
    [currentSessionId, sessions]
  )

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
  const latestUserMessage = useMemo(() => {
    return [...messages].reverse().find((message) => message.role === 'user') || null
  }, [messages])
  const recentFailedTestsCommand = useMemo(() => {
    const event = [...agentTimeline]
      .reverse()
      .find(
        (item) =>
          item.tool_name === 'tests_run' &&
          item.status === 'failed' &&
          typeof item.payload?.command === 'string' &&
          item.payload.command.trim()
      )
    return typeof event?.payload?.command === 'string' ? event.payload.command : null
  }, [agentTimeline])
  const agentStatusColor = useMemo(() => {
    switch (agentTaskStatus) {
      case 'planning':
        return 'processing'
      case 'running':
        return 'blue'
      case 'waiting_confirmation':
        return 'gold'
      case 'completed':
        return 'green'
      case 'failed':
        return 'red'
      case 'stopped':
        return 'default'
      default:
        return 'default'
    }
  }, [agentTaskStatus])
  const historyBackendOptions = useMemo(() => {
    return Array.from(
      new Set(experimentSnapshots.map((snapshot) => snapshot.experiment_config.backend).filter(Boolean))
    )
  }, [experimentSnapshots])
  const historyModelOptions = useMemo(() => {
    return Array.from(
      new Set(experimentSnapshots.map((snapshot) => snapshot.experiment_config.modelId).filter(Boolean))
    )
  }, [experimentSnapshots])
  const filteredExperimentSnapshots = useMemo(() => {
    const query = historySearch.trim().toLowerCase()

    return experimentSnapshots
      .filter((snapshot) => {
        const matchesQuery =
          !query ||
          [
            snapshot.title,
            snapshot.response,
            snapshot.experiment_config.prompt,
            snapshot.experiment_config.modelId,
            snapshot.experiment_config.backend,
          ]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(query))

        const matchesBackend =
          historyBackendFilter === 'all' ||
          snapshot.experiment_config.backend === historyBackendFilter

        const matchesModel =
          historyModelFilter === 'all' ||
          snapshot.experiment_config.modelId === historyModelFilter

        const matchesFavorite = !historyFavoritesOnly || Boolean(snapshot.isFavorite)

        return matchesQuery && matchesBackend && matchesModel && matchesFavorite
      })
      .sort((left, right) => {
        if (historySort === 'favorites') {
          const favoriteDelta = Number(Boolean(right.isFavorite)) - Number(Boolean(left.isFavorite))
          if (favoriteDelta !== 0) {
            return favoriteDelta
          }
        }

        if (historySort === 'recent') {
          return (
            new Date(right.lastViewedAt || right.createdAt).getTime() -
            new Date(left.lastViewedAt || left.createdAt).getTime()
          )
        }

        return new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
      })
  }, [
    experimentSnapshots,
    historyBackendFilter,
    historyFavoritesOnly,
    historyModelFilter,
    historySearch,
    historySort,
  ])

  const currentBranch = useMemo(
    () => branchSummaries.find((branch) => branch.id === currentBranchId) || null,
    [branchSummaries, currentBranchId]
  )

  const sortedBranchMessages = useMemo(() => {
    return Object.values(branchNodes).sort(
      (left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime()
    )
  }, [branchNodes])

  const activeBranchTipId = useMemo(() => {
    if (currentBranchId) {
      const branch = branchSummaries.find((item) => item.id === currentBranchId)
      if (branch?.last_message_id && branchNodes[branch.last_message_id]) {
        return branch.last_message_id
      }
      if (branch?.root_message_id && branchNodes[branch.root_message_id]) {
        return branch.root_message_id
      }
    }

    const trunkMessages = sortedBranchMessages.filter((node) => !node.branch_name)
    if (trunkMessages.length) {
      return trunkMessages[trunkMessages.length - 1]!.id
    }

    return sortedBranchMessages[sortedBranchMessages.length - 1]?.id || null
  }, [branchNodes, branchSummaries, currentBranchId, sortedBranchMessages])

  const currentPathTipId = useMemo(() => {
    if (replyAnchorId && branchNodes[replyAnchorId]) {
      return replyAnchorId
    }
    return activeBranchTipId
  }, [activeBranchTipId, branchNodes, replyAnchorId])

  const currentPathIds = useMemo(() => {
    if (!currentPathTipId) {
      return new Set<string>()
    }

    const path = new Set<string>()
    let cursor: string | null = currentPathTipId
    while (cursor && branchNodes[cursor] && !path.has(cursor)) {
      const currentNode: ConversationTreeNode | undefined = branchNodes[cursor]
      if (!currentNode) {
        break
      }
      path.add(cursor)
      cursor = currentNode.parent_id
    }
    return path
  }, [branchNodes, currentPathTipId])

  const branchPathMessages = useMemo(() => {
    const items: ConversationTreeNode[] = []
    if (!currentPathTipId) {
      return items
    }

    let cursor: string | null = currentPathTipId
    while (cursor && branchNodes[cursor]) {
      items.unshift(branchNodes[cursor]!)
      cursor = branchNodes[cursor]!.parent_id
    }
    return items
  }, [branchNodes, currentPathTipId])

  const visibleConversationNodes = useMemo(() => {
    if (!showActivePathOnly) {
      return sortedBranchMessages
    }
    return sortedBranchMessages.filter((node) => currentPathIds.has(node.id))
  }, [currentPathIds, showActivePathOnly, sortedBranchMessages])

  const viewedConversationNode = useMemo(() => {
    if (selectedConversationNodeId && branchNodes[selectedConversationNodeId]) {
      return branchNodes[selectedConversationNodeId]
    }
    if (currentPathTipId && branchNodes[currentPathTipId]) {
      return branchNodes[currentPathTipId]
    }
    return null
  }, [branchNodes, currentPathTipId, selectedConversationNodeId])

  const viewedParentNode = useMemo(() => {
    if (!viewedConversationNode?.parent_id) {
      return null
    }
    return branchNodes[viewedConversationNode.parent_id] || null
  }, [branchNodes, viewedConversationNode])
  const agentTaskHistory = useMemo<AgentTaskHistoryItem[]>(() => {
    return [...agentTimeline]
      .filter(
        (event) =>
          event.type === 'task_status' ||
          event.type === 'tool_result' ||
          event.type === 'confirmation_request' ||
          event.type === 'assistant_message'
      )
      .reverse()
      .slice(0, 8)
      .map((event) => ({
        id: event.id,
        title: event.title,
        status: event.status || (event.type === 'confirmation_request' ? 'pending' : 'recorded'),
        summary:
          (typeof event.payload?.loop_summary === 'string' && event.payload.loop_summary) ||
          (typeof event.payload?.recommended_next_step === 'string' && event.payload.recommended_next_step) ||
          event.description ||
          event.tool_name ||
          event.type,
        toolName: event.tool_name,
        createdAt: event.createdAt,
      }))
  }, [agentTimeline])
  const agentOutcomeItems = useMemo<AgentOutcomeItem[]>(() => {
    return [...agentTimeline]
      .filter(
        (event) =>
          event.type === 'task_status' &&
          ((typeof event.payload?.completion_summary === 'string' &&
            event.payload.completion_summary.trim()) ||
            (typeof event.payload?.handoff_note === 'string' && event.payload.handoff_note.trim()))
      )
      .reverse()
      .slice(0, 4)
      .map((event) => ({
        id: event.id,
        title: event.title,
        summary:
          (typeof event.payload?.completion_summary === 'string' &&
            event.payload.completion_summary) ||
          (typeof event.payload?.handoff_note === 'string' && event.payload.handoff_note) ||
          event.description ||
          event.title,
        createdAt: event.createdAt,
      }))
  }, [agentTimeline])
  const automationTraceItems = useMemo<AutomationTraceItem[]>(() => {
    return [...agentTimeline]
      .filter(
        (event) =>
          event.type === 'task_status' &&
          (event.payload?.automation_type === 'auto_continue' ||
            event.payload?.automation_type === 'auto_recover')
      )
      .reverse()
      .slice(0, 20)
      .map((event) => ({
        id: event.id,
        type: event.payload?.automation_type === 'auto_recover' ? 'auto_recover' : 'auto_continue',
        title: event.title,
        reason:
          (typeof event.payload?.automation_reason === 'string' && event.payload.automation_reason) ||
          event.description ||
          event.title,
        createdAt: event.createdAt,
        status: event.status || 'completed',
        attempt:
          typeof event.payload?.automation_attempt === 'number'
            ? event.payload.automation_attempt
            : 1,
      }))
  }, [agentTimeline])
  const filteredAutomationTraceItems = useMemo(() => {
    if (automationTraceFilter === 'all') {
      return automationTraceItems
    }
    return automationTraceItems.filter((item) => item.type === automationTraceFilter)
  }, [automationTraceFilter, automationTraceItems])
  const automationFailureSummary = useMemo(() => {
    const failedItems = filteredAutomationTraceItems.filter((item) => item.status === 'failed')
    const scopeText =
      automationTraceFilter === 'all'
        ? 'all automation events'
        : automationTraceFilter === 'auto_continue'
          ? 'auto-continue events'
          : 'auto-recover events'
    const lines = [
      `Automation trace summary (${scopeText})`,
      `Total events: ${filteredAutomationTraceItems.length}`,
      `Failed events: ${failedItems.length}`,
    ]

    if (failedItems.length > 0) {
      lines.push('Failure chain:')
      failedItems.slice(0, 8).forEach((item, index) => {
        lines.push(
          `${index + 1}. ${item.title} | attempt ${item.attempt} | ${item.reason} | ${new Date(
            item.createdAt
          ).toLocaleString('zh-CN')}`
        )
      })
    }

    return lines.join('\n')
  }, [automationTraceFilter, filteredAutomationTraceItems])
  const automationMarkdownReport = useMemo(() => {
    const nextStep = agentTaskHistory[0]?.summary || ''
    return buildAutomationMarkdownReport({
      scope: automationTraceFilter,
      limit: automationReportLimit,
      items: filteredAutomationTraceItems,
      recommendedNextStep: nextStep,
    })
  }, [agentTaskHistory, automationReportLimit, automationTraceFilter, filteredAutomationTraceItems])
  const agentStepGroups = useMemo<AgentStepGroup[]>(() => {
    const groups = new Map<string, AgentStepGroup>()

    agentTimeline.forEach((event) => {
      const stepMatch = event.title.match(/Step\s+(\d+)/i)
      const key = stepMatch ? `step-${stepMatch[1]}` : 'overview'
      const label = stepMatch ? `Step ${stepMatch[1]}` : 'Overview'
      const existing = groups.get(key)
      if (existing) {
        existing.events.push(event)
        if (event.status) {
          existing.status = event.status
        }
        return
      }

      groups.set(key, {
        key,
        label,
        status: event.status || 'recorded',
        events: [event],
      })
    })

    return Array.from(groups.values())
  }, [agentTimeline])

  const handleRetryTestCommand = useCallback(
    (command: string) => {
      const trimmedCommand = command.trim()
      if (!trimmedCommand) {
        return
      }

      const retryCloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Retry this test command: ${trimmedCommand}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            detected_intents: [
              {
                detected: true,
                intent_type: 'tests_run',
                action: 'tests_run',
                params: { command: trimmedCommand },
                description: 'Retry the previous failing test command.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        retryCloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleOpenFailingFile = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Open the failing test file: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Open the first failing test file.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleAnalyzeFailingFile = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Inspect the failing test file and explain the likely failure points: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and summarize the likely cause of the failing test. ` +
              'Call out suspicious assertions, fixtures, or setup issues in concise bullets.',
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Read the failing test file before summarizing it.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleCreateFixPlan = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Create a fix plan for the failing test file: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and write a concise fix plan for the failing test. ` +
              'Return 3-5 actionable steps, calling out what to inspect first and what to change next.',
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Read the failing test file before creating a fix plan.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleStartGuidedFix = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Start a guided fix for the failing test file: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and produce a guided fix response for the failing test. ` +
              'Explain the most likely root cause first, then list the first concrete code change to try next.',
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Read the failing test file before starting a guided fix.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleDraftPatchProposal = useCallback(
      (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Draft a patch proposal for the failing test file: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and draft a patch proposal for the failing test. ` +
              'Suggest concrete code edits in a diff-like format without applying changes.',
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Read the failing test file before drafting a patch proposal.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
      },
      [cloudAIConfig, runAgentTask, settings]
    )

  const handleSummarizeVerifiedFix = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Summarize why this verified fix worked: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and summarize why the verified patch fixed the failing test. ` +
              'Explain the key code change, why it addressed the failure, and what to watch for next time.',
            detected_intents: [
              {
                action: 'file_read',
                params: { path: trimmedPath },
                detected: true,
                confidence: 1.0,
                description: 'Read the verified file before summarizing the fix.',
                intent_type: 'file_read',
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleReviewVerifiedFix = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Review this verified fix for remaining risks: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and perform a concise final review of the verified fix. ` +
              'Call out any remaining risks, edge cases, or follow-up tests worth running, and say if the change looks ready.',
            detected_intents: [
              {
                action: 'file_read',
                params: { path: trimmedPath },
                detected: true,
                confidence: 1.0,
                description: 'Read the verified file before reviewing the fix.',
                intent_type: 'file_read',
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleCreateCompletionSummary = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Create a completion summary for this verified fix: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and write a concise completion summary for the verified fix. ` +
              'Include what changed, why it fixed the issue, what was verified, and any recommended follow-up in 3-5 bullets.',
            detected_intents: [
              {
                action: 'file_read',
                params: { path: trimmedPath },
                detected: true,
                confidence: 1.0,
                description: 'Read the verified file before writing the completion summary.',
                intent_type: 'file_read',
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleCreateHandoffNote = useCallback(
    (filePath: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      void runAgentTask(
        {
          prompt: `Create a handoff note for this verified fix: ${trimmedPath}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and write a short handoff note for the verified fix. ` +
              'Cover what changed, what was verified, remaining watchouts, and the recommended next owner action.',
            detected_intents: [
              {
                action: 'file_read',
                params: { path: trimmedPath },
                detected: true,
                confidence: 1.0,
                description: 'Read the verified file before preparing the handoff note.',
                intent_type: 'file_read',
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const handleAnalyzePatchFailure = useCallback(
    (filePath: string, failureReason?: string) => {
      const trimmedPath = filePath.trim()
      if (!trimmedPath) {
        return
      }

      const cloudConfig =
        settings.backend === 'cloud' && cloudAIConfig?.model
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: cloudAIConfig.model,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined

      const reasonSuffix = failureReason?.trim() ? ` Patch error: ${failureReason.trim()}` : ''

      void runAgentTask(
        {
          prompt: `Analyze why the patch failed for: ${trimmedPath}.${reasonSuffix}`,
          systemPrompt: settings.systemPrompt,
          responseFormat: settings.responseFormat,
          attachments: [],
          parameterOverrides: {
            temperature: settings.temperature,
            topP: settings.topP,
            maxTokens: settings.maxTokens,
            backend: settings.backend,
            modelId: settings.modelId,
          },
          agentContext: {
            followup_prompt:
              `Read ${trimmedPath} and analyze why the patch failed to apply. ` +
              `Use this failure reason if helpful: ${failureReason || 'patch does not apply'}. ` +
              'Explain whether the patch is stale, the hunk context is wrong, or the target file likely changed.',
            detected_intents: [
              {
                detected: true,
                intent_type: 'file_read',
                action: 'file_read',
                params: { path: trimmedPath },
                description: 'Read the patch target before analyzing the patch failure.',
                confidence: 1,
                need_confirm: false,
              },
            ],
          },
        },
        cloudConfig
      )
    },
    [cloudAIConfig, runAgentTask, settings]
  )

  const renderAgentEvent = useCallback((event: AgentTimelineEvent) => {
    const borderColor =
      event.status === 'failed'
        ? 'rgba(255,77,79,0.28)'
        : event.status === 'completed'
          ? 'rgba(82,196,26,0.28)'
          : event.status === 'cancelled'
            ? 'rgba(140,140,140,0.24)'
            : 'rgba(22,119,255,0.22)'

    const background =
      event.status === 'failed'
        ? 'rgba(255,77,79,0.08)'
        : event.status === 'completed'
          ? 'rgba(82,196,26,0.08)'
          : event.status === 'cancelled'
            ? 'rgba(140,140,140,0.08)'
            : 'rgba(22,119,255,0.06)'

    const payload = event.payload || {}
    const actionName =
      typeof payload.action === 'string'
        ? payload.action
        : typeof payload.pending_action === 'string'
          ? payload.pending_action
          : undefined
    const commandText =
      typeof payload.command === 'string'
        ? payload.command
        : typeof payload.cmd === 'string'
          ? payload.cmd
          : typeof payload.executed_command === 'string'
            ? payload.executed_command
          : undefined
    const stdoutText =
      typeof payload.stdout === 'string'
        ? payload.stdout
        : typeof payload.output === 'string'
          ? payload.output
          : undefined
    const stderrText =
      typeof payload.stderr === 'string'
        ? payload.stderr
        : typeof payload.error_output === 'string'
          ? payload.error_output
          : undefined
    const commandSummary =
      typeof payload.summary === 'string'
        ? payload.summary
        : undefined
    const testSummary =
      'test_summary' in payload && payload.test_summary && typeof payload.test_summary === 'object'
        ? (payload.test_summary as {
            passed?: number
            failed?: number
            errors?: number
            skipped?: number
            summary_line?: string
            framework?: string
            exit_reason?: string
            failure_files?: string[]
            failure_cases?: Array<{ name?: string; message?: string }>
          })
        : null
    const testSuggestion =
      event.tool_name === 'tests_run' && testSummary
        ? (testSummary.failed || 0) > 0 || event.status === 'failed'
          ? 'Verification still failing. Recommended next step: inspect the failed file, analyze the failure, then redraft or refine the patch.'
          : 'Verification passed. Recommended next step: keep this patch, review the touched file once, and move on.'
        : null
    const firstFailureFile = testSummary?.failure_files?.[0]
    const filePath =
      typeof payload.path === 'string'
        ? payload.path
        : typeof payload.file_path === 'string'
          ? payload.file_path
          : typeof payload.target_path === 'string'
            ? payload.target_path
            : undefined
    const diffSummary =
      typeof payload.diff === 'string'
        ? payload.diff
        : typeof payload.patch === 'string'
          ? payload.patch
          : typeof payload.content === 'string' && payload.content.length < 1000
            ? payload.content
            : undefined
    const patchPayload =
      event.tool_name === 'file_patch' && diffSummary ? extractPatchDraft(diffSummary) : null
    const patchSuggestion =
      event.tool_name === 'file_patch'
        ? event.status === 'completed'
          ? 'Recommended next step: rerun the failing tests first, then inspect the patched file if anything still looks off.'
          : 'Recommended next step: inspect the target file, analyze why the patch failed, then redraft a patch against the latest file contents.'
        : null
    const riskLevel =
      typeof payload.riskLevel === 'string'
        ? payload.riskLevel
        : typeof payload.risk_level === 'string'
          ? payload.risk_level
          : undefined
    const hasCommandShape =
      event.type === 'command_output' ||
      event.tool_name === 'command_run' ||
      event.tool_name === 'tests_run' ||
      Boolean(commandText)
    const hasFileShape =
      event.type === 'file_change' ||
      event.tool_name === 'file_write' ||
      event.tool_name === 'file_patch' ||
      event.tool_name === 'file_read' ||
      Boolean(filePath)
    const isConfirmation = event.type === 'confirmation_request'
    const verificationOutcome =
      event.type === 'task_status' &&
      'verification_outcome' in payload &&
      typeof payload.verification_outcome === 'string'
        ? payload.verification_outcome
        : null
    const verificationFiles =
      verificationOutcome && Array.isArray(payload.failure_files)
        ? payload.failure_files.filter((file): file is string => typeof file === 'string')
        : []
    const verificationPatchedFiles =
      verificationOutcome && Array.isArray(payload.patched_files)
        ? payload.patched_files.filter((file): file is string => typeof file === 'string')
        : []
    const verificationRerunCommand =
      verificationOutcome && typeof payload.rerun_command === 'string' ? payload.rerun_command : undefined
    const firstVerificationFailureFile = verificationFiles[0]
    const firstVerificationPatchedFile = verificationPatchedFiles[0]
    const loopSummary =
      event.type === 'task_status' && typeof payload.loop_summary === 'string' ? payload.loop_summary : null
    const recommendedNextStep =
      event.type === 'task_status' && typeof payload.recommended_next_step === 'string'
        ? payload.recommended_next_step
        : null

    return (
      <div
        key={event.id}
        style={{
          borderRadius: 16,
          border: `1px solid ${borderColor}`,
          background,
          padding: 12,
        }}
      >
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space wrap size={8}>
            <Text strong>{event.title}</Text>
            <Tag>{event.type}</Tag>
            {event.tool_name ? <Tag color="geekblue">{event.tool_name}</Tag> : null}
            {event.status ? <Tag color={event.status === 'failed' ? 'red' : event.status === 'completed' ? 'green' : event.status === 'cancelled' ? 'default' : 'processing'}>{event.status}</Tag> : null}
          </Space>
          {event.description ? <Text>{event.description}</Text> : null}

          {loopSummary ? (
            <Alert
              type={event.status === 'failed' ? 'warning' : 'info'}
              showIcon
              data-testid={`agent-loop-summary-${event.id}`}
              message="Task summary"
              description={loopSummary}
            />
          ) : null}

          {recommendedNextStep ? (
            <Alert
              type={event.status === 'failed' ? 'warning' : 'success'}
              showIcon
              data-testid={`agent-next-step-${event.id}`}
              message="Recommended next step"
              description={recommendedNextStep}
            />
          ) : null}

          {verificationOutcome ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Alert
                type={verificationOutcome === 'passed' ? 'success' : 'warning'}
                showIcon
                data-testid={`agent-verification-outcome-${event.id}`}
                message={
                  verificationOutcome === 'passed'
                    ? 'Patch verification passed'
                    : 'Patch verification still failing'
                }
                description={
                  verificationOutcome === 'passed'
                    ? event.description
                    : verificationFiles.length
                      ? `${event.description || ''} Failing files: ${verificationFiles.join(', ')}`
                      : event.description
                }
              />
              {verificationOutcome === 'passed' && verificationPatchedFiles.length ? (
                <div>
                  <Text strong>Patched files</Text>
                  <div style={{ marginTop: 4 }}>
                    <Space wrap size={6}>
                      {verificationPatchedFiles.map((file) => (
                        <Tag key={file} color="green">
                          {file}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                </div>
              ) : null}
              <Space wrap>
                {verificationOutcome === 'failed' && verificationRerunCommand ? (
                  <Button
                    size="small"
                    type="primary"
                    data-testid={`agent-verification-retry-tests-${event.id}`}
                    onClick={() => handleRetryTestCommand(verificationRerunCommand)}
                  >
                    Retry tests
                  </Button>
                ) : null}
                {verificationOutcome === 'failed' && firstVerificationFailureFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-open-failing-file-${event.id}`}
                    onClick={() => handleOpenFailingFile(firstVerificationFailureFile)}
                  >
                    Open failing file
                  </Button>
                ) : null}
                {verificationOutcome === 'failed' && firstVerificationFailureFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-analyze-failing-file-${event.id}`}
                    onClick={() => handleAnalyzeFailingFile(firstVerificationFailureFile)}
                  >
                    Analyze failing file
                  </Button>
                ) : null}
                {verificationOutcome === 'failed' && firstVerificationFailureFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-create-fix-plan-${event.id}`}
                    onClick={() => handleCreateFixPlan(firstVerificationFailureFile)}
                  >
                    Create fix plan
                  </Button>
                ) : null}
                {verificationOutcome === 'failed' && firstVerificationFailureFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-redraft-patch-${event.id}`}
                    onClick={() => handleDraftPatchProposal(firstVerificationFailureFile)}
                  >
                    Redraft patch
                  </Button>
                ) : null}
                {verificationOutcome === 'failed' && firstVerificationFailureFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-start-guided-fix-${event.id}`}
                    onClick={() => handleStartGuidedFix(firstVerificationFailureFile)}
                  >
                    Start guided fix
                  </Button>
                ) : null}
                {verificationOutcome === 'passed' && firstVerificationPatchedFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-open-patched-file-${event.id}`}
                    onClick={() => handleOpenFailingFile(firstVerificationPatchedFile)}
                  >
                    Open patched file
                  </Button>
                ) : null}
                {verificationOutcome === 'passed' && firstVerificationPatchedFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-summarize-fix-${event.id}`}
                    onClick={() => handleSummarizeVerifiedFix(firstVerificationPatchedFile)}
                  >
                    Summarize fix
                  </Button>
                ) : null}
                {verificationOutcome === 'passed' && firstVerificationPatchedFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-review-fix-${event.id}`}
                    onClick={() => handleReviewVerifiedFix(firstVerificationPatchedFile)}
                  >
                    Review final fix
                  </Button>
                ) : null}
                {verificationOutcome === 'passed' && firstVerificationPatchedFile ? (
                  <Button
                    size="small"
                    type="primary"
                    data-testid={`agent-verification-completion-summary-${event.id}`}
                    onClick={() => handleCreateCompletionSummary(firstVerificationPatchedFile)}
                  >
                    Completion summary
                  </Button>
                ) : null}
                {verificationOutcome === 'passed' && firstVerificationPatchedFile ? (
                  <Button
                    size="small"
                    data-testid={`agent-verification-handoff-note-${event.id}`}
                    onClick={() => handleCreateHandoffNote(firstVerificationPatchedFile)}
                  >
                    Handoff note
                  </Button>
                ) : null}
              </Space>
            </Space>
          ) : null}

          {isConfirmation ? (
            <div
              data-testid="agent-event-confirmation"
              style={{
                borderRadius: 12,
                padding: '10px 12px',
                background: 'rgba(250, 173, 20, 0.08)',
                border: '1px solid rgba(250, 173, 20, 0.24)',
              }}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {actionName ? <Text strong>{`Action: ${actionName}`}</Text> : null}
                {riskLevel ? <Text type="secondary">{`Risk: ${riskLevel}`}</Text> : null}
                {'params' in payload ? (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>
                    {JSON.stringify((payload as { params?: unknown }).params, null, 2)}
                  </pre>
                ) : null}
              </Space>
            </div>
          ) : null}

          {hasCommandShape ? (
            <div
              data-testid="agent-event-command"
              style={{
                borderRadius: 12,
                padding: '10px 12px',
                background: 'rgba(22, 119, 255, 0.08)',
                border: '1px solid rgba(22, 119, 255, 0.18)',
              }}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {commandText ? <Text code>{commandText}</Text> : null}
                {'message' in payload && typeof payload.message === 'string' ? (
                  <Text>{payload.message}</Text>
                ) : null}
                {commandSummary ? <Text type="secondary">{commandSummary}</Text> : null}
                {testSummary ? (
                  <Space wrap size={6}>
                    <Tag color="green">{`Passed ${testSummary.passed || 0}`}</Tag>
                    <Tag color="red">{`Failed ${testSummary.failed || 0}`}</Tag>
                    <Tag color="orange">{`Errors ${testSummary.errors || 0}`}</Tag>
                    <Tag>{`Skipped ${testSummary.skipped || 0}`}</Tag>
                    {testSummary.framework ? <Tag color="blue">{testSummary.framework}</Tag> : null}
                    {testSummary.exit_reason ? <Tag>{testSummary.exit_reason}</Tag> : null}
                  </Space>
                ) : null}
                {testSummary?.summary_line ? (
                  <Text type="secondary">{testSummary.summary_line}</Text>
                ) : null}
                {testSuggestion ? (
                  <Alert
                    type={event.status === 'failed' ? 'warning' : 'success'}
                    showIcon
                    data-testid={`agent-test-suggestion-${event.id}`}
                    message={testSuggestion}
                  />
                ) : null}
                {testSummary?.failure_files?.length ? (
                  <div>
                    <Text strong>Failed files</Text>
                    <div style={{ marginTop: 4 }}>
                      <Space wrap size={6}>
                        {testSummary.failure_files.map((file) => (
                          <Tag key={file}>{file}</Tag>
                        ))}
                      </Space>
                    </div>
                  </div>
                ) : null}
                {testSummary?.failure_cases?.length ? (
                  <div>
                    <Text strong>Failed cases</Text>
                    <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 4 }}>
                      {testSummary.failure_cases.slice(0, 3).map((failure, index) => (
                        <div
                          key={`${failure.name || 'case'}-${index}`}
                          style={{
                            borderRadius: 8,
                            padding: '6px 8px',
                            background: 'rgba(255,255,255,0.55)',
                            border: '1px solid rgba(15, 23, 42, 0.08)',
                          }}
                        >
                          {failure.name ? <Text code>{failure.name}</Text> : null}
                          {failure.message ? (
                            <div>
                              <Text type="secondary">{failure.message}</Text>
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </Space>
                  </div>
                ) : null}
                {event.tool_name === 'tests_run' && event.status === 'failed' && commandText ? (
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      data-testid={`agent-retry-tests-${event.id}`}
                      onClick={() => handleRetryTestCommand(commandText)}
                    >
                      Retry tests
                    </Button>
                    {firstFailureFile ? (
                      <Button
                        size="small"
                        data-testid={`agent-open-failing-file-${event.id}`}
                        onClick={() => handleOpenFailingFile(firstFailureFile)}
                      >
                        Open failing file
                      </Button>
                    ) : null}
                    {firstFailureFile ? (
                      <Button
                        size="small"
                        data-testid={`agent-analyze-failing-file-${event.id}`}
                        onClick={() => handleAnalyzeFailingFile(firstFailureFile)}
                      >
                        Analyze failing file
                      </Button>
                    ) : null}
                    {firstFailureFile ? (
                      <Button
                        size="small"
                        data-testid={`agent-create-fix-plan-${event.id}`}
                        onClick={() => handleCreateFixPlan(firstFailureFile)}
                      >
                        Create fix plan
                      </Button>
                    ) : null}
                    {firstFailureFile ? (
                      <Button
                        size="small"
                        data-testid={`agent-start-guided-fix-${event.id}`}
                        onClick={() => handleStartGuidedFix(firstFailureFile)}
                      >
                        Start guided fix
                      </Button>
                    ) : null}
                    {firstFailureFile ? (
                      <Button
                        size="small"
                        data-testid={`agent-draft-patch-proposal-${event.id}`}
                        onClick={() => handleDraftPatchProposal(firstFailureFile)}
                      >
                        Draft patch proposal
                      </Button>
                    ) : null}
                  </Space>
                ) : null}
                {stdoutText ? (
                  <div>
                    <Text strong>stdout</Text>
                    <pre style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                      {stdoutText}
                    </pre>
                  </div>
                ) : null}
                {stderrText ? (
                  <div>
                    <Text strong type="danger">
                      stderr
                    </Text>
                    <pre style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                      {stderrText}
                    </pre>
                  </div>
                ) : null}
                {'error' in payload && typeof payload.error === 'string' && payload.error ? (
                  <Text type="danger">{payload.error}</Text>
                ) : null}
              </Space>
            </div>
          ) : null}

          {hasFileShape ? (
            <div
              data-testid="agent-event-file"
              style={{
                borderRadius: 12,
                padding: '10px 12px',
                background: 'rgba(82, 196, 26, 0.08)',
                border: '1px solid rgba(82, 196, 26, 0.18)',
              }}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {filePath ? <Text code>{filePath}</Text> : null}
                {'message' in payload && typeof payload.message === 'string' ? (
                  <Text>{payload.message}</Text>
                ) : null}
                {'summary' in payload && typeof payload.summary === 'string' ? (
                  <Text type="secondary">{payload.summary}</Text>
                ) : null}
                {patchSuggestion ? (
                  <Alert
                    type={event.status === 'completed' ? 'success' : 'warning'}
                    showIcon
                    data-testid={`agent-patch-suggestion-${event.id}`}
                    message={patchSuggestion}
                  />
                ) : null}
                {diffSummary ? (
                  <div>
                    <Text strong>Change summary</Text>
                    <pre style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                      {diffSummary}
                    </pre>
                  </div>
                ) : null}
                {event.tool_name === 'file_patch' &&
                event.status === 'completed' &&
                'rerun_command' in payload &&
                typeof payload.rerun_command === 'string' &&
                payload.rerun_command.trim() ? (
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      data-testid={`agent-rerun-tests-after-patch-${event.id}`}
                      onClick={() => handleRetryTestCommand(payload.rerun_command as string)}
                    >
                      Rerun failing tests
                    </Button>
                  </Space>
                ) : null}
                {event.tool_name === 'file_patch' &&
                event.status === 'completed' &&
                ((Array.isArray(payload.applied_files) && typeof payload.applied_files[0] === 'string') ||
                  typeof filePath === 'string') ? (
                  <Space>
                    <Button
                      size="small"
                      data-testid={`agent-open-patched-file-${event.id}`}
                      onClick={() =>
                        handleOpenFailingFile(
                          (Array.isArray(payload.applied_files) && typeof payload.applied_files[0] === 'string'
                            ? payload.applied_files[0]
                            : filePath) as string
                        )
                      }
                    >
                      Open patched file
                    </Button>
                  </Space>
                ) : null}
                {event.tool_name === 'file_patch' && event.status === 'failed' ? (
                  <Space>
                    {patchPayload ? (
                      <Button
                        size="small"
                        data-testid={`agent-copy-failed-patch-${event.id}`}
                        onClick={async () => {
                          await navigator.clipboard.writeText(patchPayload.content)
                          message.success('Failed patch copied.')
                        }}
                      >
                        Copy failed patch
                      </Button>
                    ) : null}
                    {((Array.isArray(payload.paths) && typeof payload.paths[0] === 'string') ||
                      patchPayload?.fileHints?.[0]) ? (
                      <Button
                        size="small"
                        data-testid={`agent-open-patch-target-${event.id}`}
                        onClick={() =>
                          handleOpenFailingFile(
                            (Array.isArray(payload.paths) && typeof payload.paths[0] === 'string'
                              ? payload.paths[0]
                              : patchPayload?.fileHints?.[0] || '') as string
                          )
                        }
                      >
                        Open patch target
                      </Button>
                    ) : null}
                    {((Array.isArray(payload.paths) && typeof payload.paths[0] === 'string') ||
                      patchPayload?.fileHints?.[0]) ? (
                      <Button
                        size="small"
                        data-testid={`agent-analyze-patch-failure-${event.id}`}
                        onClick={() =>
                          handleAnalyzePatchFailure(
                            (Array.isArray(payload.paths) && typeof payload.paths[0] === 'string'
                              ? payload.paths[0]
                              : patchPayload?.fileHints?.[0] || '') as string,
                            typeof payload.error === 'string' ? payload.error : event.description
                          )
                        }
                      >
                        Analyze patch failure
                      </Button>
                    ) : null}
                    {patchPayload?.fileHints?.[0] ? (
                      <Button
                        size="small"
                        data-testid={`agent-redraft-patch-${event.id}`}
                        onClick={() => handleDraftPatchProposal(patchPayload.fileHints[0]!)}
                      >
                        Redraft patch
                      </Button>
                    ) : null}
                  </Space>
                ) : null}
              </Space>
            </div>
          ) : null}

          {event.payload && !isConfirmation && !hasCommandShape && !hasFileShape ? (
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          ) : null}
        </Space>
      </div>
    )
  }, [
    handleAnalyzeFailingFile,
    handleAnalyzePatchFailure,
      handleCreateFixPlan,
      handleCreateCompletionSummary,
      handleDraftPatchProposal,
      handleCreateHandoffNote,
      handleOpenFailingFile,
      handleRetryTestCommand,
      handleReviewVerifiedFix,
      handleSummarizeVerifiedFix,
      handleStartGuidedFix,
    ])

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
    if (!currentSessionId) {
      setBranchNodes({})
      setBranchRootId(null)
      setCurrentBranchId(null)
      setBranchSummaries([])
      setReplyAnchorId(null)
      setSelectedConversationNodeId(null)
      return
    }

    if (!messages.length) {
      void loadSession(currentSessionId)
    }
    void refreshBranchState(currentSessionId)
  }, [currentSessionId, loadSession, messages.length, refreshBranchState])

  useEffect(() => {
    if (selectedConversationNodeId && !branchNodes[selectedConversationNodeId]) {
      setSelectedConversationNodeId(null)
    }
  }, [branchNodes, selectedConversationNodeId])

  useEffect(() => {
    if (!currentSessionId || !agentMode) {
      return
    }

    const timeoutHandle = window.setTimeout(() => {
      const outcomePayload = agentOutcomeItems.map((item) => ({
        id: item.id,
        title: item.title,
        summary: item.summary,
        createdAt: item.createdAt,
      }))
      updateSessionMetadata(currentSessionId, {
        agent_mode: agentMode,
        agent_status: agentTaskStatus,
        execution_timeline: agentTimeline,
        pending_confirmation: pendingAgentConfirmation,
        workspace_root: agentWorkspaceRoot,
        auto_approve_safe_tools: autoApproveSafeTools,
        last_agent_goal: promptDraft,
        task_outcomes: outcomePayload,
        latest_task_outcome: outcomePayload[0] || null,
      })
      void updateChatSessionMetadata(currentSessionId, {
        agent_mode: agentMode,
        agent_status: agentTaskStatus,
        execution_timeline: agentTimeline,
        pending_confirmation: pendingAgentConfirmation,
        workspace_root: agentWorkspaceRoot,
        auto_approve_safe_tools: autoApproveSafeTools,
        last_agent_goal: promptDraft,
        task_outcomes: outcomePayload,
        latest_task_outcome: outcomePayload[0] || null,
      }).catch((error) => {
        console.error('Failed to sync agent session metadata:', error)
      })
    }, 150)

    return () => {
      window.clearTimeout(timeoutHandle)
    }
  }, [
    agentMode,
    agentTaskStatus,
    agentTimeline,
    agentWorkspaceRoot,
    autoApproveSafeTools,
    currentSessionId,
    agentOutcomeItems,
    pendingAgentConfirmation,
    promptDraft,
    updateSessionMetadata,
  ])

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
    clearAgentTimeline()
    setPendingAgentConfirmation(null)
    setAgentTaskStatus('idle')
    setPromptDraft('')
    clearAttachments()
    clearActiveCandidates()
    setSelectedExperimentId(null)
    setLastRunMetadata(null)
    setSelectedTaskOutcomeId(null)
  }, [
    clearActiveCandidates,
    clearAgentTimeline,
    clearAttachments,
    clearMessages,
    setAgentTaskStatus,
    setLastRunMetadata,
    setPendingAgentConfirmation,
    setPromptDraft,
    setSelectedExperimentId,
    setSelectedTaskOutcomeId,
  ])

  const handleLoadOutcomeFromHistory = useCallback(
    async (sessionId: string, outcomeId: string) => {
      setHistoryOpen(false)
      await loadSession(sessionId)
      setSelectedTaskOutcomeId(outcomeId)
      setAgentMode(true)
    },
    [loadSession, setAgentMode]
  )

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

  const handleSwitchToMainTimeline = useCallback(async () => {
    if (!currentSessionId) {
      return
    }

    await switchConversationToMainTimeline(currentSessionId)
    setReplyAnchorId(null)
    await refreshBranchState(currentSessionId)
  }, [currentSessionId, refreshBranchState])

  const ensureReplyContext = useCallback(
    async (sessionId: string) => {
      if (!replyAnchorId || replyAnchorId === activeBranchTipId) {
        return
      }

      const createPayload = await createConversationBranch(
        sessionId,
        replyAnchorId,
        `Reply ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
      )
      const nextBranchId = createPayload?.branch?.id as string | undefined
      if (!nextBranchId) {
        throw new Error('The branch service did not return a branch id.')
      }

      await switchConversationBranch(sessionId, nextBranchId)
      await refreshBranchState(sessionId)
    },
    [activeBranchTipId, refreshBranchState, replyAnchorId]
  )

  const persistPrimaryCandidateToSession = useCallback(
    async (sessionId: string, prompt: string, candidate: PlaygroundCandidate) => {
      const persistMessage = async (
        role: 'user' | 'assistant',
        content: string,
        metadata?: Record<string, unknown>
      ) => {
        await saveConversationMessage(sessionId, role, content, metadata)
      }

      await persistMessage('user', prompt, {
        source: 'playground',
        attachments: attachments.map((attachment) => ({
          id: attachment.id,
          name: attachment.name,
          type: attachment.type,
        })),
      })
      await persistMessage('assistant', candidate.content, {
        source: 'playground',
        candidate_id: candidate.id,
        run_metrics: candidate.run_metrics,
        knowledge_sources_count: candidate.knowledge_sources?.length || 0,
      })
    },
    [attachments]
  )

  const handleContinueFromMessage = useCallback(
    async (messageId: string) => {
      if (!currentSessionId) {
        message.info('Run one experiment first so there is a session to branch from.')
        return
      }

      setReplyAnchorId(messageId)
      setSelectedConversationNodeId(messageId)
      setResponseView('response')
      if (currentBranchId && messageId === activeBranchTipId) {
        return
      }

      const selectedNode = branchNodes[messageId]
      message.success(
        selectedNode
          ? `Next run will continue from: ${selectedNode.content.slice(0, 24)}`
          : 'Next run will continue from the selected message.'
      )
    },
    [activeBranchTipId, branchNodes, currentBranchId, currentSessionId, setResponseView]
  )

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

    let activeSessionId = currentSessionId
    if (!activeSessionId) {
      const createdSession = await createSession(prompt.slice(0, 48) || 'Untitled experiment', settings.modelId)
      activeSessionId = createdSession.id
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
      lastViewedAt: new Date().toISOString(),
      isFavorite: false,
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
    if (activeSessionId) {
      try {
        await ensureReplyContext(activeSessionId)
        await persistPrimaryCandidateToSession(activeSessionId, prompt, selectedCandidate)
        await loadSession(activeSessionId)
        await refreshBranchState(activeSessionId)
        setReplyAnchorId(null)
      } catch (error) {
        console.error('Failed to persist experiment result into the session tree:', error)
        message.warning(
          error instanceof Error
            ? error.message
            : 'The experiment completed, but the conversation tree could not be updated.'
        )
      }
    }
  }, [
    addExperimentSnapshot,
    attachments,
    canUseImageAttachments,
    cloudAIConfig,
    createSession,
    currentSessionId,
    ensureReplyContext,
    loadSession,
    persistPrimaryCandidateToSession,
    promptDraft,
    refreshBranchState,
    runExperimentCandidates,
    setActiveCandidates,
    setSelectedCandidateId,
    setReplyAnchorId,
    setResponseView,
    settings,
  ])

  const handleRunAgent = useCallback(async () => {
    const prompt = promptDraft.trim()
    if (!prompt) {
      message.warning('Describe the task before starting Agent Mode.')
      return
    }

    if (settings.backend === 'cloud' && !cloudAIConfig) {
      setConfigModalOpen(true)
      return
    }

    clearActiveCandidates()
    setSelectedExperimentId(null)
    setLastRunMetadata(null)

    await runAgentTask(
      {
        prompt,
        systemPrompt: settings.systemPrompt,
        responseFormat: settings.responseFormat,
        attachments,
        agentContext: {
          auto_repair_pipeline: true,
        },
        parameterOverrides: {
          temperature: settings.temperature,
          topP: settings.topP,
          maxTokens: settings.maxTokens,
          modelId: settings.modelId,
          backend: settings.backend,
        },
      },
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
  }, [
    attachments,
    clearActiveCandidates,
    cloudAIConfig,
    promptDraft,
    runAgentTask,
    setLastRunMetadata,
    setSelectedExperimentId,
    settings,
  ])

  const handlePrimaryAction = useCallback(() => {
    if (agentMode) {
      void handleRunAgent()
      return
    }
    void handleRun()
  }, [agentMode, handleRun, handleRunAgent])

  const handleResumeAgent = useCallback(() => {
    if (pendingAgentConfirmation) {
      void confirmAgentAction()
      return
    }

    const baseGoal =
      promptDraft.trim() ||
      latestUserMessage?.content?.trim() ||
      'Continue the previous task from the most recent execution state.'

    void resumeAgentTask(
      {
        prompt: baseGoal,
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
  }, [
    attachments,
    cloudAIConfig,
    confirmAgentAction,
    latestUserMessage?.content,
    pendingAgentConfirmation,
    promptDraft,
    resumeAgentTask,
    settings,
  ])

  const handleRetryAgent = useCallback(() => {
    if (!agentMode) {
      return
    }

    clearAgentTimeline()
    setPendingAgentConfirmation(null)
    setAgentTaskStatus('idle')
    void handleRunAgent()
  }, [agentMode, clearAgentTimeline, handleRunAgent, setAgentTaskStatus, setPendingAgentConfirmation])

  const handleResumeFromHistoryItem = useCallback(
    (eventId: string) => {
      const baseGoal =
        promptDraft.trim() ||
        latestUserMessage?.content?.trim() ||
        'Continue the previous task from the selected execution step.'

      void resumeAgentFromEvent(
        eventId,
        {
          prompt: baseGoal,
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
    },
    [attachments, cloudAIConfig, latestUserMessage?.content, promptDraft, resumeAgentFromEvent, settings]
  )

  const handleLoadSnapshot = useCallback(
    (snapshot: PlaygroundSnapshot) => {
      applyConfig(snapshot.experiment_config)
      setActiveCandidates(snapshot.candidates || [])
      setSelectedCandidateId(snapshot.selectedCandidateId || snapshot.candidates?.[0]?.id || null)
      setSelectedExperimentId(snapshot.id)
      const updatedSnapshot = {
        ...snapshot,
        lastViewedAt: new Date().toISOString(),
      }
      updateExperimentSnapshot(snapshot.id, {
        lastViewedAt: updatedSnapshot.lastViewedAt,
      })
      setLastRunMetadata(updatedSnapshot)
      setResponseView('response')
    },
    [
      applyConfig,
      setActiveCandidates,
      setLastRunMetadata,
      setResponseView,
      setSelectedCandidateId,
      setSelectedExperimentId,
      updateExperimentSnapshot,
    ]
  )

  const handleRestoreAndRunSnapshot = useCallback(
    async (snapshot: PlaygroundSnapshot) => {
      const config = snapshot.experiment_config

      if (!config.prompt.trim()) {
        message.warning('Snapshot prompt is empty. Update it before rerunning.')
        return
      }

      if (config.attachments.some((attachment) => attachment.type === 'image') && !canUseImageAttachments) {
        message.error('Image attachments are only available for cloud mode with GLM-4V right now.')
        return
      }

      if (config.backend === 'cloud' && !cloudAIConfig) {
        setConfigModalOpen(true)
        return
      }

      applyConfig(config)
      setAgentMode(false)
      setSelectedTaskOutcomeId(null)

      const candidates = await runExperimentCandidates(
        {
          prompt: config.prompt,
          systemPrompt: config.systemPrompt,
          responseFormat: config.responseFormat,
          attachments: config.attachments || [],
          parameterOverrides: {
            temperature: config.temperature,
            topP: config.topP,
            maxTokens: config.maxTokens,
            modelId: config.modelId,
            backend: config.backend,
          },
        },
        config.candidateCount || 1,
        config.backend === 'cloud' && cloudAIConfig
          ? {
              provider: cloudAIConfig.provider,
              apiKey: cloudAIConfig.api_key,
              keyId: cloudAIConfig.key_id,
              model: config.modelId,
              groupId: cloudAIConfig.group_id,
              baseUrl: cloudAIConfig.base_url,
            }
          : undefined
      )

      if (!candidates.length) {
        return
      }

      const selected =
        candidates.find((candidate) => candidate.status === 'completed') || candidates[0]

      if (!selected) {
        return
      }

      const now = new Date().toISOString()
      const rerunSnapshot: PlaygroundSnapshot = {
        id: `experiment_${Date.now()}`,
        createdAt: now,
        lastViewedAt: now,
        isFavorite: false,
        title: `${snapshot.title} (rerun)`.slice(0, 64),
        response: selected.content,
        selectedCandidateId: selected.id,
        candidates,
        raw_response: selected.raw_response,
        knowledge_sources: selected.knowledge_sources,
        retrieval_info: selected.retrieval_info,
        memory_context: selected.memory_context,
        unified_context: selected.unified_context,
        experiment_config: {
          ...config,
          attachments: config.attachments || [],
        },
        run_metrics: selected.run_metrics,
      }

      addExperimentSnapshot(rerunSnapshot)
      setActiveCandidates(candidates)
      setSelectedCandidateId(selected.id)
      setSelectedExperimentId(rerunSnapshot.id)
      setLastRunMetadata(rerunSnapshot)
      setResponseView('response')

      if (!currentSessionId) {
        await createSession(rerunSnapshot.title, config.modelId)
      }

      message.success('Snapshot restored and rerun complete.')
    },
    [
      addExperimentSnapshot,
      applyConfig,
      canUseImageAttachments,
      cloudAIConfig,
      createSession,
      currentSessionId,
      runExperimentCandidates,
      setActiveCandidates,
      setAgentMode,
      setLastRunMetadata,
      setResponseView,
      setSelectedCandidateId,
      setSelectedExperimentId,
      setSelectedTaskOutcomeId,
    ]
  )

  const latestAssistantMessage = [...messages].reverse().find((msg) => msg.role === 'assistant')
  const responseContent =
    viewedConversationNode?.content ||
    (isStreaming ? streamState.content : selectedCandidate?.content || selectedSnapshot?.response) ||
    latestAssistantMessage?.content ||
    ''
  const formattedJson = formatResponseContent(
    responseContent,
    selectedSnapshot?.experiment_config.responseFormat || settings.responseFormat
  )
  const patchDraft = useMemo(() => extractPatchDraft(responseContent), [responseContent])

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
      key: 'patch',
      label: 'Patch Draft',
      children: patchDraft ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }} data-testid="patch-draft-panel">
          {patchDraft.fileHints.length ? (
            <div>
              <Text strong>Files</Text>
              <div style={{ marginTop: 6 }}>
                <Space wrap size={6}>
                  {patchDraft.fileHints.map((fileHint) => (
                    <Tag key={fileHint}>{fileHint}</Tag>
                  ))}
                </Space>
              </div>
            </div>
          ) : null}
          <Button
            size="small"
            icon={<CopyOutlined />}
            data-testid="patch-draft-copy"
            onClick={async () => {
              await navigator.clipboard.writeText(patchDraft.content)
              message.success('Patch draft copied.')
            }}
          >
            Copy patch draft
          </Button>
          <Button
            size="small"
            type="primary"
            data-testid="patch-draft-apply"
            onClick={() => {
              Modal.confirm({
                title: 'Apply patch draft?',
                content:
                  'This will apply the generated diff to the current workspace. Review the patch draft before continuing.',
                okText: 'Apply patch',
                cancelText: 'Cancel',
                onOk: () => applyPatchDraft(patchDraft.content),
              })
            }}
          >
            Apply patch draft
          </Button>
          {recentFailedTestsCommand ? (
            <Button
              size="small"
              data-testid="patch-draft-apply-rerun"
              onClick={() => {
                Modal.confirm({
                  title: 'Apply patch and rerun tests?',
                  content:
                    'This will apply the generated diff and immediately rerun the most recent failing test command.',
                  okText: 'Apply and rerun',
                  cancelText: 'Cancel',
                  onOk: () => applyPatchDraft(patchDraft.content, { rerunCommand: recentFailedTestsCommand }),
                })
              }}
            >
              Apply and rerun tests
            </Button>
          ) : null}
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>{patchDraft.content}</pre>
        </Space>
      ) : (
        <Empty description="No diff-style patch draft was detected in this response." />
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
        lastViewedAt: new Date().toISOString(),
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

  const handleToggleFavoriteSnapshot = useCallback(
    (snapshot: PlaygroundSnapshot) => {
      const nextFavorite = !snapshot.isFavorite
      updateExperimentSnapshot(snapshot.id, {
        isFavorite: nextFavorite,
        lastViewedAt: new Date().toISOString(),
      })
      if (selectedSnapshot?.id === snapshot.id) {
        setLastRunMetadata({
          ...snapshot,
          isFavorite: nextFavorite,
          lastViewedAt: new Date().toISOString(),
        })
      }
      message.success(nextFavorite ? 'Experiment added to favorites.' : 'Experiment removed from favorites.')
    },
    [selectedSnapshot, setLastRunMetadata, updateExperimentSnapshot]
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
              <Space size={8}>
                <Text strong>Agent Mode</Text>
                <Switch checked={agentMode} onChange={setAgentMode} data-testid="agent-mode-switch" />
              </Space>
              <Tag color={agentStatusColor}>{agentMode ? `Agent: ${agentTaskStatus}` : 'Playground only'}</Tag>
              <Tag color={isStreaming ? 'processing' : 'default'}>
                {isStreaming ? 'Running' : agentMode ? 'Ready for task' : 'Idle'}
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
                      {agentMode ? 'Agent Workspace' : 'Build'}
                    </Title>
                    <Text type="secondary">
                      {agentMode
                        ? 'Give the assistant a goal, inspect each execution step, and confirm risky actions before they run.'
                        : 'Tune the prompt, choose context sources, and run a single experiment.'}
                    </Text>
                  </div>

                  <Card size="small" title="Agent Controls" data-testid="agent-panel">
                    <Space direction="vertical" size={14} style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong>Enable Agent Mode</Text>
                          <div>
                            <Text type="secondary">Switch from playground experiments to task execution.</Text>
                          </div>
                        </div>
                        <Switch checked={agentMode} onChange={setAgentMode} />
                      </div>

                      <div>
                        <Text strong>Workspace Root</Text>
                        <Input
                          data-testid="agent-workspace-root"
                          placeholder="C:\\project\\workspace"
                          value={agentWorkspaceRoot}
                          onChange={(event) => setAgentWorkspaceRoot(event.target.value)}
                        />
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong>Auto-approve safe tools</Text>
                          <div>
                            <Text type="secondary">Read-only tools can continue without extra confirmation.</Text>
                          </div>
                        </div>
                        <Switch checked={autoApproveSafeTools} onChange={setAutoApproveSafeTools} />
                      </div>
                    </Space>
                  </Card>

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
                    title="Conversation Path"
                    extra={
                      <Space size={8} wrap>
                        <Space size={8}>
                          <Text type="secondary">Active path only</Text>
                          <Switch checked={showActivePathOnly} onChange={setShowActivePathOnly} />
                        </Space>
                        <Button
                          size="small"
                          onClick={() => {
                            if (!viewedParentNode) {
                              return
                            }
                            setSelectedConversationNodeId(viewedParentNode.id)
                            setResponseView('response')
                          }}
                          disabled={!viewedParentNode}
                        >
                          Parent
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            if (!currentPathTipId) {
                              return
                            }
                            setSelectedConversationNodeId(currentPathTipId)
                            setResponseView('response')
                          }}
                          disabled={!currentPathTipId || selectedConversationNodeId === currentPathTipId}
                        >
                          Latest tip
                        </Button>
                        <Button
                          size="small"
                          icon={<BranchesOutlined />}
                          onClick={() => setBranchManagerOpen(true)}
                          disabled={!currentSessionId}
                        >
                          Branches
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            void handleSwitchToMainTimeline().catch((error) => {
                              message.warning(
                                error instanceof Error
                                  ? error.message
                                  : 'Failed to return to the main timeline.'
                              )
                            })
                          }}
                          disabled={!currentSessionId || (!currentBranchId && !replyAnchorId)}
                        >
                          Main Line
                        </Button>
                      </Space>
                    }
                  >
                    {!currentSessionId ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="Run an experiment once to start building the conversation tree."
                      />
                    ) : !sortedBranchMessages.length ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="This session has no persisted messages yet."
                      />
                    ) : (
                      <Space direction="vertical" size={12} style={{ width: '100%' }}>
                        <Space wrap size={8}>
                          {currentSession ? <Tag>{currentSession.title}</Tag> : null}
                          <Tag color={currentBranch ? 'blue' : 'default'}>
                            {currentBranch ? `Current branch: ${currentBranch.name}` : 'Current branch: main line'}
                          </Tag>
                          <Tag>
                            {visibleConversationNodes.length}/{sortedBranchMessages.length} messages
                          </Tag>
                          <Tag color="processing">{branchPathMessages.length} on active path</Tag>
                          <Tag color="magenta">
                            {sortedBranchMessages.filter((node) => node.children_ids.length > 1).length} branch points
                          </Tag>
                          {branchRootId ? <Tag>Root ready</Tag> : null}
                          {replyAnchorId && branchNodes[replyAnchorId] ? (
                            <Tag color="gold">
                              Reply anchor: {branchNodes[replyAnchorId]!.content.slice(0, 18)}
                            </Tag>
                          ) : null}
                        </Space>

                        {branchPathMessages.length ? (
                          <div>
                            <Text type="secondary">Active path</Text>
                            <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                              {branchPathMessages.map((node, index) => (
                                <Tag key={node.id} color={node.id === currentPathTipId ? 'gold' : 'processing'}>
                                  {index + 1}. {node.role}
                                </Tag>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <List
                          size="small"
                          dataSource={visibleConversationNodes}
                          renderItem={(node) => {
                            const parentNode = node.parent_id ? branchNodes[node.parent_id] : null
                            const isOnCurrentPath = currentPathIds.has(node.id)
                            const isReplyAnchor = node.id === replyAnchorId
                            const isCurrentTip = node.id === currentPathTipId
                            const childCount = node.children_ids.length
                            const hasBranches = childCount > 1

                            return (
                              <List.Item
                                onClick={() => {
                                  setSelectedConversationNodeId(node.id)
                                  setResponseView('response')
                                }}
                                style={{
                                  cursor: 'pointer',
                                  borderRadius: 14,
                                  padding: '12px 14px',
                                  marginBottom: 8,
                                  border: isReplyAnchor
                                    ? '1px solid rgba(250, 173, 20, 0.55)'
                                    : isOnCurrentPath
                                      ? '1px solid rgba(22, 119, 255, 0.28)'
                                      : '1px solid rgba(15, 23, 42, 0.08)',
                                  background: isReplyAnchor
                                    ? 'rgba(250, 173, 20, 0.12)'
                                    : selectedConversationNodeId === node.id
                                      ? 'rgba(114, 46, 209, 0.10)'
                                    : isOnCurrentPath
                                      ? 'rgba(22, 119, 255, 0.08)'
                                      : 'rgba(15, 23, 42, 0.02)',
                                }}
                                actions={[
                                  <Button
                                    key="continue"
                                    type={isReplyAnchor ? 'primary' : 'link'}
                                    size="small"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      void handleContinueFromMessage(node.id)
                                    }}
                                  >
                                    {isReplyAnchor ? 'Selected' : 'Continue here'}
                                  </Button>,
                                ]}
                              >
                                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                  <Space wrap size={8}>
                                    <Tag color={node.role === 'user' ? 'cyan' : node.role === 'assistant' ? 'purple' : 'default'}>
                                      {node.role}
                                    </Tag>
                                    {node.branch_name ? <Tag color="blue">{node.branch_name}</Tag> : null}
                                    {isCurrentTip ? <Tag color="gold">Current tip</Tag> : null}
                                    {isOnCurrentPath ? <Tag color="processing">Active path</Tag> : null}
                                    {node.id === branchRootId ? <Tag>Root</Tag> : null}
                                    {childCount > 0 ? (
                                      <Tag color={hasBranches ? 'magenta' : 'default'}>
                                        {childCount} child{childCount > 1 ? 'ren' : ''}
                                      </Tag>
                                    ) : (
                                      <Tag>Leaf</Tag>
                                    )}
                                    {hasBranches ? <Tag color="magenta">Branch point</Tag> : null}
                                  </Space>
                                  <Text strong>{node.content.slice(0, 96) || '(empty message)'}</Text>
                                  <Space wrap size={8}>
                                    <Text type="secondary">
                                      {new Date(node.timestamp).toLocaleString('zh-CN')}
                                    </Text>
                                    {parentNode ? (
                                      <Text type="secondary">
                                        Parent: {parentNode.content.slice(0, 40)}
                                      </Text>
                                    ) : (
                                      <Text type="secondary">Parent: root</Text>
                                    )}
                                  </Space>
                                </Space>
                              </List.Item>
                            )
                          }}
                        />
                      </Space>
                    )}
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
                      onClick={handlePrimaryAction}
                      loading={isStreaming}
                      data-testid="run-button"
                    >
                      {agentMode ? 'Run Task' : 'Run Experiment'}
                    </Button>
                    <Space wrap>
                      <Button onClick={stopStream} disabled={!isStreaming}>
                        Stop
                      </Button>
                      {agentMode && pendingAgentConfirmation ? (
                        <>
                          <Button
                            type="primary"
                            onClick={() => void confirmAgentAction()}
                            data-testid="agent-confirm-button"
                          >
                            Confirm Action
                          </Button>
                          <Button danger onClick={cancelAgentAction} data-testid="agent-cancel-button">
                            Reject
                          </Button>
                        </>
                      ) : null}
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
                {agentMode ? (
                  <>
                    <Card size="small" style={panelStyle} data-testid="agent-status-card">
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Space wrap>
                          <Tag icon={<RobotOutlined />} color="blue">
                            Agent Mode
                          </Tag>
                          <Tag color={agentStatusColor}>{agentTaskStatus}</Tag>
                          {agentWorkspaceRoot ? <Tag>{agentWorkspaceRoot}</Tag> : null}
                          {pendingAgentConfirmation ? <Tag color="gold">Awaiting confirmation</Tag> : null}
                        </Space>
                        <Paragraph style={{ marginBottom: 0 }} type="secondary">
                          The execution timeline below shows planning, tool calls, confirmations, and final task outcome.
                        </Paragraph>
                        <Space wrap>
                          <Button
                            size="small"
                            type="primary"
                            onClick={handleResumeAgent}
                            disabled={
                              !(agentTaskStatus === 'waiting_confirmation' || agentTaskStatus === 'stopped')
                            }
                            data-testid="agent-resume-button"
                          >
                            Resume
                          </Button>
                          <Button
                            size="small"
                            onClick={handleRetryAgent}
                            disabled={
                              !['failed', 'stopped', 'completed', 'waiting_confirmation'].includes(
                                agentTaskStatus
                              )
                            }
                            data-testid="agent-retry-button"
                          >
                            Retry
                          </Button>
                        </Space>
                      </Space>
                    </Card>

                    {pendingAgentConfirmation ? (
                      <Alert
                        type="warning"
                        showIcon
                        message="Confirmation required"
                        description={
                          <Space direction="vertical" size={8}>
                            <Text>{pendingAgentConfirmation.description}</Text>
                            <Text type="secondary">
                              Action: {pendingAgentConfirmation.action} | Risk: {pendingAgentConfirmation.riskLevel}
                            </Text>
                          </Space>
                        }
                      />
                    ) : null}

                    <Card
                      size="small"
                      title="Automation Trace"
                      data-testid="agent-automation-trace-card"
                      extra={
                        <Space wrap size={8}>
                          <Segmented
                            data-testid="automation-trace-filter"
                            size="small"
                            value={automationTraceFilter}
                            options={[
                              { label: 'All', value: 'all' },
                              { label: 'Continue', value: 'auto_continue' },
                              { label: 'Recover', value: 'auto_recover' },
                            ]}
                            onChange={(value) =>
                              setAutomationTraceFilter(value as 'all' | 'auto_continue' | 'auto_recover')
                            }
                          />
                          <Select
                            size="small"
                            style={{ minWidth: 110 }}
                            data-testid="automation-report-limit"
                            value={automationReportLimit}
                            options={[
                              { label: 'Last 5', value: 5 },
                              { label: 'Last 8', value: 8 },
                              { label: 'Last 12', value: 12 },
                            ]}
                            onChange={(value) => setAutomationReportLimit(value)}
                          />
                          <Button
                            size="small"
                            data-testid="automation-trace-copy-summary"
                            onClick={async () => {
                              if (!navigator.clipboard?.writeText) {
                                message.warning('Clipboard is unavailable in this environment.')
                                return
                              }
                              await navigator.clipboard.writeText(automationFailureSummary)
                              message.success('Automation summary copied.')
                            }}
                          >
                            Copy Failure Summary
                          </Button>
                          <Button
                            size="small"
                            icon={<DownloadOutlined />}
                            data-testid="automation-trace-export-markdown"
                            onClick={() => {
                              const blob = new Blob([automationMarkdownReport], {
                                type: 'text/markdown;charset=utf-8',
                              })
                              const url = URL.createObjectURL(blob)
                              const anchor = document.createElement('a')
                              anchor.href = url
                              anchor.download = `automation-trace-${new Date()
                                .toISOString()
                                .replace(/[:.]/g, '-')}.md`
                              anchor.click()
                              URL.revokeObjectURL(url)
                              message.success('Automation markdown report exported.')
                            }}
                          >
                            Export Markdown
                          </Button>
                        </Space>
                      }
                    >
                      {filteredAutomationTraceItems.length ? (
                        <List
                          size="small"
                          dataSource={filteredAutomationTraceItems}
                          renderItem={(item) => (
                            <List.Item key={item.id} data-testid={`agent-automation-item-${item.id}`}>
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <Space wrap size={8}>
                                  <Text strong>{item.title}</Text>
                                  <Tag color={item.type === 'auto_recover' ? 'purple' : 'blue'}>
                                    {item.type === 'auto_recover' ? 'Auto Recover' : 'Auto Continue'}
                                  </Tag>
                                  <Tag>{item.status}</Tag>
                                  <Tag>Attempt {item.attempt}</Tag>
                                </Space>
                                <Text>{item.reason}</Text>
                                <Text type="secondary">
                                  {new Date(item.createdAt).toLocaleString('zh-CN')}
                                </Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty description="No automation events for the current filter." />
                      )}
                    </Card>

                    <Card size="small" title="Execution Timeline" data-testid="agent-timeline-card">
                      {agentStepGroups.length ? (
                        <Collapse
                          ghost
                          items={agentStepGroups.map((group) => ({
                            key: group.key,
                            label: (
                              <Space wrap size={8}>
                                <Text strong>{group.label}</Text>
                                <Tag>{group.status}</Tag>
                                <Tag>{group.events.length} events</Tag>
                              </Space>
                            ),
                            children: (
                              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                                {group.events.map(renderAgentEvent)}
                              </Space>
                            ),
                          }))}
                        />
                      ) : (
                        <Empty description="Start an agent task to inspect the execution timeline." />
                      )}
                    </Card>

                    <Card size="small" title="Task History" data-testid="agent-history-card">
                      {agentTaskHistory.length ? (
                        <List
                          dataSource={agentTaskHistory}
                          renderItem={(item) => (
                            <List.Item key={item.id}>
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <Space wrap size={8}>
                                  <Text strong>{item.title}</Text>
                                  <Tag>{item.status}</Tag>
                                  {item.toolName ? <Tag color="geekblue">{item.toolName}</Tag> : null}
                                </Space>
                                <Text>{item.summary}</Text>
                                <Text type="secondary">
                                  {new Date(item.createdAt).toLocaleString('zh-CN')}
                                </Text>
                                <Space>
                                  <Button
                                    size="small"
                                    type="link"
                                    data-testid={`agent-history-resume-${item.id}`}
                                    onClick={() => handleResumeFromHistoryItem(item.id)}
                                  >
                                    Continue From Here
                                  </Button>
                                </Space>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty description="Task history will appear after the first execution step." />
                      )}
                    </Card>

                    <Card size="small" title="Task Outcomes" data-testid="agent-outcomes-card">
                      {agentOutcomeItems.length ? (
                        <List
                          dataSource={agentOutcomeItems}
                          renderItem={(item) => (
                            <List.Item
                              key={item.id}
                              data-testid={`agent-outcome-item-${item.id}`}
                              style={{
                                borderRadius: 12,
                                padding: 12,
                                background:
                                  selectedTaskOutcomeId === item.id
                                    ? 'rgba(22, 119, 255, 0.10)'
                                    : 'transparent',
                                border:
                                  selectedTaskOutcomeId === item.id
                                    ? '1px solid rgba(22, 119, 255, 0.28)'
                                    : '1px solid transparent',
                              }}
                            >
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <Space wrap size={8}>
                                  <Text strong>{item.title}</Text>
                                  <Tag color="green">Recorded</Tag>
                                  {selectedTaskOutcomeId === item.id ? <Tag color="blue">Focused</Tag> : null}
                                </Space>
                                <Text>{item.summary}</Text>
                                <Text type="secondary">
                                  {new Date(item.createdAt).toLocaleString('zh-CN')}
                                </Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty description="Completion summaries and handoff notes will appear here." />
                      )}
                    </Card>
                  </>
                ) : null}

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
                    {viewedConversationNode ? (
                      <Alert
                        style={{ marginBottom: 12 }}
                        type="info"
                        showIcon
                        message={`Viewing ${viewedConversationNode.role} node from the conversation tree`}
                        description={
                          <Space direction="vertical" size={8} style={{ width: '100%' }}>
                            <Space wrap size={8}>
                              {viewedConversationNode.branch_name ? (
                                <Tag color="blue">{viewedConversationNode.branch_name}</Tag>
                              ) : (
                                <Tag>Main line</Tag>
                              )}
                              <Tag color={viewedConversationNode.id === currentPathTipId ? 'gold' : 'default'}>
                                {viewedConversationNode.id === currentPathTipId ? 'Current tip' : 'Historical node'}
                              </Tag>
                              {replyAnchorId === viewedConversationNode.id ? (
                                <Tag color="gold">Reply anchor</Tag>
                              ) : null}
                              {viewedParentNode ? (
                                <Tag>Parent ready</Tag>
                              ) : (
                                <Tag>Root node</Tag>
                              )}
                            </Space>
                            <Space wrap size={8}>
                              <Button
                                size="small"
                                onClick={() => {
                                  if (!viewedParentNode) {
                                    return
                                  }
                                  setSelectedConversationNodeId(viewedParentNode.id)
                                  setResponseView('response')
                                }}
                                disabled={!viewedParentNode}
                              >
                                Jump to parent
                              </Button>
                              <Button
                                size="small"
                                onClick={() => {
                                  if (!currentPathTipId) {
                                    return
                                  }
                                  setSelectedConversationNodeId(currentPathTipId)
                                  setResponseView('response')
                                }}
                                disabled={!currentPathTipId || selectedConversationNodeId === currentPathTipId}
                              >
                                Jump to latest tip
                              </Button>
                            </Space>
                          </Space>
                        }
                      />
                    ) : null}
                    <Tabs
                      data-testid="response-tabs"
                      activeKey={responseView}
                      items={responseTabs}
                      onChange={(value) =>
                        setResponseView(value as 'response' | 'patch' | 'sources' | 'metadata' | 'raw')
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
                    <Space size={8} wrap>
                      <Tag data-testid="history-count-tag">
                        {filteredExperimentSnapshots.length}/{experimentSnapshots.length} shown
                      </Tag>
                      <Button
                        type="link"
                        onClick={() => {
                          setHistorySearch('')
                          setHistoryBackendFilter('all')
                          setHistoryModelFilter('all')
                          setHistoryFavoritesOnly(false)
                          setHistorySort('newest')
                        }}
                        disabled={
                          !historySearch.trim() &&
                          historyBackendFilter === 'all' &&
                          historyModelFilter === 'all' &&
                          !historyFavoritesOnly &&
                          historySort === 'newest'
                        }
                      >
                        Clear Filters
                      </Button>
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
                    </Space>
                  }
                >
                  {experimentSnapshots.length ? (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Input
                        data-testid="history-search-input"
                        placeholder="Search title, prompt, response, model, or backend"
                        value={historySearch}
                        onChange={(event) => setHistorySearch(event.target.value)}
                      />
                      <Space size={8} wrap style={{ width: '100%' }}>
                        <Segmented
                          data-testid="history-sort"
                          value={historySort}
                          options={[
                            { label: 'Newest', value: 'newest' },
                            { label: 'Recently Viewed', value: 'recent' },
                            { label: 'Favorites First', value: 'favorites' },
                          ]}
                          onChange={(value) =>
                            setHistorySort(value as 'newest' | 'recent' | 'favorites')
                          }
                        />
                        <Switch
                          data-testid="history-favorites-only"
                          checked={historyFavoritesOnly}
                          onChange={setHistoryFavoritesOnly}
                        />
                        <Text type="secondary">Favorites only</Text>
                      </Space>
                      <Space size={8} wrap style={{ width: '100%' }}>
                        <Select
                          data-testid="history-backend-filter"
                          style={{ minWidth: 160 }}
                          value={historyBackendFilter}
                          options={[
                            { label: 'All backends', value: 'all' },
                            ...historyBackendOptions.map((backend) => ({
                              label: backend,
                              value: backend,
                            })),
                          ]}
                          onChange={setHistoryBackendFilter}
                        />
                        <Select
                          data-testid="history-model-filter"
                          style={{ minWidth: 180 }}
                          value={historyModelFilter}
                          options={[
                            { label: 'All models', value: 'all' },
                            ...historyModelOptions.map((model) => ({
                              label: model,
                              value: model,
                            })),
                          ]}
                          onChange={setHistoryModelFilter}
                        />
                      </Space>
                      {filteredExperimentSnapshots.length ? (
                        <List
                          data-testid="experiment-history"
                          dataSource={filteredExperimentSnapshots}
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
                                  key="restore-run"
                                  type="link"
                                  data-testid={`history-restore-run-${snapshot.id}`}
                                  onClick={() => {
                                    void handleRestoreAndRunSnapshot(snapshot)
                                  }}
                                >
                                  Restore & Run
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
                                    <Button
                                      type="text"
                                      size="small"
                                      data-testid={`history-favorite-${snapshot.id}`}
                                      icon={
                                        snapshot.isFavorite ? (
                                          <StarFilled style={{ color: '#faad14' }} />
                                        ) : (
                                          <StarOutlined />
                                        )
                                      }
                                      onClick={() => handleToggleFavoriteSnapshot(snapshot)}
                                    />
                                    <Tag>{snapshot.experiment_config.backend}</Tag>
                                    <Tag>{snapshot.experiment_config.modelId || 'Unknown model'}</Tag>
                                    <Tag>{snapshot.candidates?.length || 1} candidates</Tag>
                                    {snapshot.isFavorite ? <Tag color="gold">Favorite</Tag> : null}
                                  </Space>
                                  <Text type="secondary">
                                    {new Date(snapshot.createdAt).toLocaleString('zh-CN')}
                                  </Text>
                                  {snapshot.lastViewedAt ? (
                                    <Text type="secondary">
                                      Viewed {new Date(snapshot.lastViewedAt).toLocaleString('zh-CN')}
                                    </Text>
                                  ) : null}
                                  <Text ellipsis>{snapshot.response.slice(0, 120) || 'No response content.'}</Text>
                                </Space>
                              </div>
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description="No experiments match the current filters."
                        />
                      )}
                    </Space>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No experiments yet." />
                  )}
                </Card>
              </div>
            </div>
          </div>
        </div>

        <ChatBranchManager
          visible={branchManagerOpen}
          sessionId={currentSessionId || ''}
          onClose={() => setBranchManagerOpen(false)}
          onBranchSwitch={() => {
            if (currentSessionId) {
              void refreshBranchState(currentSessionId)
            }
            setReplyAnchorId(null)
          }}
          onBranchCreate={() => {
            if (currentSessionId) {
              void refreshBranchState(currentSessionId)
            }
          }}
        />

        <ChatHistoryDrawer
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          sessions={sessions.map((session) => ({
            id: session.id,
            title: session.title,
            created_at: session.createdAt,
            updated_at: session.updatedAt,
            message_count: session.messageCount,
            metadata: session.metadata,
          }))}
          onLoadSession={(id) => loadSession(id)}
          onLoadOutcome={handleLoadOutcomeFromHistory}
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
