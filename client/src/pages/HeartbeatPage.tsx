import { useState, useEffect } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
  Badge,
  Switch,
  Typography,
  Row,
  Col,
  Statistic,
  Timeline,
  Tooltip,
} from 'antd'
import {
  HeartOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ScheduleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { apiClient } from '../services/api'

const { Title, Text } = Typography

interface Task {
  id: string
  name: string
  description: string
  schedule: string
  task_type: string
  enabled: boolean
  status?: string
  last_run?: string
  next_run?: string
}

interface TaskResult {
  task_id: string
  status: string
  result?: any
  error?: string
  duration_ms?: number
  executed_at: string
}

interface HeartbeatStatus {
  scheduler: {
    running: boolean
    total_tasks: number
    enabled_tasks: number
  }
  executor: {
    total_executed: number
    success_count: number
    failure_count: number
  }
}

export default function HeartbeatPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [results, setResults] = useState<TaskResult[]>([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<HeartbeatStatus | null>(null)
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [createForm] = Form.useForm()

  useEffect(() => {
    fetchHeartbeatData()
    const interval = setInterval(fetchHeartbeatData, 5000)
    return () => clearInterval(interval)
  }, [])

  const fetchHeartbeatData = async () => {
    setLoading(true)
    try {
      const [statusRes, tasksRes, resultsRes] = await Promise.all([
        apiClient.get('/heartbeat/status').catch(() => ({ data: null })),
        apiClient.get('/heartbeat/tasks').catch(() => ({ data: { tasks: [] } })),
        apiClient.get('/heartbeat/results?limit=20').catch(() => ({ data: { results: [] } })),
      ])
      
      setStatus(statusRes.data)
      setTasks(tasksRes.data?.tasks || [])
      setResults(resultsRes.data?.results || [])
    } catch (error) {
      console.error('Failed to fetch heartbeat data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateTask = async (values: any) => {
    try {
      const response = await apiClient.post('/heartbeat/tasks', {
        name: values.name,
        description: values.description || '',
        schedule: values.schedule,
        task_type: values.task_type || 'check',
        enabled: true,
        config: {},
      })
      
      if (response.data?.success) {
        message.success('任务创建成功')
        setCreateModalVisible(false)
        createForm.resetFields()
        fetchHeartbeatData()
      } else {
        message.error(response.data?.message || '创建失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建失败')
    }
  }

  const handleToggleTask = async (taskId: string, enabled: boolean) => {
    try {
      const endpoint = enabled ? '/heartbeat/tasks/{id}/enable' : '/heartbeat/tasks/{id}/disable'
      await apiClient.post(endpoint.replace('{id}', taskId))
      message.success(enabled ? '任务已启用' : '任务已禁用')
      fetchHeartbeatData()
    } catch (error) {
      message.error('操作失败')
    }
  }

  const handleDeleteTask = async (taskId: string) => {
    try {
      await apiClient.delete(`/heartbeat/tasks/${taskId}`)
      message.success('任务已删除')
      fetchHeartbeatData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleStartScheduler = async () => {
    try {
      const response = await apiClient.post('/heartbeat/start')
      if (response.data?.success) {
        message.success('调度器已启动')
        fetchHeartbeatData()
      } else {
        message.warning(response.data?.message || '启动失败')
      }
    } catch (error) {
      message.error('启动失败')
    }
  }

  const handleStopScheduler = async () => {
    try {
      const response = await apiClient.post('/heartbeat/stop')
      if (response.data?.success) {
        message.success('调度器已停止')
        fetchHeartbeatData()
      } else {
        message.warning(response.data?.message || '停止失败')
      }
    } catch (error) {
      message.error('停止失败')
    }
  }

  const getTaskTypeTag = (type: string) => {
    const typeMap: Record<string, { color: string; text: string }> = {
      check: { color: 'blue', text: '检查' },
      report: { color: 'green', text: '汇报' },
      reminder: { color: 'orange', text: '提醒' },
      custom: { color: 'purple', text: '自定义' },
    }
    const config = typeMap[type] || { color: 'default', text: type }
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { status: 'success' | 'processing' | 'error' | 'default'; text: string }> = {
      completed: { status: 'success', text: '已完成' },
      running: { status: 'processing', text: '运行中' },
      failed: { status: 'error', text: '失败' },
      pending: { status: 'default', text: '待执行' },
    }
    const config = statusMap[status] || { status: 'default', text: status }
    return <Badge status={config.status} text={config.text} />
  }

  const taskColumns: ColumnsType<Task> = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record) => (
        <Space>
          {name}
          {!record.enabled && <Tag color="default">已禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      render: (type: string) => getTaskTypeTag(type),
    },
    {
      title: '调度周期',
      dataIndex: 'schedule',
      key: 'schedule',
      render: (schedule: string) => (
        <Tooltip title="Cron 表达式或秒数">
          <Tag icon={<ClockCircleOutlined />}>{schedule}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => status ? getStatusBadge(status) : '-',
    },
    {
      title: '上次执行',
      dataIndex: 'last_run',
      key: 'last_run',
      render: (time: string) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space>
          <Tooltip title={record.enabled ? '禁用' : '启用'}>
            <Switch
              size="small"
              checked={record.enabled}
              onChange={(checked) => handleToggleTask(record.id, checked)}
            />
          </Tooltip>
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteTask(record.id)}
          />
        </Space>
      ),
    },
  ]

  const successRate = status?.executor 
    ? Math.round((status.executor.success_count / Math.max(status.executor.total_executed, 1)) * 100)
    : 0

  return (
    <div style={{ padding: '0 0 24px' }}>
      <Title level={4} style={{ marginBottom: 24 }}>
        <HeartOutlined style={{ marginRight: 8 }} />
        Heartbeat 任务调度
      </Title>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="调度器状态"
              value={status?.scheduler?.running ? '运行中' : '已停止'}
              prefix={status?.scheduler?.running ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              valueStyle={{ color: status?.scheduler?.running ? '#52c41a' : '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="任务总数"
              value={status?.scheduler?.total_tasks || 0}
              prefix={<ScheduleOutlined />}
              suffix={`/ ${status?.scheduler?.enabled_tasks || 0} 启用`}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="执行次数"
              value={status?.executor?.total_executed || 0}
              prefix={<SyncOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="成功率"
              value={successRate}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: successRate >= 90 ? '#52c41a' : successRate >= 70 ? '#faad14' : '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={16}>
          <Card
            title="任务列表"
            extra={
              <Space>
                {status?.scheduler?.running ? (
                  <Button
                    danger
                    icon={<PauseCircleOutlined />}
                    onClick={handleStopScheduler}
                  >
                    停止调度
                  </Button>
                ) : (
                  <Button
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    onClick={handleStartScheduler}
                  >
                    启动调度
                  </Button>
                )}
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => setCreateModalVisible(true)}
                >
                  创建任务
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={fetchHeartbeatData}
                  loading={loading}
                >
                  刷新
                </Button>
              </Space>
            }
          >
            <Table
              columns={taskColumns}
              dataSource={tasks}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
              size="small"
            />
          </Card>
        </Col>

        <Col span={8}>
          <Card title="执行历史">
            <Timeline
              items={results.slice(0, 10).map((result) => ({
                color: result.status === 'completed' ? 'green' : result.status === 'failed' ? 'red' : 'blue',
                children: (
                  <div>
                    <Text strong>{result.task_id}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {new Date(result.executed_at).toLocaleString()}
                    </Text>
                    <br />
                    {result.duration_ms && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        耗时: {result.duration_ms}ms
                      </Text>
                    )}
                    {result.error && (
                      <Text type="danger" style={{ fontSize: 12 }}>
                        {result.error}
                      </Text>
                    )}
                  </div>
                ),
              }))}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="创建任务"
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onOk={() => createForm.submit()}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateTask}
        >
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="例如: 定期检查 GPU 状态" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="任务描述（可选）" />
          </Form.Item>
          <Form.Item
            name="task_type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
          >
            <Select placeholder="选择任务类型">
              <Select.Option value="check">检查任务</Select.Option>
              <Select.Option value="report">汇报任务</Select.Option>
              <Select.Option value="reminder">提醒任务</Select.Option>
              <Select.Option value="custom">自定义任务</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="schedule"
            label="调度周期"
            rules={[{ required: true, message: '请输入调度周期' }]}
            extra="支持秒数（如 60）或 Cron 表达式（如 '0 * * * *'）"
          >
            <Input placeholder="例如: 60 或 '0 * * * *'" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
