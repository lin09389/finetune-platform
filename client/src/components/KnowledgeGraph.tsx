/**
 * 知识图谱可视化组件
 * 展示实体关系网络
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Tabs, Table, Tag, Button, Input, Space, Spin, Empty,
  Typography, Descriptions, Drawer, Select, message, Tooltip,
  Statistic, Row, Col, Badge, Popconfirm, Modal, Form
} from 'antd'
import {
  SearchOutlined, NodeIndexOutlined, LinkOutlined,
  PlusOutlined, DeleteOutlined, ReloadOutlined,
  ExpandOutlined, InfoCircleOutlined, UserOutlined,
  ProjectOutlined, BulbOutlined
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import {
  graphApi,
  Entity, Relation, GraphStats,
  ENTITY_TYPES, RELATION_TYPES
} from '../services/memoryApi'

const { Search } = Input
const { Title } = Typography
const { Option } = Select

interface KnowledgeGraphProps {
  style?: React.CSSProperties
}

export default function KnowledgeGraph({ style }: KnowledgeGraphProps) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [relations, setRelations] = useState<Relation[]>([])
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedEntityType, setSelectedEntityType] = useState<string>()
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null)
  const [entityContext, setEntityContext] = useState<{
    entity: Entity
    relations: Relation[]
    related_entities: Entity[]
  } | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [addEntityModalOpen, setAddEntityModalOpen] = useState(false)
  const [addRelationModalOpen, setAddRelationModalOpen] = useState(false)
  const [addEntityForm] = Form.useForm()
  const [addRelationForm] = Form.useForm()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const loadGraphData = useCallback(async () => {
    setLoading(true)
    try {
      const [statsData, allEntities, allRelations] = await Promise.all([
        graphApi.getStats(),
        graphApi.getAllEntities(),
        graphApi.getAllRelations()
      ])
      setStats(statsData)
      setEntities(allEntities)
      setRelations(allRelations)
    } catch (error) {
      console.error('加载知识图谱失败:', error)
      message.error('加载知识图谱失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadGraphData()
  }, [loadGraphData])

  useEffect(() => {
    if (canvasRef.current && entities.length > 0) {
      drawGraph()
    }
  }, [entities, relations])

  const drawGraph = () => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height

    ctx.fillStyle = '#1a1a2e'
    ctx.fillRect(0, 0, width, height)

    const centerX = width / 2
    const centerY = height / 2
    const radius = Math.min(width, height) * 0.35

    const nodePositions: Map<string, { x: number; y: number }> = new Map()
    
    entities.forEach((entity, index) => {
      const angle = (index / entities.length) * 2 * Math.PI
      const x = centerX + radius * Math.cos(angle)
      const y = centerY + radius * Math.sin(angle)
      nodePositions.set(entity.id, { x, y })
    })

    ctx.strokeStyle = 'rgba(100, 150, 255, 0.3)'
    ctx.lineWidth = 1
    relations.forEach(rel => {
      const source = nodePositions.get(rel.source_id)
      const target = nodePositions.get(rel.target_id)
      if (source && target) {
        ctx.beginPath()
        ctx.moveTo(source.x, source.y)
        ctx.lineTo(target.x, target.y)
        ctx.stroke()
      }
    })

    entities.forEach(entity => {
      const pos = nodePositions.get(entity.id)
      if (!pos) return

      const typeConfig = ENTITY_TYPES[entity.entity_type] || { color: '#666' }
      
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, 20, 0, 2 * Math.PI)
      ctx.fillStyle = typeConfig.color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()

      ctx.fillStyle = '#fff'
      ctx.font = '10px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(entity.name.slice(0, 6), pos.x, pos.y + 35)
    })
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadGraphData()
      return
    }

    setLoading(true)
    try {
      const results = await graphApi.search(searchQuery, selectedEntityType ? [selectedEntityType] : undefined)
      setEntities(results)
    } catch (error) {
      message.error('搜索失败')
    } finally {
      setLoading(false)
    }
  }

  const handleEntityClick = async (entity: Entity) => {
    setSelectedEntity(entity)
    setDrawerOpen(true)
    try {
      const context = await graphApi.getEntityContext(entity.id)
      setEntityContext(context)
    } catch (error) {
      console.error('获取实体上下文失败:', error)
    }
  }

  const handleAddEntity = async (values: { name: string; type: string; attributes: string }) => {
    try {
      const attrs = values.attributes ? JSON.parse(values.attributes) : {}
      await graphApi.addEntity(values.name, values.type, attrs)
      message.success('实体添加成功')
      setAddEntityModalOpen(false)
      addEntityForm.resetFields()
      loadGraphData()
    } catch (error) {
      message.error('添加失败')
    }
  }

  const handleAddRelation = async (values: { source: string; target: string; type: string; evidence: string }) => {
    try {
      await graphApi.addRelation(values.source, values.target, values.type, values.evidence)
      message.success('关系添加成功')
      setAddRelationModalOpen(false)
      addRelationForm.resetFields()
      loadGraphData()
    } catch (error) {
      message.error('添加失败')
    }
  }

  const handleDeleteEntity = async (entityId: string) => {
    try {
      await graphApi.deleteEntity(entityId)
      message.success('实体已删除')
      loadGraphData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const entityColumns: ColumnsType<Entity> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Button type="link" onClick={() => handleEntityClick(record)}>
          {text}
        </Button>
      )
    },
    {
      title: '类型',
      dataIndex: 'entity_type',
      key: 'entity_type',
      render: (type: string) => {
        const config = ENTITY_TYPES[type] || { label: type, color: '#666', icon: '' }
        return <Tag color={config.color}>{config.icon} {config.label}</Tag>
      }
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (val) => `${(val * 100).toFixed(0)}%`
    },
    {
      title: '访问次数',
      dataIndex: 'access_count',
      key: 'access_count'
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Tooltip title="查看详情">
            <Button size="small" icon={<InfoCircleOutlined />} onClick={() => handleEntityClick(record)} />
          </Tooltip>
          <Popconfirm title="确定删除此实体？" onConfirm={() => handleDeleteEntity(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ]

  const relationColumns: ColumnsType<Relation> = [
    {
      title: '源实体',
      dataIndex: 'source_id',
      key: 'source_id',
      render: (id) => {
        const entity = entities.find(e => e.id === id)
        return entity?.name || id.slice(0, 8)
      }
    },
    {
      title: '关系',
      dataIndex: 'relation_type',
      key: 'relation_type',
      render: (type) => {
        const config = RELATION_TYPES[type] || { label: type, color: '#666' }
        return <Tag color={config.color}>{config.label}</Tag>
      }
    },
    {
      title: '目标实体',
      dataIndex: 'target_id',
      key: 'target_id',
      render: (id) => {
        const entity = entities.find(e => e.id === id)
        return entity?.name || id.slice(0, 8)
      }
    },
    {
      title: '权重',
      dataIndex: 'weight',
      key: 'weight',
      render: (val) => val.toFixed(2)
    },
    {
      title: '证据',
      dataIndex: 'evidence',
      key: 'evidence',
      ellipsis: true
    }
  ]

  return (
    <div style={style}>
      <Card
        title={
          <Space>
            <NodeIndexOutlined />
            <span>知识图谱</span>
            {stats && (
              <Badge count={stats.total_entities} style={{ backgroundColor: '#52c41a' }} />
            )}
          </Space>
        }
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={() => setAddEntityModalOpen(true)}>
              添加实体
            </Button>
            <Button icon={<LinkOutlined />} onClick={() => setAddRelationModalOpen(true)}>
              添加关系
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadGraphData}>
              刷新
            </Button>
          </Space>
        }
      >
        {stats && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Statistic title="实体总数" value={stats.total_entities} prefix={<UserOutlined />} />
            </Col>
            <Col span={6}>
              <Statistic title="关系总数" value={stats.total_relations} prefix={<LinkOutlined />} />
            </Col>
            <Col span={6}>
              <Statistic title="实体类型" value={Object.keys(stats.entity_types).length} prefix={<BulbOutlined />} />
            </Col>
            <Col span={6}>
              <Statistic title="关系类型" value={Object.keys(stats.relation_types).length} prefix={<ProjectOutlined />} />
            </Col>
          </Row>
        )}

        <Space style={{ width: '100%', marginBottom: 16 }}>
          <Search
            placeholder="搜索实体..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onSearch={handleSearch}
            style={{ width: 300 }}
            enterButton={<SearchOutlined />}
          />
          <Select
            placeholder="实体类型"
            value={selectedEntityType}
            onChange={setSelectedEntityType}
            style={{ width: 150 }}
            allowClear
          >
            {Object.entries(ENTITY_TYPES).map(([key, config]) => (
              <Option key={key} value={key}>
                {config.icon} {config.label}
              </Option>
            ))}
          </Select>
        </Space>

        <Tabs
          items={[
            {
              key: 'graph',
              label: '图谱视图',
              icon: <ExpandOutlined />,
              children: (
                <div style={{ position: 'relative' }}>
                  {loading ? (
                    <Spin style={{ display: 'block', margin: '100px auto' }} />
                  ) : entities.length === 0 ? (
                    <Empty description="暂无实体数据" />
                  ) : (
                    <canvas
                      ref={canvasRef}
                      width={700}
                      height={400}
                      style={{ border: '1px solid #303030', borderRadius: 8 }}
                    />
                  )}
                </div>
              )
            },
            {
              key: 'entities',
              label: `实体列表 (${entities.length})`,
              icon: <UserOutlined />,
              children: (
                <Table
                  dataSource={entities}
                  columns={entityColumns}
                  rowKey="id"
                  loading={loading}
                  size="small"
                  pagination={{ pageSize: 10 }}
                />
              )
            },
            {
              key: 'relations',
              label: `关系列表 (${relations.length})`,
              icon: <LinkOutlined />,
              children: (
                <Table
                  dataSource={relations}
                  columns={relationColumns}
                  rowKey="id"
                  loading={loading}
                  size="small"
                  pagination={{ pageSize: 10 }}
                />
              )
            }
          ]}
        />
      </Card>

      <Drawer
        title={`实体详情: ${selectedEntity?.name}`}
        placement="right"
        width={500}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {selectedEntity && (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="ID">{selectedEntity.id}</Descriptions.Item>
              <Descriptions.Item label="名称">{selectedEntity.name}</Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={ENTITY_TYPES[selectedEntity.entity_type]?.color}>
                  {ENTITY_TYPES[selectedEntity.entity_type]?.label}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="置信度">{(selectedEntity.confidence * 100).toFixed(0)}%</Descriptions.Item>
              <Descriptions.Item label="访问次数">{selectedEntity.access_count}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{selectedEntity.created_at}</Descriptions.Item>
              <Descriptions.Item label="属性">
                <pre style={{ margin: 0 }}>{JSON.stringify(selectedEntity.attributes, null, 2)}</pre>
              </Descriptions.Item>
            </Descriptions>

            {entityContext && entityContext.relations.length > 0 && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>关联关系</Title>
                {entityContext.relations.map(rel => (
                  <Tag key={rel.id} color={RELATION_TYPES[rel.relation_type]?.color}>
                    {rel.relation_type}
                  </Tag>
                ))}
              </>
            )}

            {entityContext && entityContext.related_entities.length > 0 && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>关联实体</Title>
                <Space wrap>
                  {entityContext.related_entities.map(entity => (
                    <Tag key={entity.id} color={ENTITY_TYPES[entity.entity_type]?.color}>
                      {ENTITY_TYPES[entity.entity_type]?.icon} {entity.name}
                    </Tag>
                  ))}
                </Space>
              </>
            )}
          </>
        )}
      </Drawer>

      <Modal
        title="添加实体"
        open={addEntityModalOpen}
        onCancel={() => setAddEntityModalOpen(false)}
        footer={null}
      >
        <Form form={addEntityForm} onFinish={handleAddEntity} layout="vertical">
          <Form.Item name="name" label="实体名称" rules={[{ required: true }]}>
            <Input placeholder="输入实体名称" />
          </Form.Item>
          <Form.Item name="type" label="实体类型" rules={[{ required: true }]}>
            <Select placeholder="选择实体类型">
              {Object.entries(ENTITY_TYPES).map(([key, config]) => (
                <Option key={key} value={key}>
                  {config.icon} {config.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="attributes" label="属性 (JSON)">
            <Input.TextArea placeholder='{"key": "value"}' rows={3} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">添加</Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="添加关系"
        open={addRelationModalOpen}
        onCancel={() => setAddRelationModalOpen(false)}
        footer={null}
      >
        <Form form={addRelationForm} onFinish={handleAddRelation} layout="vertical">
          <Form.Item name="source" label="源实体名称" rules={[{ required: true }]}>
            <Input placeholder="输入源实体名称" />
          </Form.Item>
          <Form.Item name="target" label="目标实体名称" rules={[{ required: true }]}>
            <Input placeholder="输入目标实体名称" />
          </Form.Item>
          <Form.Item name="type" label="关系类型" rules={[{ required: true }]}>
            <Select placeholder="选择关系类型">
              {Object.entries(RELATION_TYPES).map(([key, config]) => (
                <Option key={key} value={key}>
                  {config.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="evidence" label="证据">
            <Input.TextArea placeholder="输入证据文本" rows={2} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">添加</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
