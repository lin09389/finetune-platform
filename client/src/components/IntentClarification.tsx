import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, Empty, Input, List, Modal, Progress, Space, Spin, Tag, Typography, message as antdMessage } from 'antd'

const { Text, Title } = Typography

interface ExtractedParam {
  name: string
  value: unknown
  param_type: string
  confidence: number
  raw_text: string
}

interface DetectedIntent {
  intent_type: string
  action: string
  params: ExtractedParam[]
  confidence: number
  description: string
  need_clarification: boolean
  clarification_question: string
  raw_match: string
}

interface ClarificationOption {
  label: string
  value: string
}

interface ClarificationDialog {
  question: string
  options: ClarificationOption[]
}

interface IntentClarificationProps {
  visible: boolean
  message: string
  onConfirm: (intent: DetectedIntent, params: Record<string, unknown>) => void
  onCancel: () => void
  onMultiIntentSelect?: (intents: DetectedIntent[]) => void
  context?: Record<string, unknown>
}

const IntentClarification: React.FC<IntentClarificationProps> = ({
  visible,
  message,
  onConfirm,
  onCancel,
  onMultiIntentSelect,
  context,
}) => {
  const [loading, setLoading] = useState(false)
  const [detectedIntents, setDetectedIntents] = useState<DetectedIntent[]>([])
  const [hasAmbiguity, setHasAmbiguity] = useState(false)
  const [clarificationDialog, setClarificationDialog] = useState<ClarificationDialog | null>(null)
  const [selectedIntent, setSelectedIntent] = useState<DetectedIntent | null>(null)
  const [customParams, setCustomParams] = useState<Record<string, string>>({})

  const requiredParamsMap = useMemo<Record<string, string[]>>(
    () => ({
      file_create: ['file_path'],
      file_read: ['file_path'],
      file_write: ['file_path', 'content'],
      file_delete: ['file_path'],
      app_open: ['app_name'],
      url_open: ['url'],
      mouse_click: ['x', 'y'],
      keyboard_type: ['text'],
    }),
    []
  )

  const checkMissingParams = useCallback(
    (intent: DetectedIntent): string[] => {
      const required = requiredParamsMap[intent.action] || []
      const existing = new Set(intent.params.map((p) => p.name))
      return required.filter((name) => !existing.has(name) || !intent.params.find((p) => p.name === name)?.value)
    },
    [requiredParamsMap]
  )

  const mapIntent = (intent: any): DetectedIntent => ({
    intent_type: intent.intent_type || 'unknown',
    action: intent.action || '',
    params: Object.entries(intent.params || {}).map(([name, value]) => ({
      name,
      value,
      param_type: typeof value,
      confidence: Number(intent.confidence || 0),
      raw_text: String(value ?? ''),
    })),
    confidence: Number(intent.confidence || 0),
    description: intent.description || intent.intent_type || 'Detected intent',
    need_clarification: Boolean(intent.need_confirm),
    clarification_question: intent.need_confirm ? 'More input is required before execution.' : '',
    raw_match: '',
  })

  const detectIntent = useCallback(async () => {
    if (!message) return

    setLoading(true)
    try {
      const response = await fetch('/api/agent/detect-intent-multi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context }),
      })
      const data = await response.json()

      if (!data.detected) {
        setDetectedIntents([])
        setSelectedIntent(null)
        return
      }

      const intents: DetectedIntent[] = (data.intents || []).map(mapIntent)
      setDetectedIntents(intents)
      setHasAmbiguity(Boolean(data.has_ambiguity))
      setClarificationDialog(data.clarification_dialog || null)
      if (intents.length === 1 && !data.has_ambiguity) {
        setSelectedIntent(intents[0] || null)
      }
    } catch (error) {
      console.error('intent detect failed', error)
      antdMessage.error('Intent detection failed')
    } finally {
      setLoading(false)
    }
  }, [message, context])

  useEffect(() => {
    if (visible && message) {
      void detectIntent()
    }
  }, [visible, message, detectIntent])

  useEffect(() => {
    if (!visible) {
      setDetectedIntents([])
      setSelectedIntent(null)
      setClarificationDialog(null)
      setCustomParams({})
    }
  }, [visible])

  const handleConfirm = () => {
    if (!selectedIntent) return
    const params: Record<string, unknown> = {}
    selectedIntent.params.forEach((p) => {
      params[p.name] = p.value
    })
    Object.entries(customParams).forEach(([k, v]) => {
      if (v) params[k] = v
    })
    onConfirm(selectedIntent, params)
  }

  const handleClarificationResponse = (value: string) => {
    if (value === 'cancel') {
      onCancel()
      return
    }
    if (value === 'all') {
      if (onMultiIntentSelect) onMultiIntentSelect(detectedIntents)
      return
    }
    if (value === 'confirm') {
      setSelectedIntent(detectedIntents[0] || null)
    }
  }

  return (
    <Modal
      title="Intent Confirmation"
      open={visible}
      onCancel={onCancel}
      width={760}
      footer={[
        <Button key="cancel" onClick={onCancel}>Cancel</Button>,
        <Button key="confirm" type="primary" disabled={!selectedIntent} onClick={handleConfirm}>Confirm</Button>,
        detectedIntents.length > 1 ? (
          <Button key="all" onClick={() => onMultiIntentSelect && onMultiIntentSelect(detectedIntents)}>Run All</Button>
        ) : null,
      ]}
    >
      <Spin spinning={loading}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert message="Original Message" description={message} type="info" showIcon />

          {hasAmbiguity && clarificationDialog ? (
            <Card>
              <Space direction="vertical">
                <Text strong>{clarificationDialog.question}</Text>
                <Space wrap>
                  {(clarificationDialog.options || []).map((opt, idx) => (
                    <Button key={idx} onClick={() => handleClarificationResponse(opt.value)}>{opt.label}</Button>
                  ))}
                </Space>
              </Space>
            </Card>
          ) : null}

          {detectedIntents.length === 0 && !loading ? (
            <Empty description="No intent detected" />
          ) : (
            <>
              <Title level={5}>Detected Intents <Badge count={detectedIntents.length} /></Title>
              <List
                dataSource={detectedIntents}
                renderItem={(intent) => {
                  const missing = checkMissingParams(intent)
                  const selected = selectedIntent === intent
                  return (
                    <Card
                      key={`${intent.intent_type}-${intent.action}-${intent.confidence}`}
                      hoverable
                      onClick={() => setSelectedIntent(intent)}
                      style={{ border: selected ? '2px solid #1677ff' : undefined }}
                    >
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                          <Text strong>{intent.description}</Text>
                          <Tag>{intent.intent_type}</Tag>
                          <Tag color="blue">{intent.action}</Tag>
                        </Space>
                        <Progress percent={Math.round(intent.confidence * 100)} size="small" />
                        <Space wrap>
                          {intent.params.map((p) => (
                            <Tag key={p.name}>{p.name}: {String(p.value)}</Tag>
                          ))}
                        </Space>
                        {missing.length > 0 ? (
                          <Alert type="warning" showIcon message={`Missing params: ${missing.join(', ')}`} />
                        ) : null}
                      </Space>
                    </Card>
                  )
                }}
              />

              {selectedIntent ? (
                <Card>
                  <Title level={5}>Supplement Params</Title>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {checkMissingParams(selectedIntent).map((name) => (
                      <Input
                        key={name}
                        value={customParams[name] || ''}
                        placeholder={`Input ${name}`}
                        onChange={(e) => setCustomParams((prev) => ({ ...prev, [name]: e.target.value }))}
                      />
                    ))}
                  </Space>
                </Card>
              ) : null}
            </>
          )}
        </Space>
      </Spin>
    </Modal>
  )
}

export default IntentClarification
