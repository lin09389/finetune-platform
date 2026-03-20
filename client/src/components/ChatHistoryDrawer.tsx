import { Drawer, List, Button, Input, Empty, Typography, Tag } from 'antd'
import { DeleteOutlined, SearchOutlined } from '@ant-design/icons'
import { useState } from 'react'

interface Session {
  id: string
  title: string
  model_id?: string
  created_at?: string
  updated_at?: string
  message_count?: number
}

interface ChatHistoryDrawerProps {
  open: boolean
  onClose: () => void
  sessions: Session[]
  onLoadSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
}

const { Text } = Typography

const ChatHistoryDrawer: React.FC<ChatHistoryDrawerProps> = ({
  open,
  onClose,
  sessions,
  onLoadSession,
  onDeleteSession,
}) => {
  const [searchTerm, setSearchTerm] = useState('')

  const filteredSessions = sessions.filter(session =>
    session.title.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    
    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  return (
    <Drawer
      title="对话历史"
      placement="left"
      width={320}
      open={open}
      onClose={onClose}
      styles={{
        body: { padding: 0 }
      }}
    >
      <div style={{ padding: 16, borderBottom: '1px solid #f0f0f0' }}>
        <Input
          placeholder="搜索对话..."
          prefix={<SearchOutlined style={{ color: '#999' }} />}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          allowClear
        />
      </div>

      <div style={{ padding: 8 }}>
        {filteredSessions.length === 0 ? (
          searchTerm ? (
            <Empty description="没有找到匹配的对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Empty description="暂无对话历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )
        ) : (
          <List
            dataSource={filteredSessions}
            renderItem={(session) => (
              <List.Item
                onClick={() => onLoadSession(session.id)}
                style={{
                  padding: '12px 16px',
                  marginBottom: 8,
                  borderRadius: 8,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  background: '#fff',
                  border: '1px solid #f0f0f0',
                }}
                actions={[
                  <Button
                    key="delete"
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      onDeleteSession(session.id)
                    }}
                  />,
                ]}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = '#f5f5f5'
                  e.currentTarget.style.borderColor = '#d9d9d9'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = '#fff'
                  e.currentTarget.style.borderColor = '#f0f0f0'
                }}
              >
                <List.Item.Meta
                  title={
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text ellipsis style={{ maxWidth: 180, fontWeight: 500 }}>
                        {session.title}
                      </Text>
                      {session.message_count !== undefined && (
                        <Tag color="blue" style={{ marginLeft: 8 }}>{session.message_count}条</Tag>
                      )}
                    </div>
                  }
                  description={
                    <div style={{ fontSize: 12, color: '#999' }}>
                      {formatDate(session.updated_at || session.created_at)}
                      {session.model_id && (
                        <span style={{ marginLeft: 8 }}>· {session.model_id}</span>
                      )}
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </Drawer>
  )
}

export default ChatHistoryDrawer
