import { useEffect, useState } from 'react'
import {
  App,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Form,
  InputNumber,
  Modal,
  Progress,
  Row,
  Slider,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import {
  BankOutlined,
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  SettingOutlined,
  SyncOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { API_BASE_URL } from '../services/api'

const { Title } = Typography

interface SkillMemoryConfig {
  skill_name: string
  memory_enabled: boolean
  context_injection: boolean
  result_storage: boolean
  preference_learning: boolean
  max_memories: number
  relevance_threshold: number
}

interface UserPreference {
  key: string
  value: string
  learned_at: string
  confidence: number
}

interface OperationHistory {
  skill_name: string
  timestamp: string
  success: boolean
  duration: number
  params: Record<string, unknown>
}

export default function SkillMemory() {
  const { message } = App.useApp()
  const [configs, setConfigs] = useState<SkillMemoryConfig[]>([])
  const [preferences, setPreferences] = useState<UserPreference[]>([])
  const [history, setHistory] = useState<OperationHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingConfig, setEditingConfig] = useState<SkillMemoryConfig | null>(null)
  const [form] = Form.useForm()

  useEffect(() => {
    void fetchConfigs()
    void fetchPreferences()
    void fetchHistory()
  }, [])

  const fetchConfigs = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/configs`)
      if (!response.ok) {
        message.error('加载技能配置失败')
        return
      }
      const data = await response.json()
      setConfigs(data.configs || [])
    } catch (error) {
      console.error('Failed to fetch configs:', error)
      message.error('加载技能配置失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchPreferences = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/preferences`)
      if (!response.ok) {
        message.error('加载用户偏好失败')
        return
      }
      const data = await response.json()
      setPreferences(data.preferences || [])
    } catch (error) {
      console.error('Failed to fetch preferences:', error)
      message.error('加载用户偏好失败')
    }
  }

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/history`)
      if (!response.ok) {
        message.error('加载操作历史失败')
        return
      }
      const data = await response.json()
      setHistory(data.history || [])
    } catch (error) {
      console.error('Failed to fetch history:', error)
      message.error('加载操作历史失败')
    }
  }

  const handleUpdateConfig = async (values: Partial<SkillMemoryConfig>) => {
    if (!editingConfig) return

    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/configs/${editingConfig.skill_name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })

      if (!response.ok) {
        message.error('更新配置失败')
        return
      }

      await fetchConfigs()
      setEditModalVisible(false)
      message.success('配置已更新')
    } catch (error) {
      console.error('Failed to update config:', error)
      message.error('更新配置失败')
    }
  }

  const handleDeletePreference = async (key: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/preferences/${key}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        message.error('删除偏好失败')
        return
      }

      await fetchPreferences()
      message.success('偏好已删除')
    } catch (error) {
      console.error('Failed to delete preference:', error)
      message.error('删除偏好失败')
    }
  }

  const handleClearHistory = async () => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空全部操作历史吗？',
      onOk: async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/skills/memory/history`, {
            method: 'DELETE',
          })

          if (!response.ok) {
            message.error('清空历史失败')
            return
          }

          setHistory([])
          message.success('历史已清空')
        } catch (error) {
          console.error('Failed to clear history:', error)
          message.error('清空历史失败')
        }
      },
    })
  }

  const configColumns: ColumnsType<SkillMemoryConfig> = [
    {
      title: '技能名称',
      dataIndex: 'skill_name',
      key: 'skill_name',
      render: (name: string) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: '记忆启用',
      dataIndex: 'memory_enabled',
      key: 'memory_enabled',
      render: (enabled: boolean) => <Badge status={enabled ? 'success' : 'default'} text={enabled ? '启用' : '禁用'} />,
    },
    {
      title: '上下文注入',
      dataIndex: 'context_injection',
      key: 'context_injection',
      render: (enabled: boolean) => <Switch checked={enabled} size="small" disabled />,
    },
    {
      title: '结果存储',
      dataIndex: 'result_storage',
      key: 'result_storage',
      render: (enabled: boolean) => <Switch checked={enabled} size="small" disabled />,
    },
    {
      title: '偏好学习',
      dataIndex: 'preference_learning',
      key: 'preference_learning',
      render: (enabled: boolean) => <Switch checked={enabled} size="small" disabled />,
    },
    {
      title: '最大记忆数',
      dataIndex: 'max_memories',
      key: 'max_memories',
    },
    {
      title: '相关性阈值',
      dataIndex: 'relevance_threshold',
      key: 'relevance_threshold',
      render: (value: number) => `${(value * 100).toFixed(0)}%`,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: SkillMemoryConfig) => (
        <Button
          icon={<EditOutlined />}
          data-testid={`skill-config-edit-${record.skill_name}`}
          onClick={() => {
            setEditingConfig(record)
            form.setFieldsValue(record)
            setEditModalVisible(true)
          }}
        />
      ),
    },
  ]

  const preferenceColumns: ColumnsType<UserPreference> = [
    { title: '偏好键', dataIndex: 'key', key: 'key' },
    { title: '偏好值', dataIndex: 'value', key: 'value', ellipsis: true },
    {
      title: '学习时间',
      dataIndex: 'learned_at',
      key: 'learned_at',
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (value: number) => <Progress percent={value * 100} size="small" status={value > 0.8 ? 'success' : 'normal'} />,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: UserPreference) => (
        <Button icon={<DeleteOutlined />} danger onClick={() => handleDeletePreference(record.key)} />
      ),
    },
  ]

  const historyColumns: ColumnsType<OperationHistory> = [
    {
      title: '技能',
      dataIndex: 'skill_name',
      key: 'skill_name',
      render: (name: string) => <Tag>{name}</Tag>,
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: '状态',
      dataIndex: 'success',
      key: 'success',
      render: (success: boolean) => <Badge status={success ? 'success' : 'error'} text={success ? '成功' : '失败'} />,
    },
    {
      title: '耗时',
      dataIndex: 'duration',
      key: 'duration',
      render: (value: number) => `${value.toFixed(2)}s`,
    },
  ]

  const successRate = history.length > 0 ? (history.filter((item) => item.success).length / history.length) * 100 : 0

  const tabItems = [
    {
      key: 'configs',
      label: (
        <span>
          <SettingOutlined /> 技能配置
        </span>
      ),
      children: (
        <Card>
          <Table columns={configColumns} dataSource={configs} rowKey="skill_name" loading={loading} pagination={{ pageSize: 10 }} />
        </Card>
      ),
    },
    {
      key: 'preferences',
      label: (
        <span data-testid="skill-tab-preferences">
          <TrophyOutlined /> 用户偏好
        </span>
      ),
      children: (
        <Card>
          <Space style={{ marginBottom: 16 }}>
            <Button icon={<SyncOutlined />} onClick={() => void fetchPreferences()}>
              刷新
            </Button>
          </Space>
          {preferences.length > 0 ? (
            <Table columns={preferenceColumns} dataSource={preferences} rowKey="key" pagination={{ pageSize: 10 }} />
          ) : (
            <Empty description="暂无用户偏好" />
          )}
        </Card>
      ),
    },
    {
      key: 'history',
      label: (
        <span data-testid="skill-tab-history">
          <HistoryOutlined /> 操作历史
        </span>
      ),
      children: (
        <Card>
          <Space style={{ marginBottom: 16 }}>
            <Button icon={<SyncOutlined />} onClick={() => void fetchHistory()}>
              刷新
            </Button>
            <Button icon={<DeleteOutlined />} danger onClick={() => void handleClearHistory()}>
              清除历史
            </Button>
          </Space>
          <Table
            columns={historyColumns}
            dataSource={history}
            rowKey={(record) => `${record.skill_name}-${record.timestamp}-${record.duration}`}
            pagination={{ pageSize: 20 }}
          />
        </Card>
      ),
    },
  ]

  return (
    <div className="skill-memory-page" style={{ padding: 24 }}>
      <Title level={2}>
        <BankOutlined style={{ marginRight: 8 }} />
        记忆-技能配置
      </Title>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="已配置技能" value={configs.length} prefix={<SettingOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="用户偏好" value={preferences.length} prefix={<TrophyOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="操作历史" value={history.length} prefix={<HistoryOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="成功率"
              value={successRate.toFixed(1)}
              suffix="%"
              valueStyle={{ color: successRate > 80 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="configs" items={tabItems} />

      <Modal title="编辑技能配置" open={editModalVisible} onOk={() => form.submit()} onCancel={() => setEditModalVisible(false)}>
        <Form form={form} onFinish={handleUpdateConfig} layout="vertical">
          <Form.Item name="memory_enabled" label="启用记忆" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="context_injection" label="上下文注入" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="result_storage" label="结果存储" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="preference_learning" label="偏好学习" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="max_memories" label="最大记忆数">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="relevance_threshold" label="相关性阈值">
            <Slider min={0} max={1} step={0.1} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
