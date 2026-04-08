/**
 * 上下文理解面板组件
 * 功能：
 * - 代词消解可视化
 * - 省略补全展示
 * - 对话摘要生成
 * - 上下文窗口管理
 */
import { useState, useEffect } from 'react'
import {
  Card, Tabs, Typography, Space, Button, Input, List, Tag,
  Spin, message, Progress, Statistic, Row, Col, Badge,
  Tooltip, Switch, Select, Alert, Collapse, Descriptions
} from 'antd'
import {
  BulbOutlined, ExpandOutlined,
  SwapOutlined, FileTextOutlined, DashboardOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined, CopyOutlined
} from '@ant-design/icons'
import axios from 'axios'
import { API_BASE_URL } from '../services/api'

const { Text, Paragraph } = Typography
const { TextArea } = Input
const { Panel } = Collapse
const { Option } = Select

interface PronounResolution {
  pronoun: string
  type: string
  resolved_to: string | null
  confidence: number
  position: [number, number]
}

interface OmissionCompletion {
  original: string
  completed: string
  confidence: number
}

interface Entity {
  text: string
  type: string
  importance: number
}

interface WindowStats {
  total_tokens: number
  max_tokens: number
  utilization: number
  overflow_count: number
}

interface ContextMessage {
  role: string
  content: string
  importance: number
}

interface ProcessResult {
  success: boolean
  original_text: string
  resolved_text: string
  pronoun_resolutions: PronounResolution[]
  omission_completion: OmissionCompletion
  entities: Entity[]
}

interface EnhanceResult {
  success: boolean
  enhanced_query: string
  context_messages: ContextMessage[]
  summary: string | null
  entities: Entity[]
  pronoun_resolutions: PronounResolution[]
  window_stats: WindowStats
}

interface SummaryResult {
  success: boolean
  summary_text: string
  key_points: string[]
  entities_mentioned: string[]
  topics: string[]
  token_count: number
}

interface WindowResult {
  success: boolean
  window_messages: ContextMessage[]
  total_tokens: number
  max_tokens: number
  utilization: number
  overflow_count: number
  summary: string | null
}

interface ContextPanelProps {
  messages?: Array<{ role: string; content: string }>
  onContextEnhanced?: (result: EnhanceResult) => void
}

