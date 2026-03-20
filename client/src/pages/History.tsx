import { useState, useEffect } from 'react'
import { Table, Tag, Button, Descriptions, Space, message, Drawer } from 'antd'
import { DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { getTrainingHistory } from '../services/api'
import type { TrainingRecord } from '../types'

export default function History() {
  const { trainingRecords, setTrainingRecords, removeTrainingRecord } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<TrainingRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  useEffect(() => {
    loadRecords()
  }, [])

  const loadRecords = async () => {
    setLoading(true)
    try {
      const records = await getTrainingHistory()
      setTrainingRecords(records)
    } catch (error) {
      console.error('Failed to load records:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    // TODO: Add delete API when available
    removeTrainingRecord(id)
    message.success('记录已删除')
  }

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      running: { color: 'blue', text: '训练中' },
      completed: { color: 'green', text: '已完成' },
      failed: { color: 'red', text: '失败' },
      stopped: { color: 'gray', text: '已停止' },
    }
    const config = statusMap[status] || { color: 'default', text: status }
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const getMethodTag = (method: string) => {
    const methodMap: Record<string, { color: string; text: string }> = {
      lora: { color: 'blue', text: 'LoRA' },
      qlora: { color: 'purple', text: 'QLoRA' },
      full: { color: 'orange', text: '全量' },
    }
    const config = methodMap[method] || { color: 'default', text: method }
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const calculateDuration = (start: string, end?: string) => {
    if (!end) return '-'
    const duration = new Date(end).getTime() - new Date(start).getTime()
    const minutes = Math.floor(duration / 60000)
    const seconds = Math.floor((duration % 60000) / 1000)
    return `${minutes}分${seconds}秒`
  }

  const columns = [
    {
      title: '训练 ID',
      dataIndex: 'id',
      key: 'id',
      ellipsis: true,
    },
    {
      title: '模型',
      dataIndex: 'modelName',
      key: 'modelName',
    },
    {
      title: '数据集',
      dataIndex: 'datasetName',
      key: 'datasetName',
    },
    {
      title: '训练方法',
      dataIndex: 'method',
      key: 'method',
      render: (method: string) => getMethodTag(method),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '开始时间',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: TrainingRecord) => (
        <Space>
          <Button
            icon={<EyeOutlined />}
            size="small"
            onClick={() => {
              setSelectedRecord(record)
              setDetailOpen(true)
            }}
          >
            详情
          </Button>
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">训练历史</div>

        <Table
          columns={columns}
          dataSource={trainingRecords}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />

        <Drawer
          title="训练详情"
          placement="right"
          width={600}
          open={detailOpen}
          onClose={() => setDetailOpen(false)}
          extra={[
            <Button key="close" onClick={() => setDetailOpen(false)}>
              关闭
            </Button>,
          ]}
        >
          {selectedRecord && (
            <Descriptions column={1} size="small">
              <Descriptions.Item label="训练 ID">{selectedRecord.id}</Descriptions.Item>
              <Descriptions.Item label="模型">{selectedRecord.modelName}</Descriptions.Item>
              <Descriptions.Item label="数据集">{selectedRecord.datasetName}</Descriptions.Item>
              <Descriptions.Item label="训练方法">{getMethodTag(selectedRecord.method)}</Descriptions.Item>
              <Descriptions.Item label="状态">{getStatusTag(selectedRecord.status)}</Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {new Date(selectedRecord.startTime).toLocaleString('zh-CN')}
              </Descriptions.Item>
              {selectedRecord.endTime && (
                <Descriptions.Item label="结束时间">
                  {new Date(selectedRecord.endTime).toLocaleString('zh-CN')}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="训练耗时">
                {calculateDuration(selectedRecord.startTime, selectedRecord.endTime)}
              </Descriptions.Item>
              <Descriptions.Item label="输出路径">{selectedRecord.outputPath}</Descriptions.Item>
              <Descriptions.Item label="训练配置">
                <div style={{ fontSize: 12 }}>
                  <div>Rank: {selectedRecord.config?.rank || '-'}</div>
                  <div>Alpha: {selectedRecord.config?.alpha || '-'}</div>
                  <div>Learning Rate: {selectedRecord.config?.learningRate?.toExponential(2) || '-'}</div>
                  <div>Epochs: {selectedRecord.config?.epochs || '-'}</div>
                  <div>Batch Size: {selectedRecord.config?.batchSize || '-'}</div>
                </div>
              </Descriptions.Item>
            </Descriptions>
          )}
        </Drawer>
      </div>
    </div>
  )
}
