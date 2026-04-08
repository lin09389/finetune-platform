/**
 * 增强版记忆管理组件
 * 支持知识图谱、短期记忆、MCP协议
 */
import { useState, useEffect } from 'react'
import {
  Modal, List, Button, Tag, Empty, Spin, message,
  Tabs, Typography, Popconfirm, Input, Space, Card,
  Statistic, Row, Col, Progress, Divider, Drawer,
  Select, Badge, Tooltip
} from 'antd'
import {
  DeleteOutlined, ClockCircleOutlined,
  HistoryOutlined, BookOutlined,
  SearchOutlined, ClearOutlined,
  NodeIndexOutlined, ExportOutlined,
  ImportOutlined, DashboardOutlined, ApiOutlined
} from '@ant-design/icons'

import {
  memoryApi,
  Memory, GraphStats, SessionSummary,
  MEMORY_TYPES, ENTITY_TYPES
} from '../services/memoryApi'
import KnowledgeGraph from './KnowledgeGraph'

const { Search } = Input
const { Text } = Typography
const { Option } = Select

interface MemoryManagerProps {
  open: boolean
  onClose: () => void
}

export default function MemoryManager({ open, onClose }: MemoryManagerProps) {
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(false)
  const [activeType, setActiveType] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [totalCount, setTotalCount] = useState(0)
  const [stats, setStats] = useState<{
    total_memories: number
    knowledge_graph: GraphStats
    short_term_memory: SessionSummary
  } | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null)
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)

  useEffect(() => {
    if (open) {
      loadData()
    }
  }, [open, activeType])

  const loadData = async () => {
    setLoading(true)
    try {
      const [memoriesData, statsData] = await Promise.all([
        memoryApi.listMemories('default', activeType === 'all' ? undefined : activeType, 100),
        memoryApi.getStats()
      ])
      setMemories(memoriesData.memories)
      setTotalCount(memoriesData.count)
      setStats(statsData)
    } catch (error) {
      console.error('加载记忆失败:', error)
      message.error('加载记忆失败')
    } finally {
      setLoading(false)
    }
  }

  const searchMemories = async () => {
    if (!searchQuery.trim()) {
      loadData()
      return
    }

    setLoading(true)
    try {
      const results = await memoryApi.recall(searchQuery, 'default', 20)
      setMemories(results)
      setTotalCount(results.length)
    } catch (error) {
      console.error('搜索失败:', error)
      message.error('搜索失败')
    } finally {
      setLoading(false)
    }
  }

  const deleteMemory = async (memoryId: string) => {
    try {
      await memoryApi.deleteMemory(memoryId)
      message.success('已删除')
      loadData()
    } catch (error) {
      console.error('删除失败:', error)
      message.error('删除失败')
    }
  }

  const clearAllMemories = async () => {
    try {
      await memoryApi.clearAll()
      message.success('所有记忆已清除')
      setMemories([])
      setTotalCount(0)
      loadData()
    } catch (error) {
      console.error('清除失败:', error)
      message.error('清除失败')
    }
  }

  const exportState = async () => {
    try {
      const state = await memoryApi.exportState()
      const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `memory-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (error) {
      message.error('导出失败')
    }
  }

  const importState = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      
      try {
        const text = await file.text()
        const state = JSON.parse(text)
        await memoryApi.importState(state)
        message.success('导入成功')
        loadData()
      } catch (error) {
        message.error('导入失败')
      }
    }
    input.click()
  }

  const getTypeConfig = (type: string) => {
    return MEMORY_TYPES[type] || { label: type, color: 'default', icon: '📄' }
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    try {
      return new Date(dateStr).toLocaleString('zh-CN')
    } catch {
      return dateStr
    }
  }

  const renderImportance = (importance: number) => {
    const percent = Math.round(importance * 100)
    return (
      <Progress 
        percent={percent} 
        size="small" 
        showInfo={false}
        strokeColor={{
          '0%': '#ff4d4f',
          '50%': '#faad14',
          '100%': '#52c41a'
        }}
        style={{ width: 60 }}
      />
    )
  }

  const tabItems = [
    {
      key: 'memories',
      label: (
        <span>
          <BookOutlined />
          记忆列表
          <Badge count={totalCount} style={{ marginLeft: 8 }} />
        </span>
      ),
      children: (
        <>
          <Space style={{ width: '100%', marginBottom: 16 }}>
            <Search
              placeholder="搜索记忆..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onSearch={searchMemories}
              style={{ width: 300 }}
              enterButton={<SearchOutlined />}
            />
            <Select
              value={activeType}
              onChange={setActiveType}
              style={{ width: 150 }}
            >
              <Option value="all">全部类型</Option>
              {Object.entries(MEMORY_TYPES).map(([key, config]) => (
                <Option key={key} value={key}>
                  {config.icon} {config.label}
                </Option>
              ))}
            </Select>
            <Popconfirm
              title="确定清除所有记忆？"
              description="此操作不可恢复"
              onConfirm={clearAllMemories}
            >
              <Button danger icon={<ClearOutlined />}>
                清除全部
              </Button>
            </Popconfirm>
          </Space>

          {loading ? (
            <Spin style={{ display: 'block', margin: '40px auto' }} />
          ) : memories.length === 0 ? (
            <Empty
              description="暂无记忆"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Text type="secondary">
                对话中提到的重要信息会自动保存为记忆
              </Text>
            </Empty>
          ) : (
            <List
              dataSource={memories}
              style={{ maxHeight: 400, overflow: 'auto' }}
              renderItem={(memory) => {
                const config = getTypeConfig(memory.type)

                return (
                  <List.Item
                    actions={[
                      <Tooltip key="detail" title="查看详情">
                        <Button
                          type="text"
                          size="small"
                          icon={<DashboardOutlined />}
                          onClick={() => {
                            setSelectedMemory(memory)
                            setDetailDrawerOpen(true)
                          }}
                        />
                      </Tooltip>,
                      <Popconfirm
                        key="delete"
                        title="确定删除这条记忆？"
                        onConfirm={() => deleteMemory(memory.id)}
                      >
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                        />
                      </Popconfirm>
                    ]}
                  >
                    <List.Item.Meta
                      avatar={
                        <Tag color={config.color} style={{ padding: '4px 8px' }}>
                          {config.icon}
                        </Tag>
                      }
                      title={<Text style={{ fontSize: 14 }}>{memory.content}</Text>}
                      description={
                        <Space split={<span style={{ color: '#d9d9d9' }}>|</span>} style={{ fontSize: 12 }}>
                          <span>
                            <ClockCircleOutlined /> {formatDate(memory.created_at)}
                          </span>
                          <span>
                            重要度: {renderImportance(memory.importance)}
                          </span>
                          <span>
                            访问: {memory.access_count}次
                          </span>
                          {memory.relevance !== undefined && memory.relevance > 0 && (
                            <span>
                              相关度: {(memory.relevance * 100).toFixed(0)}%
                            </span>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )
              }}
            />
          )}
        </>
      )
    },
    {
      key: 'graph',
      label: (
        <span>
          <NodeIndexOutlined />
          知识图谱
          {stats?.knowledge_graph && (
            <Badge 
              count={stats.knowledge_graph.total_entities} 
              style={{ marginLeft: 8, backgroundColor: '#52c41a' }} 
            />
          )}
        </span>
      ),
      children: <KnowledgeGraph />
    },
    {
      key: 'stats',
      label: (
        <span>
          <DashboardOutlined />
          统计面板
        </span>
      ),
      children: (
        <>
          {stats && (
            <>
              <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="总记忆数"
                      value={stats.total_memories}
                      prefix={<BookOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="知识实体"
                      value={stats.knowledge_graph.total_entities}
                      prefix={<NodeIndexOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="关系数量"
                      value={stats.knowledge_graph.total_relations}
                      prefix={<ApiOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="会话消息"
                      value={stats.short_term_memory.message_count}
                      prefix={<HistoryOutlined />}
                    />
                  </Card>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col span={12}>
                  <Card title="实体类型分布" size="small">
                    {Object.entries(stats.knowledge_graph.entity_types).map(([type, count]) => (
                      <div key={type} style={{ marginBottom: 8 }}>
                        <Text>
                          {ENTITY_TYPES[type]?.icon || '📄'} {ENTITY_TYPES[type]?.label || type}: {count}
                        </Text>
                        <Progress 
                          percent={(count / stats.knowledge_graph.total_entities) * 100} 
                          size="small"
                          showInfo={false}
                        />
                      </div>
                    ))}
                  </Card>
                </Col>
                <Col span={12}>
                  <Card title="关系类型分布" size="small">
                    {Object.entries(stats.knowledge_graph.relation_types).map(([type, count]) => (
                      <div key={type} style={{ marginBottom: 8 }}>
                        <Text>{type}: {count}</Text>
                        <Progress 
                          percent={(count / Math.max(1, stats.knowledge_graph.total_relations)) * 100} 
                          size="small"
                          showInfo={false}
                        />
                      </div>
                    ))}
                  </Card>
                </Col>
              </Row>

              <Divider />

              <Card title="短期记忆状态" size="small">
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title="会话时长"
                      value={Math.round(stats.short_term_memory.session_duration)}
                      suffix="秒"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="活跃实体"
                      value={stats.short_term_memory.active_entities.length}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="平均重要性"
                      value={stats.short_term_memory.average_importance * 100}
                      precision={1}
                      suffix="%"
                    />
                  </Col>
                </Row>
              </Card>
            </>
          )}
        </>
      )
    }
  ]

  return (
    <Modal
      title={
        <Space>
          <span>🧠 智能记忆管理</span>
          <Tag color="blue">增强版</Tag>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <Button icon={<ExportOutlined />} onClick={exportState}>
            导出
          </Button>
          <Button icon={<ImportOutlined />} onClick={importState}>
            导入
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
      width={900}
    >
      <Tabs items={tabItems} />

      <Drawer
        title="记忆详情"
        placement="right"
        width={400}
        open={detailDrawerOpen}
        onClose={() => setDetailDrawerOpen(false)}
      >
        {selectedMemory && (
          <>
            <div><strong>ID:</strong> {selectedMemory.id}</div>
            <div><strong>类型:</strong> {getTypeConfig(selectedMemory.type).label}</div>
            <div><strong>内容:</strong></div>
            <Card size="small">{selectedMemory.content}</Card>
            <div><strong>重要度:</strong> {renderImportance(selectedMemory.importance)}</div>
            <div><strong>创建时间:</strong> {formatDate(selectedMemory.created_at)}</div>
            <div><strong>最后访问:</strong> {formatDate(selectedMemory.last_accessed)}</div>
            <div><strong>访问次数:</strong> {selectedMemory.access_count}</div>
          </>
        )}
      </Drawer>
    </Modal>
  )
}