export default function ContextPanel({ messages = [], onContextEnhanced }: ContextPanelProps) {
  const [activeTab, setActiveTab] = useState('process')
  const [loading, setLoading] = useState(false)
  
  const [inputText, setInputText] = useState('')
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null)
  
  const [enhanceQuery, setEnhanceQuery] = useState('')
  const [enhanceResult, setEnhanceResult] = useState<EnhanceResult | null>(null)
  
  const [summaryResult, setSummaryResult] = useState<SummaryResult | null>(null)
  const [useLlm, setUseLlm] = useState(false)
  
  const [windowResult, setWindowResult] = useState<WindowResult | null>(null)
  const [maxTokens, setMaxTokens] = useState(4096)
  const [keepRecent, setKeepRecent] = useState(3)
  
  const [engineStatus, setEngineStatus] = useState<any>(null)

  useEffect(() => {
    fetchEngineStatus()
  }, [])

  const fetchEngineStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/context/understanding/status`)
      setEngineStatus(response.data.status)
    } catch (error) {
      console.error('获取引擎状态失败:', error)
    }
  }

  const processMessage = async () => {
    if (!inputText.trim()) {
      message.warning('请输入要处理的文本')
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE_URL}/context/understanding/process`, {
        message: inputText,
        role: 'user',
        history: messages.map((m, i) => ({
          id: `msg_${i}`,
          role: m.role,
          content: m.content
        }))
      })
      setProcessResult(response.data)
    } catch (error) {
      console.error('处理消息失败:', error)
      message.error('处理消息失败')
    } finally {
      setLoading(false)
    }
  }

  const enhanceContext = async () => {
    if (!enhanceQuery.trim()) {
      message.warning('请输入查询内容')
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE_URL}/context/understanding/enhance`, {
        query: enhanceQuery,
        messages: messages.map((m, i) => ({
          id: `msg_${i}`,
          role: m.role,
          content: m.content
        })),
        max_context_tokens: maxTokens
      })
      setEnhanceResult(response.data)
      onContextEnhanced?.(response.data)
    } catch (error) {
      console.error('增强上下文失败:', error)
      message.error('增强上下文失败')
    } finally {
      setLoading(false)
    }
  }

  const generateSummary = async () => {
    if (messages.length === 0) {
      message.warning('没有对话消息可摘要')
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE_URL}/context/understanding/summarize`, {
        messages: messages.map((m, i) => ({
          id: `msg_${i}`,
          role: m.role,
          content: m.content
        })),
        use_llm: useLlm
      })
      setSummaryResult(response.data)
    } catch (error) {
      console.error('生成摘要失败:', error)
      message.error('生成摘要失败')
    } finally {
      setLoading(false)
    }
  }

  const manageWindow = async () => {
    if (messages.length === 0) {
      message.warning('没有消息可管理')
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE_URL}/context/understanding/window`, {
        messages: messages.map((m, i) => ({
          id: `msg_${i}`,
          role: m.role,
          content: m.content
        })),
        max_tokens: maxTokens,
        keep_recent: keepRecent
      })
      setWindowResult(response.data)
    } catch (error) {
      console.error('管理窗口失败:', error)
      message.error('管理窗口失败')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制到剪贴板')
  }

  const renderProcessTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card title="输入文本" size="small">
        <TextArea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="输入要处理的文本，例如：'他说的对吗？' 或 '是'"
          rows={3}
        />
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={processMessage}
          loading={loading}
          style={{ marginTop: 12 }}
        >
          处理消息
        </Button>
      </Card>

      {processResult && (
        <Card title="处理结果" size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>原文：</Text>
              <Text>{processResult.original_text}</Text>
            </div>

            {processResult.resolved_text !== processResult.original_text && (
              <div>
                <Text strong>消解后：</Text>
                <Text type="success">{processResult.resolved_text}</Text>
                <Button
                  type="link"
                  icon={<CopyOutlined />}
                  onClick={() => copyToClipboard(processResult.resolved_text)}
                  size="small"
                />
              </div>
            )}

            {processResult.pronoun_resolutions.length > 0 && (
              <div>
                <Text strong>代词消解：</Text>
                <List
                  size="small"
                  dataSource={processResult.pronoun_resolutions}
                  renderItem={(item) => (
                    <List.Item>
                      <Space>
                        <Tag color="blue">{item.pronoun}</Tag>
                        <SwapOutlined />
                        <Tag color={item.resolved_to ? 'green' : 'default'}>
                          {item.resolved_to || '未解析'}
                        </Tag>
                        <Progress
                          percent={Math.round(item.confidence * 100)}
                          size="small"
                          style={{ width: 80 }}
                          showInfo={false}
                        />
                      </Space>
                    </List.Item>
                  )}
                />
              </div>
            )}

            {processResult.omission_completion.confidence > 0.5 && (
              <div>
                <Text strong>省略补全：</Text>
                <Space>
                  <Text delete>{processResult.omission_completion.original}</Text>
                  <SwapOutlined />
                  <Text type="success">{processResult.omission_completion.completed}</Text>
                </Space>
                <Progress
                  percent={Math.round(processResult.omission_completion.confidence * 100)}
                  size="small"
                  style={{ width: 100, marginLeft: 8 }}
                  showInfo={false}
                />
              </div>
            )}

            {processResult.entities.length > 0 && (
              <div>
                <Text strong>识别实体：</Text>
                <Space wrap>
                  {processResult.entities.map((entity, idx) => (
                    <Tag key={idx} color="purple">
                      {entity.text} ({entity.type})
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        </Card>
      )}
    </Space>
  )

  const renderEnhanceTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card title="上下文增强" size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          <TextArea
            value={enhanceQuery}
            onChange={(e) => setEnhanceQuery(e.target.value)}
            placeholder="输入查询，系统将自动进行代词消解、省略补全和窗口管理"
            rows={2}
          />
          <Space>
            <Text>最大Token：</Text>
            <Select value={maxTokens} onChange={setMaxTokens} style={{ width: 120 }}>
              <Option value={2048}>2048</Option>
              <Option value={4096}>4096</Option>
              <Option value={8192}>8192</Option>
              <Option value={16384}>16384</Option>
            </Select>
          </Space>
          <Button
            type="primary"
            icon={<ExpandOutlined />}
            onClick={enhanceContext}
            loading={loading}
          >
            增强上下文
          </Button>
        </Space>
      </Card>

      {enhanceResult && (
        <Card title="增强结果" size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>增强查询：</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {enhanceResult.enhanced_query}
              </Paragraph>
            </div>

            {enhanceResult.summary && (
              <div>
                <Text strong>历史摘要：</Text>
                <Paragraph ellipsis={{ rows: 3, expandable: true }}>
                  {enhanceResult.summary}
                </Paragraph>
              </div>
            )}

            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title="Token使用"
                  value={enhanceResult.window_stats.total_tokens}
                  suffix={`/ ${enhanceResult.window_stats.max_tokens}`}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="利用率"
                  value={Math.round(enhanceResult.window_stats.utilization * 100)}
                  suffix="%"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="溢出消息"
                  value={enhanceResult.window_stats.overflow_count}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="上下文消息"
                  value={enhanceResult.context_messages.length}
                />
              </Col>
            </Row>

            {enhanceResult.entities.length > 0 && (
              <div>
                <Text strong>识别实体：</Text>
                <Space wrap>
                  {enhanceResult.entities.map((entity, idx) => (
                    <Tag key={idx} color="purple">{entity.text}</Tag>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        </Card>
      )}
    </Space>
  )

  const renderSummaryTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card title="对话摘要" size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Text>使用LLM：</Text>
            <Switch checked={useLlm} onChange={setUseLlm} />
            <Tooltip title="开启后使用大语言模型生成更精确的摘要">
              <QuestionCircleOutlined />
            </Tooltip>
          </Space>
          <Button
            type="primary"
            icon={<FileTextOutlined />}
            onClick={generateSummary}
            loading={loading}
            disabled={messages.length === 0}
          >
            生成摘要
          </Button>
          {messages.length === 0 && (
            <Alert type="info" message="当前没有对话消息" />
          )}
        </Space>
      </Card>

      {summaryResult && (
        <Card title="摘要结果" size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>摘要内容：</Text>
              <Paragraph copyable>{summaryResult.summary_text || '无摘要'}</Paragraph>
            </div>

            {summaryResult.key_points.length > 0 && (
              <div>
                <Text strong>关键点：</Text>
                <List
                  size="small"
                  dataSource={summaryResult.key_points}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </div>
            )}

            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="主题" value={summaryResult.topics.length} />
              </Col>
              <Col span={8}>
                <Statistic title="实体" value={summaryResult.entities_mentioned.length} />
              </Col>
              <Col span={8}>
                <Statistic title="Token数" value={summaryResult.token_count} />
              </Col>
            </Row>

            {summaryResult.topics.length > 0 && (
              <div>
                <Text strong>讨论主题：</Text>
                <Space wrap>
                  {summaryResult.topics.map((topic, idx) => (
                    <Tag key={idx} color="blue">{topic}</Tag>
                  ))}
                </Space>
              </div>
            )}

            {summaryResult.entities_mentioned.length > 0 && (
              <div>
                <Text strong>涉及实体：</Text>
                <Space wrap>
                  {summaryResult.entities_mentioned.map((entity, idx) => (
                    <Tag key={idx} color="green">{entity}</Tag>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        </Card>
      )}
    </Space>
  )

  const renderWindowTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card title="窗口管理" size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Row gutter={16}>
            <Col span={12}>
              <Space>
                <Text>最大Token：</Text>
                <Select value={maxTokens} onChange={setMaxTokens} style={{ width: 120 }}>
                  <Option value={2048}>2048</Option>
                  <Option value={4096}>4096</Option>
                  <Option value={8192}>8192</Option>
                  <Option value={16384}>16384</Option>
                </Select>
              </Space>
            </Col>
            <Col span={12}>
              <Space>
                <Text>保留最近：</Text>
                <Select value={keepRecent} onChange={setKeepRecent} style={{ width: 80 }}>
                  <Option value={1}>1条</Option>
                  <Option value={2}>2条</Option>
                  <Option value={3}>3条</Option>
                  <Option value={5}>5条</Option>
                  <Option value={10}>10条</Option>
                </Select>
              </Space>
            </Col>
          </Row>
          <Button
            type="primary"
            icon={<DashboardOutlined />}
            onClick={manageWindow}
            loading={loading}
            disabled={messages.length === 0}
          >
            管理窗口
          </Button>
        </Space>
      </Card>

      {windowResult && (
        <Card title="窗口状态" size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title="当前Token"
                  value={windowResult.total_tokens}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="最大Token"
                  value={windowResult.max_tokens}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="利用率"
                  value={Math.round(windowResult.utilization * 100)}
                  suffix="%"
                  valueStyle={{
                    color: windowResult.utilization > 0.9 ? '#cf1322' : '#3f8600'
                  }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="溢出消息"
                  value={windowResult.overflow_count}
                  valueStyle={{
                    color: windowResult.overflow_count > 0 ? '#fa8c16' : '#52c41a'
                  }}
                />
              </Col>
            </Row>

            <Progress
              percent={Math.round(windowResult.utilization * 100)}
              status={windowResult.utilization > 0.9 ? 'exception' : 'active'}
            />

            {windowResult.summary && (
              <div>
                <Text strong>溢出摘要：</Text>
                <Paragraph ellipsis={{ rows: 2, expandable: true }}>
                  {windowResult.summary}
                </Paragraph>
              </div>
            )}

            {windowResult.window_messages.length > 0 && (
              <div>
                <Text strong>窗口内消息 ({windowResult.window_messages.length}条)：</Text>
                <List
                  size="small"
                  dataSource={windowResult.window_messages}
                  renderItem={(msg) => (
                    <List.Item>
                      <Space>
                        <Tag color={msg.role === 'user' ? 'blue' : 'green'}>
                          {msg.role === 'user' ? '用户' : '助手'}
                        </Tag>
                        <Text ellipsis style={{ maxWidth: 300 }}>
                          {msg.content.substring(0, 50)}...
                        </Text>
                        <Progress
                          percent={Math.round(msg.importance * 100)}
                          size="small"
                          style={{ width: 60 }}
                          showInfo={false}
                        />
                      </Space>
                    </List.Item>
                  )}
                />
              </div>
            )}
          </Space>
        </Card>
      )}
    </Space>
  )

  const renderStatusTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      {engineStatus ? (
        <Card title="引擎状态" size="small">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="窗口管理器">
              最大Token: {engineStatus.window_manager?.max_tokens}, 
              预留Token: {engineStatus.window_manager?.reserved_tokens}
            </Descriptions.Item>
            <Descriptions.Item label="代词消解器">
              人称代词: {engineStatus.pronoun_resolver?.personal_pronouns}个, 
              指示代词: {engineStatus.pronoun_resolver?.demonstrative_pronouns}个,
              实体模式: {engineStatus.pronoun_resolver?.entity_patterns}个
            </Descriptions.Item>
            <Descriptions.Item label="省略补全器">
              省略模式: {engineStatus.omission_completer?.patterns}个,
              问题模式: {engineStatus.omission_completer?.question_patterns}个
            </Descriptions.Item>
            <Descriptions.Item label="摘要生成器">
              关键词权重: {engineStatus.summarizer?.keyword_weights}个,
              LLM启用: {engineStatus.summarizer?.llm_enabled ? '是' : '否'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      ) : (
        <Spin />
      )}

      <Card title="使用说明" size="small">
        <Collapse ghost>
          <Panel header="代词消解" key="1">
            <Paragraph>
              自动识别文本中的代词（他、她、它、这、那等），
              并根据上下文解析其指向的实体。
            </Paragraph>
          </Panel>
          <Panel header="省略补全" key="2">
            <Paragraph>
              检测省略句（如"是"、"对"、"好"等单字回答），
              根据对话历史补全省略的内容。
            </Paragraph>
          </Panel>
          <Panel header="对话摘要" key="3">
            <Paragraph>
              对长对话自动生成摘要，提取关键点、主题和实体，
              支持基于规则和LLM两种方式。
            </Paragraph>
          </Panel>
          <Panel header="窗口管理" key="4">
            <Paragraph>
              管理上下文窗口的Token预算，采用滑动窗口策略，
              重要信息优先保留，溢出内容自动摘要。
            </Paragraph>
          </Panel>
        </Collapse>
      </Card>
    </Space>
  )

  return (
    <Card
      title={
        <Space>
          <BulbOutlined />
          <span>上下文理解</span>
          {engineStatus && (
            <Badge status="success" text="引擎就绪" />
          )}
        </Space>
      }
      extra={
        <Button size="small" onClick={fetchEngineStatus}>
          刷新状态
        </Button>
      }
    >
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <Tabs.TabPane tab="消息处理" key="process">
          {renderProcessTab()}
        </Tabs.TabPane>
        <Tabs.TabPane tab="上下文增强" key="enhance">
          {renderEnhanceTab()}
        </Tabs.TabPane>
        <Tabs.TabPane tab="对话摘要" key="summary">
          {renderSummaryTab()}
        </Tabs.TabPane>
        <Tabs.TabPane tab="窗口管理" key="window">
          {renderWindowTab()}
        </Tabs.TabPane>
        <Tabs.TabPane tab="状态信息" key="status">
          {renderStatusTab()}
        </Tabs.TabPane>
      </Tabs>
    </Card>
  )
}
