import { useState, useEffect } from 'react'
import {
  Alert,
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
  Tabs,
  Badge,
  Descriptions,
  Typography,
  Row,
  Col,
  Statistic,
} from 'antd'
import {
  ApiOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  LinkOutlined,
  UserOutlined,
  MessageOutlined,
  ClusterOutlined,
  SafetyOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { API_BASE_URL, apiClient } from '../services/api'

const { Title } = Typography
const { TabPane } = Tabs
const gatewayWebSocketUrl = API_BASE_URL.replace(/^http/i, 'ws') + '/gateway/ws'

interface Device {
  id: string
  name: string
  type: string
  status: string
  permissions: string[]
  last_seen: string
  created_at: string
}

interface Binding {
  id: string
  name: string
  peer_id?: string
  guild_id?: string
  channel_id?: string
  agent_id: string
  priority: number
  enabled: boolean
}

interface Agent {
  id: string
  name: string
  status: string
  workspace_path: string
  created_at: string
}

export default function GatewayPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [bindings, setBindings] = useState<Binding[]>([])
  const [agents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(false)
  const [registerModalVisible, setRegisterModalVisible] = useState(false)
  const [bindingModalVisible, setBindingModalVisible] = useState(false)
  const [registerForm] = Form.useForm()
  const [bindingForm] = Form.useForm()
  const [gatewayStatus, setGatewayStatus] = useState<any>({})

  useEffect(() => {
    fetchGatewayData()
    const interval = setInterval(fetchGatewayData, 10000)
    return () => clearInterval(interval)
  }, [])

  const getApiErrorMessage = (error: any, fallback: string) =>
    error?.response?.data?.detail || error?.response?.data?.message || fallback

  const normalizeDevice = (device: any): Device => ({
    id: device.id || device.device_id,
    name: device.name || device.device_name || device.id || device.device_id,
    type: device.type || device.device_type || 'unknown',
    status: device.status || 'unknown',
    permissions: device.permissions || device.allowed_actions || [],
    last_seen: device.last_seen || device.last_active || '',
    created_at: device.created_at || '',
  })

  const normalizeBinding = (binding: any): Binding => ({
    id: binding.id,
    name: binding.name || binding.id,
    peer_id: binding.peer_id,
    guild_id: binding.guild_id,
    channel_id: binding.channel_id,
    agent_id: binding.agent_id,
    priority: binding.priority ?? 0,
    enabled: binding.enabled ?? true,
  })

  const fetchGatewayData = async () => {
    setLoading(true)
    try {
      const [statusRes, devicesRes, bindingsRes] = await Promise.all([
        apiClient.get('/gateway/status').catch(() => ({ data: {} })),
        apiClient.get('/gateway/devices').catch(() => ({ data: { devices: [] } })),
        apiClient.get('/gateway/bindings').catch(() => ({ data: { bindings: [] } })),
      ])
      
      setGatewayStatus(statusRes.data || {})
      setDevices((devicesRes.data?.devices || []).map(normalizeDevice))
      setBindings((bindingsRes.data?.bindings || []).map(normalizeBinding))
    } catch (error) {
      console.error('Failed to fetch gateway data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleRegisterDevice = async (values: any) => {
    try {
      const response = await apiClient.post('/gateway/devices/register', {
        device_name: values.name,
        device_type: values.type,
        metadata: {
          requested_permissions: values.permissions || [],
        },
      })
      
      if (response.data?.success) {
        message.success('设备注册成功')
        setRegisterModalVisible(false)
        registerForm.resetFields()
        fetchGatewayData()
      } else {
        message.error(response.data?.message || '注册失败')
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '注册失败'))
    }
  }

  const handleCreateBinding = async (values: any) => {
    try {
      const response = await apiClient.post('/gateway/bindings', {
        name: values.name,
        peer_id: values.peer_id,
        guild_id: values.guild_id,
        channel_id: values.channel_id,
        agent_id: values.agent_id,
        priority: values.priority || 0,
        enabled: true,
      })
      
      if (response.data?.success) {
        message.success('绑定规则创建成功')
        setBindingModalVisible(false)
        bindingForm.resetFields()
        fetchGatewayData()
      } else {
        message.error(response.data?.message || '创建失败')
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '创建失败'))
    }
  }

  const handleDeleteDevice = async (deviceId: string) => {
    try {
      const response = await apiClient.delete(`/gateway/devices/${deviceId}`)
      if (!response.data?.success) {
        message.error(response.data?.message || '删除失败')
        return
      }
      message.success('设备已删除')
      fetchGatewayData()
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '删除失败'))
    }
  }

  const handleDeleteBinding = async (bindingId: string) => {
    try {
      const response = await apiClient.delete(`/gateway/bindings/${bindingId}`)
      if (!response.data?.success) {
        message.error(response.data?.message || '删除失败')
        return
      }
      message.success('绑定规则已删除')
      fetchGatewayData()
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '删除失败'))
    }
  }

  const deviceColumns: ColumnsType<Device> = [
    {
      title: '设备 ID',
      dataIndex: 'id',
      key: 'id',
      width: 200,
      ellipsis: true,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Badge 
          status={status === 'active' ? 'success' : status === 'inactive' ? 'default' : 'warning'} 
          text={status === 'active' ? '在线' : status === 'inactive' ? '离线' : '待认证'}
        />
      ),
    },
    {
      title: '权限',
      dataIndex: 'permissions',
      key: 'permissions',
      render: (permissions: string[]) => (
        <Space size={4} wrap>
          {permissions?.map((p, i) => (
            <Tag key={i} color="green">{p}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '最后在线',
      dataIndex: 'last_seen',
      key: 'last_seen',
      render: (time: string) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDeleteDevice(record.id)}
        />
      ),
    },
  ]

  const bindingColumns: ColumnsType<Binding> = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Peer ID',
      dataIndex: 'peer_id',
      key: 'peer_id',
      render: (v: string) => v || '-',
    },
    {
      title: 'Guild ID',
      dataIndex: 'guild_id',
      key: 'guild_id',
      render: (v: string) => v || '-',
    },
    {
      title: 'Channel ID',
      dataIndex: 'channel_id',
      key: 'channel_id',
      render: (v: string) => v || '-',
    },
    {
      title: 'Agent ID',
      dataIndex: 'agent_id',
      key: 'agent_id',
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      sorter: (a, b) => a.priority - b.priority,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'success' : 'default'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDeleteBinding(record.id)}
        />
      ),
    },
  ]

  return (
    <div style={{ padding: '0 0 24px' }}>
      <Alert
        type="warning"
        showIcon
        message="实验功能"
        description="Gateway 当前仍处于实验阶段，页面展示与操作结果需要以实际后端状态和设备绑定结果为准。"
        style={{ marginBottom: 16 }}
      />
      <Title level={4} style={{ marginBottom: 24 }}>
        <ClusterOutlined style={{ marginRight: 8 }} />
        Gateway 管理（实验）
      </Title>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="在线设备"
              value={devices.filter(d => d.status === 'active').length}
              prefix={<LinkOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总设备数"
              value={devices.length}
              prefix={<ApiOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="绑定规则"
              value={bindings.length}
              prefix={<SafetyOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="活跃 Agent"
              value={agents.filter(a => a.status === 'active').length}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="devices">
          <TabPane
            tab={
              <span>
                <ApiOutlined />
                设备管理
              </span>
            }
            key="devices"
          >
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setRegisterModalVisible(true)}
                >
                  注册设备
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={fetchGatewayData}
                  loading={loading}
                >
                  刷新
                </Button>
              </Space>
            </div>
            <Table
              columns={deviceColumns}
              dataSource={devices}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane
            tab={
              <span>
                <LinkOutlined />
                绑定规则
              </span>
            }
            key="bindings"
          >
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setBindingModalVisible(true)}
                >
                  创建绑定
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={fetchGatewayData}
                  loading={loading}
                >
                  刷新
                </Button>
              </Space>
            </div>
            <Table
              columns={bindingColumns}
              dataSource={bindings}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane
            tab={
              <span>
                <MessageOutlined />
                消息路由
              </span>
            }
            key="messages"
          >
            <Card>
              <Descriptions title="Gateway 状态" column={2}>
                <Descriptions.Item label="服务状态">
                  <Badge status="success" text="运行中" />
                </Descriptions.Item>
                <Descriptions.Item label="WebSocket">
                  <Tag color="blue">{gatewayWebSocketUrl}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="活跃连接">
                  {gatewayStatus.gateway?.active_connections || 0}
                </Descriptions.Item>
                <Descriptions.Item label="消息队列">
                  {gatewayStatus.router?.message_queue_size || 0}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title="注册设备"
        open={registerModalVisible}
        onCancel={() => setRegisterModalVisible(false)}
        onOk={() => registerForm.submit()}
      >
        <Form
          form={registerForm}
          layout="vertical"
          onFinish={handleRegisterDevice}
        >
          <Form.Item
            name="name"
            label="设备名称"
            rules={[{ required: true, message: '请输入设备名称' }]}
          >
            <Input placeholder="例如: My Device" />
          </Form.Item>
          <Form.Item
            name="type"
            label="设备类型"
            rules={[{ required: true, message: '请选择设备类型' }]}
          >
            <Select placeholder="选择设备类型">
              <Select.Option value="desktop">桌面端</Select.Option>
              <Select.Option value="mobile">移动端</Select.Option>
              <Select.Option value="web">Web 端</Select.Option>
              <Select.Option value="api">API 客户端</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="permissions"
            label="权限"
          >
            <Select mode="multiple" placeholder="选择权限">
              <Select.Option value="chat">对话</Select.Option>
              <Select.Option value="inference">推理</Select.Option>
              <Select.Option value="training">训练</Select.Option>
              <Select.Option value="admin">管理</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="创建绑定规则"
        open={bindingModalVisible}
        onCancel={() => setBindingModalVisible(false)}
        onOk={() => bindingForm.submit()}
        width={600}
      >
        <Form
          form={bindingForm}
          layout="vertical"
          onFinish={handleCreateBinding}
        >
          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <Input placeholder="例如: Discord 绑定" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="peer_id" label="Peer ID">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="guild_id" label="Guild ID">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="channel_id" label="Channel ID">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="agent_id"
                label="Agent ID"
                rules={[{ required: true, message: '请输入 Agent ID' }]}
              >
                <Input placeholder="绑定到的 Agent" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="priority" label="优先级" initialValue={0}>
            <Select>
              <Select.Option value={100}>高 (100)</Select.Option>
              <Select.Option value={50}>中 (50)</Select.Option>
              <Select.Option value={0}>低 (0)</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
