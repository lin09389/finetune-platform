import { useState, useEffect } from 'react'
import { Card, Select, Input, Button, Space, Divider, Tag, Row, Col, Slider, Alert, message, Badge } from 'antd'
import { SendOutlined, LoadingOutlined, ClearOutlined, SwapOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { streamInference, getBackends, switchBackend, getOllamaStatus, getModelList } from '../services/api'
import type { BackendInfo } from '../types'

const { TextArea } = Input

export default function Inference() {
  const { models, setModels, backendStatus } = useAppStore()
  const [selectedModel, setSelectedModel] = useState<string>()
  const [prompt, setPrompt] = useState('')
  const [response, setResponse] = useState('')
  const [loading, setLoading] = useState(false)
  const [maxTokens, setMaxTokens] = useState(1024)
  const [temperature, setTemperature] = useState(0.7)
  const [currentBackend, setCurrentBackend] = useState<string>('huggingface')
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [ollamaModels, setOllamaModels] = useState<{ id: string; name: string }[]>([])

  useEffect(() => {
    loadBackends()
    loadModels()
  }, [backendStatus])

  const loadModels = async () => {
    try {
      const list = await getModelList()
      setModels(list)
    } catch (error) {
      console.error('Failed to load models:', error)
    }
  }

  const loadBackends = async () => {
    try {
      const data = await getBackends()
      setCurrentBackend(data.current)
      setBackends(data.backends)

      if (data.current === 'ollama') {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(ollamaStatus.models.map((m: { name: string; size: number }) => ({
          id: m.name,
          name: m.name
        })))
      }
    } catch (error) {
      console.error('Failed to load backends:', error)
    }
  }

  const handleBackendChange = async (backend: string) => {
    try {
      await switchBackend(backend)
      setCurrentBackend(backend)
      setSelectedModel(undefined)
      setModelsForBackend(backend)
      message.success(`已切换到 ${backend === 'ollama' ? 'Ollama' : 'HuggingFace'} 后端`)
    } catch (error) {
      message.error('切换失败')
    }
  }

  const setModelsForBackend = async (backend: string) => {
    if (backend === 'ollama') {
      try {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(ollamaStatus.models.map((m: { name: string }) => ({
          id: m.name,
          name: m.name
        })))
      } catch {
        setOllamaModels([])
      }
    }
  }

  const modelOptions = currentBackend === 'ollama' 
    ? ollamaModels.map(m => ({ value: m.id, label: m.name }))
    : models
        .filter(m => m.type === 'base' || m.type === 'merged')
        .map(m => ({
          value: m.id,
          label: `${m.name} ${m.quantized ? `(INT${m.quantized})` : ''}`
        }))

  const currentBackendInfo = backends.find(b => b.id === currentBackend)
  const isBackendAvailable = currentBackendInfo?.available ?? true

  const handleSend = async () => {
    if (!selectedModel || !prompt.trim()) return

    setLoading(true)
    setResponse('')

    try {
      await streamInference(
        {
          modelId: selectedModel,
          prompt: prompt,
          maxTokens: maxTokens,
          temperature: temperature,
          backend: currentBackend
        },
        (text: string) => {
          setResponse(prev => prev + text)
        }
      )
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '推理失败'
      setResponse(`错误: ${errorMsg}`)
    } finally {
      setLoading(false)
    }
  }

  const handleClear = () => {
    setPrompt('')
    setResponse('')
  }

  const getBackendBadge = () => {
    if (currentBackend === 'ollama') {
      return <Badge status={isBackendAvailable ? 'success' : 'error'} text={isBackendAvailable ? 'Ollama 已连接' : 'Ollama 未运行'} />
    }
    return <Badge status="success" text="本地模型" />
  }

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">推理测试</div>

        {backendStatus !== 'connected' ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            后端服务未连接，请先启动应用
          </div>
        ) : (
          <Row gutter={24}>
            <Col xs={24} lg={16}>
              <Card
                title="对话"
                variant="borderless"
                extra={
                  <Space>
                    <Select
                      value={currentBackend}
                      onChange={handleBackendChange}
                      style={{ width: 160 }}
                      suffixIcon={<SwapOutlined />}
                      options={backends.map(b => ({
                        value: b.id,
                        label: b.available ? b.name : `${b.name} (不可用)`,
                        disabled: !b.available
                      }))}
                    />
                    <Select
                      placeholder={currentBackend === 'ollama' ? "选择 Ollama 模型" : "选择模型"}
                      value={selectedModel}
                      onChange={setSelectedModel}
                      style={{ width: 250 }}
                      options={modelOptions}
                      disabled={loading}
                      loading={modelOptions.length === 0}
                    />
                  </Space>
                }
              >
                {!isBackendAvailable && currentBackend === 'ollama' && (
                  <Alert
                    type="warning"
                    message="Ollama 未运行"
                    description="请确保 Ollama 已启动，然后刷新页面"
                    showIcon
                    style={{ marginBottom: 16 }}
                    action={
                      <Button size="small" onClick={loadBackends}>刷新</Button>
                    }
                  />
                )}

                <div style={{ 
                  minHeight: 400, 
                  maxHeight: 500, 
                  overflowY: 'auto',
                  background: '#fafafa',
                  padding: 16,
                  borderRadius: 8,
                  marginBottom: 16,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace'
                }}>
                  {response || '模型输出将显示在这里...'}
                  {loading && <LoadingOutlined style={{ marginLeft: 8 }} spin />}
                </div>

                <TextArea
                  placeholder="输入你的问题..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onPressEnter={(e) => {
                    if (!e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  rows={4}
                  disabled={loading || !selectedModel}
                  style={{ marginBottom: 16 }}
                />

                <Space>
                  <Button 
                    type="primary" 
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    loading={loading}
                    disabled={!selectedModel || !prompt.trim()}
                  >
                    发送
                  </Button>
                  <Button 
                    icon={<ClearOutlined />}
                    onClick={handleClear}
                    disabled={loading}
                  >
                    清空
                  </Button>
                  <Tag color="blue">Shift+Enter 换行</Tag>
                  {getBackendBadge()}
                </Space>
              </Card>
            </Col>

            <Col xs={24} lg={8}>
              <Card title="推理参数" variant="borderless">
                <div style={{ marginBottom: 24 }}>
                  <div style={{ marginBottom: 8 }}>
                    <span>最大Token数: </span>
                    <Tag color="blue">{maxTokens}</Tag>
                  </div>
                  <Slider
                    min={128}
                    max={4096}
                    step={128}
                    value={maxTokens}
                    onChange={setMaxTokens}
                    disabled={loading}
                  />
                </div>

                <div style={{ marginBottom: 24 }}>
                  <div style={{ marginBottom: 8 }}>
                    <span>Temperature (创造性): </span>
                    <Tag color="blue">{temperature}</Tag>
                  </div>
                  <Slider
                    min={0.1}
                    max={2.0}
                    step={0.1}
                    value={temperature}
                    onChange={setTemperature}
                    disabled={loading}
                    marks={{
                      0.1: '精确',
                      0.7: '平衡',
                      2.0: '创意'
                    }}
                  />
                </div>

                <Divider>参数说明</Divider>
                <ul style={{ paddingLeft: 20, color: '#666', fontSize: 13 }}>
                  <li><b>Max Tokens:</b> 限制回复的最大长度</li>
                  <li><b>Temperature:</b> 越高越有创意，越低越精确</li>
                  <li><b>建议:</b> 问答用 0.3-0.5，创作用 0.7-1.0</li>
                </ul>
              </Card>

              <Card
                title="推理后端"
                variant="borderless"
                styles={{ body: { marginTop: 16 } }}
                size="small"
              >
                {backends.map(backend => (
                  <div 
                    key={backend.id}
                    style={{ 
                      padding: '8px 12px', 
                      marginBottom: 8, 
                      borderRadius: 6,
                      background: currentBackend === backend.id ? '#e6f7ff' : '#fafafa',
                      border: currentBackend === backend.id ? '1px solid #91d5ff' : '1px solid #f0f0f0',
                      cursor: backend.available ? 'pointer' : 'not-allowed',
                      opacity: backend.available ? 1 : 0.6
                    }}
                    onClick={() => backend.available && handleBackendChange(backend.id)}
                  >
                    <div style={{ fontWeight: currentBackend === backend.id ? 600 : 400 }}>
                      {backend.name}
                    </div>
                    <div style={{ fontSize: 12, color: '#999' }}>
                      {backend.description}
                    </div>
                  </div>
                ))}
              </Card>

              <Card title="使用提示" variant="borderless" styles={{ body: { marginTop: 16 } }}>
                <ul style={{ paddingLeft: 20, color: '#666', fontSize: 13 }}>
                  <li>支持 HuggingFace 本地模型推理</li>
                  <li>也支持 Ollama 部署的模型</li>
                  <li>训练完成后可在推理测试中验证效果</li>
                </ul>
              </Card>
            </Col>
          </Row>
        )}
      </div>
    </div>
  )
}
