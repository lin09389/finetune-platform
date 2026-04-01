import { useEffect, useState } from 'react'
import { App, Badge, Button, Card, Empty, Form, Input, List, Modal, Space, Tag } from 'antd'
import { DeleteOutlined, EditOutlined, FolderOutlined, PlusOutlined } from '@ant-design/icons'
import { API_BASE_URL } from '../services/api'

const { TextArea } = Input

interface Workspace {
  id: string
  name: string
  description?: string
  created_at: string
  updated_at: string
  document_count: number
  vector_count: number
}

type WorkspaceListResponse = Workspace[] | { workspaces?: Workspace[] }

function normalizeWorkspaces(data: WorkspaceListResponse): Workspace[] {
  if (Array.isArray(data)) {
    return data
  }
  if (data && Array.isArray(data.workspaces)) {
    return data.workspaces
  }
  return []
}

export default function WorkspaceManager() {
  const { message } = App.useApp()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editingWorkspace, setEditingWorkspace] = useState<Workspace | null>(null)
  const [form] = Form.useForm()

  useEffect(() => {
    void loadWorkspaces()
  }, [])

  const loadWorkspaces = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces`)
      if (!response.ok) {
        message.error('加载工作空间失败')
        return
      }
      const data = (await response.json()) as WorkspaceListResponse
      setWorkspaces(normalizeWorkspaces(data))
    } catch (error) {
      console.error('Failed to load workspaces:', error)
      message.error('加载工作空间失败')
    }
  }

  const handleCreate = async (values: { name: string; description?: string }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })

      if (response.ok) {
        message.success('工作空间创建成功')
        setModalVisible(false)
        form.resetFields()
        await loadWorkspaces()
      } else {
        message.error('创建工作空间失败')
      }
    } catch {
      message.error('创建工作空间失败')
    }
  }

  const handleUpdate = async (values: { name?: string; description?: string }) => {
    if (!editingWorkspace) return

    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces/${editingWorkspace.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })

      if (response.ok) {
        message.success('工作空间更新成功')
        setModalVisible(false)
        setEditingWorkspace(null)
        form.resetFields()
        await loadWorkspaces()
      } else {
        message.error('更新工作空间失败')
      }
    } catch {
      message.error('更新工作空间失败')
    }
  }

  const handleDelete = async (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后将无法恢复，确认继续吗？',
      onOk: async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/workspace/workspaces/${id}`, {
            method: 'DELETE',
          })

          if (response.ok) {
            message.success('工作空间已删除')
            await loadWorkspaces()
          } else {
            message.error('删除工作空间失败')
          }
        } catch {
          message.error('删除工作空间失败')
        }
      },
    })
  }

  const openModal = (workspace?: Workspace) => {
    if (workspace) {
      setEditingWorkspace(workspace)
      form.setFieldsValue({
        name: workspace.name,
        description: workspace.description,
      })
    } else {
      setEditingWorkspace(null)
      form.resetFields()
    }
    setModalVisible(true)
  }

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">工作空间管理</div>

        <Card
          variant="borderless"
          extra={
            <Button
              type="primary"
              icon={<PlusOutlined />}
              data-testid="workspace-create-primary"
              onClick={() => openModal()}
            >
              新建工作空间
            </Button>
          }
        >
          {workspaces.length > 0 ? (
            <List
              grid={{ gutter: 16, column: 2 }}
              dataSource={workspaces}
              renderItem={(ws) => (
                <List.Item>
                  <Card
                    hoverable
                    actions={[
                      <Button
                        key="edit"
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => openModal(ws)}
                      >
                        编辑
                      </Button>,
                      <Button
                        key="delete"
                        type="link"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(ws.id)}
                      >
                        删除
                      </Button>,
                    ]}
                  >
                    <Card.Meta
                      title={
                        <Space>
                          <FolderOutlined style={{ color: '#1677ff' }} />
                          <span>{ws.name}</span>
                          <Badge count={ws.vector_count} size="small" color="blue" />
                        </Space>
                      }
                      description={
                        <div>
                          <div style={{ color: '#666', marginBottom: 8 }}>
                            {ws.description || '暂无描述'}
                          </div>
                          <Space size="small">
                            <Tag color="green">{ws.document_count} 文档</Tag>
                            <Tag color="blue">{ws.vector_count} 向量</Tag>
                          </Space>
                          <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
                            创建于：{new Date(ws.created_at).toLocaleDateString('zh-CN')}
                          </div>
                        </div>
                      }
                    />
                  </Card>
                </List.Item>
              )}
            />
          ) : (
            <Empty description="暂无工作空间" image={Empty.PRESENTED_IMAGE_SIMPLE}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                data-testid="workspace-create-empty"
                onClick={() => openModal()}
              >
                创建工作空间
              </Button>
            </Empty>
          )}
        </Card>

        <Modal
          title={editingWorkspace ? '编辑工作空间' : '创建工作空间'}
          open={modalVisible}
          onOk={() => form.submit()}
          onCancel={() => {
            setModalVisible(false)
            setEditingWorkspace(null)
            form.resetFields()
          }}
        >
          <Form
            form={form}
            layout="vertical"
            onFinish={editingWorkspace ? handleUpdate : handleCreate}
          >
            <Form.Item
              name="name"
              label="名称"
              rules={[{ required: true, message: '请输入名称' }]}
            >
              <Input placeholder="例如：个人知识库、项目文档" />
            </Form.Item>

            <Form.Item name="description" label="描述">
              <TextArea rows={3} placeholder="可选，用于说明该工作空间用途" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </div>
  )
}
