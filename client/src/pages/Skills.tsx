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
  App,
  Typography,
  Descriptions,
  Empty,
  Tooltip,
  Badge,
  Divider,
  Row,
  Col,
  Statistic,
} from 'antd'
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  CodeOutlined,
  FileOutlined,
  CloudOutlined,
  DatabaseOutlined,
  SettingOutlined,
  ToolOutlined,
  ApiOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { API_BASE_URL } from '../services/api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface SkillParameter {
  name: string
  type: string
  description: string
  required: boolean
  default?: any
}

interface Skill {
  name: string
  description: string
  category: string
  version: string
  tags: string[]
  parameters: SkillParameter[]
  priority: string
  enabled: boolean
}

interface ExecutionResult {
  execution_id: string
  skill_name: string
  status: string
  result?: any
  error?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
}

interface Stats {
  total_skills: number
  total_executions: number
  categories: Record<string, number>
  tags: Record<string, number>
}

const categoryIcons: Record<string, React.ReactNode> = {
  file: <FileOutlined />,
  network: <CloudOutlined />,
  data: <DatabaseOutlined />,
  code: <CodeOutlined />,
  system: <SettingOutlined />,
  utility: <ToolOutlined />,
  ai: <ApiOutlined />,
  custom: <AppstoreOutlined />,
}

const categoryColors: Record<string, string> = {
  file: 'blue',
  network: 'green',
  data: 'orange',
  code: 'purple',
  system: 'red',
  utility: 'cyan',
  ai: 'magenta',
  custom: 'default',
}

