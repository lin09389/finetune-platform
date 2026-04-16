import { useState, useEffect } from 'react'
import {
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
  Alert,
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
  WarningOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { API_BASE_URL, apiClient } from '../services/api'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './GatewayPage.module.css'

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

interface GatewayStatus {
  tier?: string
  available?: boolean
  runtime_status?: string
  dependency_status?: string
  failure_mode?: string
  message?: string
  gateway?: {
    active_connections?: number
  }
  router?: {
    message_queue_size?: number
  }
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

type TabKey = 'devices' | 'bindings' | 'messages'

export default function GatewayPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [bindings, setBindings] = useState<Binding[]>([])
  const [agents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('devices')
  const [registerModalVisible, setRegisterModalVisible] = useState(false)
  const [bindingModalVisible, setBindingModalVisible] = useState(false)
  const [registerForm] = Form.useForm()
  const [bindingForm] = Form.useForm()
  const [gatewayStatus, setGatewayStatus] = useState<GatewayStatus>({})
  const [statusNotice, setStatusNotice] = useState('')

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
      setStatusNotice(
        statusRes.data && Object.keys(statusRes.data).length > 0
          ? ''
          : 'Gateway 状态接口当前不可用，设备和绑定列表不代表路由、会话与消息能力已经可用。'
      )
      setDevices((devicesRes.data?.devices || []).map(normalizeDevice))
      setBindings((bindingsRes.data?.bindings || []).map(normalizeBinding))
    } catch (error) {
      console.error('Failed to fetch gateway data:', error)
      setStatusNotice('Gateway 数据获取失败，当前页面无法确认实验连接与路由能力。')
    } finally {
      setLoading(false)
    }
  }

  const handleRegisterDevice = async (values: any) => {
    try {
      const response = await apiClient.post('/gateway/devices/register', {
        device_name: values.name,
        device_type: values.type,
        metadata: { requested_permissions: values.permissions || [] },
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
    { title: '设备 ID', dataIndex: 'id', key: 'id', width: 200, ellipsis: true },
    { title: '名称', dataIndex: 'name', key: 'name' },
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
          {permissions?.map((p, i) => <Tag key={i} color="green">{p}</Tag>)}
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
        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteDevice(record.id)} />
      ),
    },
  ]

  const bindingColumns: ColumnsType<Binding> = [
    { title: '规则名称', dataIndex: 'name', key: 'name' },
    { title: 'Peer ID', dataIndex: 'peer_id', key: 'peer_id', render: (v: string) => v || '-' },
    { title: 'Guild ID', dataIndex: 'guild_id', key: 'guild_id', render: (v: string) => v || '-' },
    { title: 'Channel ID', dataIndex: 'channel_id', key: 'channel_id', render: (v: string) => v || '-' },
    { title: 'Agent ID', dataIndex: 'agent_id', key: 'agent_id' },
    { title: '优先级', dataIndex: 'priority', key: 'priority', sorter: (a, b) => a.priority - b.priority },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => <Tag color={enabled ? 'success' : 'default'}>{enabled ? '启用' : '禁用'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteBinding(record.id)} />
      ),
    },
  ]

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'devices', label: '设备管理', icon: <ApiOutlined /> },
    { key: 'bindings', label: '绑定规则', icon: <LinkOutlined /> },
    { key: 'messages', label: '消息路由', icon: <MessageOutlined /> },
  ]

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
      {/* 标题栏 */}
      <div className={styles.headerCard}>
        <div className={styles.headerIcon}>
          <ClusterOutlined />
        </div>
        <div>
          <h2 className={styles.headerTitle}>Gateway 管理</h2>
          <p className={styles.headerSubtitle}>设备认证、消息路由与绑定规则管理</p>
        </div>
      </div>

      {/* 实验提示 */}
      <div className={styles.warningBanner}>
        <WarningOutlined className={styles.warningIcon} />
        <span>
          <strong>实验功能</strong> — Gateway 当前仍处于实验阶段，页面展示与操作结果需要以实际后端状态和设备绑定结果为准。
        </span>
      </div>
      <Alert
        data-testid="gateway-runtime-status"
        showIcon
        type={gatewayStatus.runtime_status === 'ready' ? 'success' : 'warning'}
        message={gatewayStatus.runtime_status === 'ready' ? '已检测到 Gateway 活跃连接' : 'Gateway 当前能力受限'}
        description={`${statusNotice || gatewayStatus.message || '尚未拿到 Gateway 运行状态。'}${gatewayStatus.dependency_status ? ` 依赖状态：${gatewayStatus.dependency_status}。` : ''}`}
        style={{ marginBottom: 20 }}
      />

      {/* 统计卡片 */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.green}`}><LinkOutlined /></div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{devices.filter(d => d.status === 'active').length}</span>
            <span className={styles.statLabel}>在线设备</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.blue}`}><ApiOutlined /></div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{devices.length}</span>
            <span className={styles.statLabel}>总设备数</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.purple}`}><SafetyOutlined /></div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{bindings.length}</span>
            <span className={styles.statLabel}>绑定规则</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.cyan}`}><UserOutlined /></div>
          <div className={styles.statInfo}>
            <span className={styles.statValue}>{agents.filter(a => a.status === 'active').length}</span>
            <span className={styles.statLabel}>活跃 Agent</span>
          </div>
        </div>
      </div>

      {/* 主内容卡片 */}
      <div className={styles.mainCard}>
        {/* 标签栏 */}
        <div className={styles.tabsHeader}>
          {tabs.map(t => (
            <div
              key={t.key}
              className={`${styles.tab} ${activeTab === t.key ? styles.active : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.icon}
              {t.label}
            </div>
          ))}
        </div>

        <div className={styles.tabContent}>
          {activeTab === 'devices' && (
            <>
              <div className={styles.toolbarRow}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterModalVisible(true)}>
                  注册设备
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchGatewayData} loading={loading}>
                  刷新
                </Button>
              </div>
              <Table columns={deviceColumns} dataSource={devices} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
            </>
          )}

          {activeTab === 'bindings' && (
            <>
              <div className={styles.toolbarRow}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setBindingModalVisible(true)}>
                  创建绑定
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchGatewayData} loading={loading}>
                  刷新
                </Button>
              </div>
              <Table columns={bindingColumns} dataSource={bindings} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
            </>
          )}

          {activeTab === 'messages' && (
            <div className={styles.statusRow}>
              <div className={styles.statusItem}>
                <div className={styles.statusLabel}>服务状态</div>
                <div className={styles.statusValue}><Badge status="success" text="运行中" /></div>
              </div>
              <div className={styles.statusItem}>
                <div className={styles.statusLabel}>WebSocket 地址</div>
                <div className={styles.wsUrl}>{gatewayWebSocketUrl}</div>
              </div>
              <div className={styles.statusItem}>
                <div className={styles.statusLabel}>活跃连接</div>
                <div className={styles.statusValue}>{gatewayStatus.gateway?.active_connections || 0}</div>
              </div>
              <div className={styles.statusItem}>
                <div className={styles.statusLabel}>消息队列</div>
                <div className={styles.statusValue}>{gatewayStatus.router?.message_queue_size || 0}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 注册设备弹窗 */}
      <Modal title="注册设备" open={registerModalVisible} onCancel={() => setRegisterModalVisible(false)} onOk={() => registerForm.submit()}>
        <Form form={registerForm} layout="vertical" onFinish={handleRegisterDevice}>
          <Form.Item name="name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
            <Input placeholder="例如: My Device" />
          </Form.Item>
          <Form.Item name="type" label="设备类型" rules={[{ required: true, message: '请选择设备类型' }]}>
            <Select placeholder="选择设备类型">
              <Select.Option value="desktop">桌面端</Select.Option>
              <Select.Option value="mobile">移动端</Select.Option>
              <Select.Option value="web">Web 端</Select.Option>
              <Select.Option value="api">API 客户端</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="permissions" label="权限">
            <Select mode="multiple" placeholder="选择权限">
              <Select.Option value="chat">对话</Select.Option>
              <Select.Option value="inference">推理</Select.Option>
              <Select.Option value="training">训练</Select.Option>
              <Select.Option value="admin">管理</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 创建绑定弹窗 */}
      <Modal title="创建绑定规则" open={bindingModalVisible} onCancel={() => setBindingModalVisible(false)} onOk={() => bindingForm.submit()} width={600}>
        <Form form={bindingForm} layout="vertical" onFinish={handleCreateBinding}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="例如: Discord 绑定" />
          </Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item name="peer_id" label="Peer ID"><Input placeholder="可选" /></Form.Item>
            <Form.Item name="guild_id" label="Guild ID"><Input placeholder="可选" /></Form.Item>
            <Form.Item name="channel_id" label="Channel ID"><Input placeholder="可选" /></Form.Item>
            <Form.Item name="agent_id" label="Agent ID" rules={[{ required: true, message: '请输入 Agent ID' }]}>
              <Input placeholder="绑定到的 Agent" />
            </Form.Item>
          </div>
          <Form.Item name="priority" label="优先级" initialValue={0}>
            <Select>
              <Select.Option value={100}>高 (100)</Select.Option>
              <Select.Option value={50}>中 (50)</Select.Option>
              <Select.Option value={0}>低 (0)</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
      </MotionItem>
    </MotionList>
  )
}
