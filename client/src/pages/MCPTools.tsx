import { useState, useEffect } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Typography,
  Tag,
  message,
  Modal,
  Form,
  Input,
  Select,
  Row,
  Col,
  Statistic,
  Divider,
  Badge,
  Empty,
  Spin,
} from 'antd'
import {
  ApiOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  LinkOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { apiClient } from '../services/api'

const { Title, Text } = Typography

interface MCPToolItem {
  name: string
  description: string
  input_schema: Record<string, unknown>
  server_name?: string
}

interface MCPServerItem {
  name: string
  transport: 'stdio' | 'sse'
  status: 'connected' | 'disconnected'
  command?: string
  args?: string[]
  url?: string
  tool_count?: number
}

export default function MCPTools() {
  const [tools, setTools] = useState<MCPToolItem[]>([])
  const [servers, setServers] = useState<MCPServerItem[]>([])
  const [loading, setLoading] = useState(false)
  const [addModalVisible, setAddModalVisible] = useState(false)
  const [callModalVisible, setCallModalVisible] = useState(false)
  const [selectedTool, setSelectedTool] = useState<MCPToolItem | null>(null)
  const [callArgs, setCallArgs] = useState('{}')
  const [form] = Form.useForm()

  useEffect(() => {
    fetchTools()
    fetchServers()
  }, [])

  const fetchTools = async () => {
    setLoading(true)
    try {
      const response = await apiClient.get('/mcp/tools')
      setTools(response.data.tools || [])
    } catch (error) {
      console.error('Failed to fetch tools:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchServers = async () => {
    try {
      const response = await apiClient.get('/mcp/servers')
      setServers(response.data.servers || [])
    } catch (error) {
      console.error('Failed to fetch servers:', error)
    }
  }

  const handleAddServer = async (values: {
    name: string
    transport: 'stdio' | 'sse'
    command?: string
    args?: string
    url?: string
  }) => {
    try {
      const payload: Record<string, unknown> = {
        name: values.name,
        transport: values.transport,
      }
      if (values.transport === 'stdio') {
        payload['command'] = values.command
        payload['args'] = values.args ? values.args.split(' ') : []
      } else {
        payload['url'] = values.url
      }

      await apiClient.post('/mcp/servers', payload)
      message.success('服务器添加成功')
      setAddModalVisible(false)
      form.resetFields()
      fetchServers()
      fetchTools()
    } catch (error) {
      message.error('添加服务器失败')
    }
  }

  const handleRemoveServer = async (name: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除服务器 "${name}" 吗？`,
      onOk: async () => {
        try {
          await apiClient.delete(`/mcp/servers/${name}`)
          message.success('服务器已删除')
          fetchServers()
          fetchTools()
        } catch (error) {
          message.error('删除失败')
        }
      },
    })
  }

  const handleReconnect = async (name: string) => {
    try {
      await apiClient.post(`/mcp/servers/${name}/reconnect`)
      message.success('重连成功')
      fetchServers()
    } catch (error) {
      message.error('重连失败')
    }
  }

  const handleCallTool = async () => {
    if (!selectedTool) return
    try {
      const args = JSON.parse(callArgs)
      const response = await apiClient.post('/mcp/call', {
        tool_name: selectedTool.name,
        arguments: args,
      })
      if (response.data.is_error) {
        message.error(`调用失败: ${response.data.content}`)
      } else {
        message.success('调用成功')
        Modal.success({
          title: '执行结果',
          content: (
            <pre style={{ maxHeight: 400, overflow: 'auto' }}>
              {JSON.stringify(response.data.content, null, 2)}
            </pre>
          ),
        })
      }
    } catch (error) {
      message.error('参数格式错误或调用失败')
    }
  }

  const toolColumns = [
    {
      title: '工具名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '服务器',
      dataIndex: 'server_name',
      key: 'server_name',
      render: (name: string) => name ? <Tag>{name}</Tag> : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: MCPToolItem) => (
        <Button
          type="link"
          icon={<PlayCircleOutlined />}
          onClick={() => {
            setSelectedTool(record)
            setCallArgs('{}')
            setCallModalVisible(true)
          }}
        >
          调用
        </Button>
      ),
    },
  ]

  const serverColumns = [
    {
      title: '服务器名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '传输类型',
      dataIndex: 'transport',
      key: 'transport',
      render: (t: string) => <Tag color={t === 'stdio' ? 'green' : 'orange'}>{t}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Badge
          status={status === 'connected' ? 'success' : 'error'}
          text={status === 'connected' ? '已连接' : '未连接'}
        />
      ),
    },
    {
      title: '工具数量',
      dataIndex: 'tool_count',
      key: 'tool_count',
      render: (count: number) => count || 0,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: MCPServerItem) => (
        <Space>
          <Button
            type="link"
            icon={<LinkOutlined />}
            onClick={() => handleReconnect(record.name)}
          >
            重连
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleRemoveServer(record.name)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const connectedCount = servers.filter((s) => s.status === 'connected').length

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <ApiOutlined /> MCP 工具集成
      </Title>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="已连接服务器" value={connectedCount} suffix={`/ ${servers.length}`} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="可用工具" value={tools.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="传输类型"
              value={servers.filter((s) => s.transport === 'stdio').length}
              suffix="stdio"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="SSE 连接"
              value={servers.filter((s) => s.transport === 'sse').length}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title="MCP 服务器"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { fetchServers(); fetchTools(); }}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalVisible(true)}>
              添加服务器
            </Button>
          </Space>
        }
        style={{ marginBottom: 24 }}
      >
        {servers.length > 0 ? (
          <Table columns={serverColumns} dataSource={servers} rowKey="name" pagination={false} />
        ) : (
          <Empty description="暂无服务器" />
        )}
      </Card>

      <Card title="可用工具" extra={<Button icon={<ReloadOutlined />} onClick={fetchTools}>刷新</Button>}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : tools.length > 0 ? (
          <Table columns={toolColumns} dataSource={tools} rowKey="name" pagination={{ pageSize: 20 }} />
        ) : (
          <Empty description="暂无工具，请先添加 MCP 服务器" />
        )}
      </Card>

      <Modal
        title="添加 MCP 服务器"
        open={addModalVisible}
        onOk={() => form.submit()}
        onCancel={() => {
          setAddModalVisible(false)
          form.resetFields()
        }}
      >
        <Form form={form} onFinish={handleAddServer} layout="vertical">
          <Form.Item name="name" label="服务器名称" rules={[{ required: true }]}>
            <Input placeholder="例如: filesystem" />
          </Form.Item>
          <Form.Item name="transport" label="传输类型" rules={[{ required: true }]} initialValue="stdio">
            <Select
              options={[
                { label: 'stdio (本地进程)', value: 'stdio' },
                { label: 'sse (HTTP/SSE)', value: 'sse' },
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, curr) => prev.transport !== curr.transport}
          >
            {({ getFieldValue }) =>
              getFieldValue('transport') === 'stdio' ? (
                <>
                  <Form.Item name="command" label="命令" rules={[{ required: true }]}>
                    <Input placeholder="例如: npx" />
                  </Form.Item>
                  <Form.Item name="args" label="参数 (空格分隔)">
                    <Input placeholder="例如: -y @modelcontextprotocol/server-filesystem /path" />
                  </Form.Item>
                </>
              ) : (
                <Form.Item name="url" label="URL" rules={[{ required: true }]}>
                  <Input placeholder="例如: http://localhost:8080/sse" />
                </Form.Item>
              )
            }
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`调用工具: ${selectedTool?.name || ''}`}
        open={callModalVisible}
        onOk={handleCallTool}
        onCancel={() => setCallModalVisible(false)}
        width={600}
      >
        {selectedTool && (
          <>
            <Text type="secondary">{selectedTool.description}</Text>
            <Divider />
            <Text strong>参数 (JSON 格式):</Text>
            <Input.TextArea
              value={callArgs}
              onChange={(e) => setCallArgs(e.target.value)}
              rows={10}
              style={{ fontFamily: 'monospace', marginTop: 8 }}
            />
            {selectedTool.input_schema && (
              <>
                <Divider />
                <Text strong>参数 Schema:</Text>
                <pre style={{ maxHeight: 200, overflow: 'auto', background: '#f5f5f5', padding: 12 }}>
                  {JSON.stringify(selectedTool.input_schema, null, 2)}
                </pre>
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  )
}
