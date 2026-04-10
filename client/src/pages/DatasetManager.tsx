import { useEffect, useState, useRef } from 'react'
import { Table, Button, Space, Tag, message, Drawer, Alert, Popconfirm } from 'antd'
import { DeleteOutlined, UploadOutlined, FolderOpenOutlined, EyeOutlined, FileTextOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { getDatasetList, uploadDataset, deleteDataset, previewDataset } from '../services/api'
import type { DatasetInfo } from '../types'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './DatasetManager.module.css'
import glassStyles from '../components/shared/GlassCard.module.css'

export default function DatasetManager() {
  const { datasets, setDatasets, removeDataset, addDataset, backendStatus } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [previewVisible, setPreviewVisible] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewData, setPreviewData] = useState<{ total_samples: number; preview: unknown[] } | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const fetchDatasets = async () => {
    if (backendStatus !== 'connected') return
    setLoading(true)
    try {
      const list = await getDatasetList()
      setDatasets(list)
    } catch (error) {
      message.error('获取数据集列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDatasets()
  }, [backendStatus])

  const handleSelectFile = async () => {
    if (window.electronAPI) {
      // Electron 环境
      const filePath = await window.electronAPI.selectFile([
        { name: 'JSON/JSONL', extensions: ['json', 'jsonl'] }
      ])
      if (filePath) {
        try {
          setLoading(true)
          // 读取文件内容
          const fileData = await window.electronAPI.readFile(filePath)
          if (!fileData) {
            throw new Error('无法读取文件')
          }
          // 将 base64 转换为 Blob
          const byteCharacters = atob(fileData.data)
          const byteNumbers = new Array(byteCharacters.length)
          for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i)
          }
          const byteArray = new Uint8Array(byteNumbers)
          const blob = new Blob([byteArray])
          // 创建 File 对象
          const file = new File([blob], fileData.name, { type: 'application/json' })
          // 上传数据集
          const result = await uploadDataset(file)
          message.success('数据集上传成功')
          addDataset(result)
          fetchDatasets()
        } catch (error: any) {
          message.error(error.message || '数据集上传失败')
        } finally {
          setLoading(false)
        }
      }
    } else {
      // Web 环境 - 使用 file input
      fileInputRef.current?.click()
    }
  }

  const handleWebFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setLoading(true)
      const result = await uploadDataset(file)
      message.success('数据集上传成功')
      addDataset(result)
      fetchDatasets()
    } catch (error: any) {
      message.error(error.message || '数据集上传失败')
    } finally {
      setLoading(false)
      // 清空 input 以便再次选择同一文件
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleDelete = async (datasetId: string) => {
    try {
      await deleteDataset(datasetId)
      removeDataset(datasetId)
      message.success('数据集删除成功')
    } catch (error) {
      message.error('删除失败')
      fetchDatasets()
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`
    }
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const handlePreview = async (datasetId: string) => {
    setPreviewLoading(true)
    try {
      const data = await previewDataset(datasetId, 10)
      setPreviewData(data)
      setPreviewVisible(true)
    } catch (error) {
      message.error('预览失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  const columns = [
    {
      title: '数据集名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '格式',
      dataIndex: 'format',
      key: 'format',
      render: (format: string) => (
        <Tag color={format === 'json' ? 'blue' : 'green'}>
          {format.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '样本数',
      dataIndex: 'samples',
      key: 'samples',
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      render: (size: number) => formatSize(size),
    },
    {
      title: '上传时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: DatasetInfo) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => handlePreview(record.id)}
            loading={previewLoading}
          >
            预览
          </Button>
          <Button
            type="link"
            icon={<FolderOpenOutlined />}
            onClick={() => window.electronAPI?.openFolder(record.path)}
          >
            打开
          </Button>
          <Popconfirm
            title="确认删除?"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <MotionList className={styles.container} stagger={0.08}>
      {/* 隐藏的文件上传 input (用于 Web 环境) */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.jsonl"
        style={{ display: 'none' }}
        onChange={handleWebFileUpload}
      />
      <MotionItem>
      <div className={`${glassStyles.glassCard} ${styles.headerCard}`}>
        <h1 className={styles.title}>
          <FileTextOutlined />
          数据集管理
        </h1>
        <Button
          type="primary"
          icon={<UploadOutlined />}
          onClick={handleSelectFile}
          loading={loading}
          size="large"
          style={{ borderRadius: 8 }}
        >
          上传数据集
        </Button>
      </div>
      </MotionItem>

      <MotionItem>
      <div className={`${glassStyles.glassCard} ${styles.tableCard}`}>
        <Alert
          message="数据集格式说明"
          description={
            <div>
              支持 JSON 和 JSONL 格式。每行一条对话数据，格式如下：
              <pre className={styles.codePreview} style={{ marginTop: 8, marginBottom: 0, padding: 12 }}>
{`[
  {"role": "user", "content": "你好"},
  {"role": "assistant", "content": "你好！有什么可以帮你的？"}
]`}
              </pre>
            </div>
          }
          type="info"
          showIcon
          style={{ marginBottom: 24, borderRadius: 8, background: 'rgba(22, 119, 255, 0.05)', border: '1px solid rgba(22, 119, 255, 0.1)' }}
        />

        {backendStatus !== 'connected' ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            后端服务未连接，请先启动应用
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={datasets}
            rowKey="id"
            locale={{ emptyText: '暂无数据集，请上传后使用' }}
            loading={loading}
          />
        )}
      </div>
      </MotionItem>

      <Drawer
        title="数据集预览"
        placement="right"
        width={600}
        open={previewVisible}
        onClose={() => setPreviewVisible(false)}
        className="glass-drawer"
      >
        {previewData && (
          <div style={{ paddingBottom: 24 }}>
            <div style={{ 
              marginBottom: 16, 
              padding: '12px 16px', 
              background: 'rgba(22, 119, 255, 0.05)', 
              borderRadius: 8,
              border: '1px solid rgba(22, 119, 255, 0.1)',
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}>
              <strong style={{ color: 'var(--text-primary)' }}>总样本数:</strong> 
              <span style={{ color: 'var(--accent-primary)', fontSize: 16, fontWeight: 500 }}>{previewData.total_samples}</span>
            </div>
            <pre className={styles.codePreview}>
              {JSON.stringify(previewData.preview, null, 2)}
            </pre>
          </div>
        )}
      </Drawer>
    </MotionList>
  )
}