export default function Skills() {
  const { message: appMessage } = App.useApp()
  const [skills, setSkills] = useState<Skill[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [executeModalOpen, setExecuteModalOpen] = useState(false)
  const [resultModalOpen, setResultModalOpen] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [executing, setExecuting] = useState(false)
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null)
  const [form] = Form.useForm()

  useEffect(() => {
    loadSkills()
    loadStats()
  }, [])

  const loadSkills = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills`)
      if (response.ok) {
        const data = await response.json()
        setSkills(data.skills || [])
      }
    } catch (error) {
      console.error('Failed to load skills:', error)
      appMessage.error('加载技能列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/stats`)
      if (response.ok) {
        const data = await response.json()
        setStats(data)
      }
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleScan = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/scan`, {
        method: 'POST',
      })
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          appMessage.success(`扫描完成，发现 ${data.discovered} 个技能，注册 ${data.registered?.length || 0} 个`)
          loadSkills()
          loadStats()
        } else {
          appMessage.error(data.error || '扫描失败')
        }
      }
    } catch (error) {
      appMessage.error('扫描技能失败')
    }
  }

  const handleExecute = async (values: any) => {
    if (!selectedSkill) return

    setExecuting(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_name: selectedSkill.name,
          parameters: values.parameters ? JSON.parse(values.parameters) : {},
          priority: values.priority || 'normal',
        }),
      })

      if (response.ok) {
        const data = await response.json()
        setExecutionResult(data)
        setResultModalOpen(true)
        setExecuteModalOpen(false)
        form.resetFields()
        
        if (data.status === 'completed') {
          appMessage.success('技能执行成功')
        } else {
          appMessage.warning(`技能执行状态: ${data.status}`)
        }
      } else {
        const error = await response.json()
        appMessage.error(error.detail || '执行失败')
      }
    } catch (error) {
      appMessage.error('执行技能失败')
    } finally {
      setExecuting(false)
    }
  }

  const showDetail = (skill: Skill) => {
    setSelectedSkill(skill)
    setDetailModalOpen(true)
  }

  const showExecute = (skill: Skill) => {
    setSelectedSkill(skill)
    const defaultParams: Record<string, any> = {}
    skill.parameters.forEach(p => {
      if (p.default !== undefined) {
        defaultParams[p.name] = p.default
      }
    })
    form.setFieldsValue({
      parameters: Object.keys(defaultParams).length > 0 ? JSON.stringify(defaultParams, null, 2) : '{}',
      priority: 'normal',
    })
    setExecuteModalOpen(true)
  }

  const filteredSkills = skills.filter(skill => {
    const matchSearch = !searchText || 
      skill.name.toLowerCase().includes(searchText.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchText.toLowerCase()) ||
      skill.tags.some(t => t.toLowerCase().includes(searchText.toLowerCase()))
    
    const matchCategory = !categoryFilter || skill.category === categoryFilter
    
    return matchSearch && matchCategory
  })

  const columns: ColumnsType<Skill> = [
    {
      title: '技能名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, record: Skill) => (
        <Space>
          {categoryIcons[record.category] || <ToolOutlined />}
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (category: string) => (
        <Tag color={categoryColors[category] || 'default'}>
          {category}
        </Tag>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 150,
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {tags.slice(0, 3).map(tag => (
            <Tag key={tag} style={{ margin: 0 }}>{tag}</Tag>
          ))}
          {tags.length > 3 && <Tag>+{tags.length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '参数',
      dataIndex: 'parameters',
      key: 'parameters',
      width: 80,
      render: (params: SkillParameter[]) => (
        <Badge count={params.length} showZero style={{ backgroundColor: '#1890ff' }}>
          <CodeOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Skill) => (
        <Space>
          <Tooltip title="执行">
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              size="small"
              onClick={() => showExecute(record)}
            />
          </Tooltip>
          <Tooltip title="详情">
            <Button
              icon={<InfoCircleOutlined />}
              size="small"
              onClick={() => showDetail(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <ThunderboltOutlined style={{ marginRight: 8 }} />
        技能管理
      </Title>
      <Paragraph type="secondary">
        管理和执行系统技能，支持文件操作、网络请求、代码执行等功能
      </Paragraph>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总技能数"
              value={stats?.total_skills || 0}
              prefix={<ToolOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总执行次数"
              value={stats?.total_executions || 0}
              prefix={<PlayCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="类别数"
              value={Object.keys(stats?.categories || {}).length}
              prefix={<AppstoreOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="标签数"
              value={Object.keys(stats?.tags || {}).length}
              prefix={<TagOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder="搜索技能..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <Select
            placeholder="筛选类别"
            value={categoryFilter}
            onChange={setCategoryFilter}
            style={{ width: 150 }}
            allowClear
            options={[
              { value: 'file', label: '文件' },
              { value: 'network', label: '网络' },
              { value: 'data', label: '数据' },
              { value: 'code', label: '代码' },
              { value: 'system', label: '系统' },
              { value: 'utility', label: '工具' },
              { value: 'ai', label: 'AI' },
              { value: 'custom', label: '自定义' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>
            刷新
          </Button>
          <Button type="primary" icon={<SearchOutlined />} onClick={handleScan}>
            扫描新技能
          </Button>
        </Space>

        <Table
          columns={columns}
          dataSource={filteredSkills}
          rowKey="name"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{
            emptyText: (
              <Empty
                description="暂无技能"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
        />
      </Card>

      <Modal
        title={`技能详情 - ${selectedSkill?.name}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            关闭
          </Button>,
          <Button
            key="execute"
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => {
              setDetailModalOpen(false)
              showExecute(selectedSkill!)
            }}
          >
            执行
          </Button>,
        ]}
        width={700}
      >
        {selectedSkill && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="名称">{selectedSkill.name}</Descriptions.Item>
              <Descriptions.Item label="版本">{selectedSkill.version}</Descriptions.Item>
              <Descriptions.Item label="类别">
                <Tag color={categoryColors[selectedSkill.category]}>
                  {selectedSkill.category}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">{selectedSkill.priority}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {selectedSkill.description}
              </Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                <Space wrap>
                  {selectedSkill.tags.map(tag => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
            </Descriptions>

            {selectedSkill.parameters.length > 0 && (
              <>
                <Divider>参数</Divider>
                <Table
                  dataSource={selectedSkill.parameters}
                  rowKey="name"
                  size="small"
                  pagination={false}
                  columns={[
                    {
                      title: '参数名',
                      dataIndex: 'name',
                      key: 'name',
                    },
                    {
                      title: '类型',
                      dataIndex: 'type',
                      key: 'type',
                      render: (type: string) => <Tag>{type}</Tag>,
                    },
                    {
                      title: '必填',
                      dataIndex: 'required',
                      key: 'required',
                      render: (required: boolean) => (
                        <Tag color={required ? 'red' : 'default'}>
                          {required ? '是' : '否'}
                        </Tag>
                      ),
                    },
                    {
                      title: '默认值',
                      dataIndex: 'default',
                      key: 'default',
                      render: (value: any) =>
                        value !== undefined ? JSON.stringify(value) : '-',
                    },
                    {
                      title: '描述',
                      dataIndex: 'description',
                      key: 'description',
                    },
                  ]}
                />
              </>
            )}
          </div>
        )}
      </Modal>

      <Modal
        title={`执行技能 - ${selectedSkill?.name}`}
        open={executeModalOpen}
        onCancel={() => {
          setExecuteModalOpen(false)
          form.resetFields()
        }}
        footer={null}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleExecute}>
          <Form.Item
            name="parameters"
            label="参数 (JSON 格式)"
            rules={[
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve()
                  try {
                    JSON.parse(value)
                    return Promise.resolve()
                  } catch {
                    return Promise.reject(new Error('请输入有效的 JSON'))
                  }
                },
              },
            ]}
          >
            <TextArea
              rows={8}
              placeholder='{"key": "value"}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item name="priority" label="优先级">
            <Select
              options={[
                { value: 'low', label: '低' },
                { value: 'normal', label: '普通' },
                { value: 'high', label: '高' },
                { value: 'critical', label: '紧急' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button onClick={() => setExecuteModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={executing}>
                执行
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="执行结果"
        open={resultModalOpen}
        onCancel={() => setResultModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setResultModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={700}
      >
        {executionResult && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="执行 ID">
                {executionResult.execution_id}
              </Descriptions.Item>
              <Descriptions.Item label="技能名称">
                {executionResult.skill_name}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag
                  color={
                    executionResult.status === 'completed'
                      ? 'green'
                      : executionResult.status === 'failed'
                      ? 'red'
                      : 'blue'
                  }
                >
                  {executionResult.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="耗时">
                {executionResult.duration_ms
                  ? `${executionResult.duration_ms.toFixed(2)} ms`
                  : '-'}
              </Descriptions.Item>
              {executionResult.started_at && (
                <Descriptions.Item label="开始时间">
                  {new Date(executionResult.started_at).toLocaleString()}
                </Descriptions.Item>
              )}
              {executionResult.completed_at && (
                <Descriptions.Item label="完成时间">
                  {new Date(executionResult.completed_at).toLocaleString()}
                </Descriptions.Item>
              )}
            </Descriptions>

            {executionResult.error && (
              <>
                <Divider>错误信息</Divider>
                <Text type="danger">{executionResult.error}</Text>
              </>
            )}

            {executionResult.result && (
              <>
                <Divider>返回结果</Divider>
                <pre
                  style={{
                    background: '#f5f5f5',
                    padding: 16,
                    borderRadius: 4,
                    maxHeight: 300,
                    overflow: 'auto',
                  }}
                >
                  {JSON.stringify(executionResult.result, null, 2)}
                </pre>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

function TagOutlined(props: any) {
  return <Tag {...props} />
}
