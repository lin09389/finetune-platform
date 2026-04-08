import { useState, useEffect } from 'react'
import { Card, Button, Upload, Space, Progress, Tag, List, Typography, App, Alert } from 'antd'
import { InboxOutlined, DeleteOutlined, FileTextOutlined, CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd/es/upload/interface'
import { API_BASE_URL } from '../services/api'

const { Dragger } = Upload
const { Text } = Typography

interface DocumentItem {
  doc_id: string
  source: string
  chunk_count: number
  uploaded_at: string
}

interface CollectionInfo {
  name: string
  count: number
  documents: DocumentItem[]
}

interface EmbedderStatus {
  loaded: boolean
  model_name?: string
  dimension?: number
  error?: string
}

export default function KnowledgeBase() {
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadStatus, setUploadStatus] = useState<string>('')
  const [collectionId, setCollectionId] = useState('default')
  const [collectionInfo, setCollectionInfo] = useState<CollectionInfo | null>(null)
  const [embedderStatus, setEmbedderStatus] = useState<EmbedderStatus | null>(null)
  const [preloading, setPreloading] = useState(false)

  useEffect(() => {
    checkEmbedderStatus()
  }, [])

  const checkEmbedderStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/embedder/status`, {
        signal: AbortSignal.timeout(5000)
      })
      if (response.ok) {
        const data = await response.json()
        setEmbedderStatus(data)
      }
    } catch (error) {
      setEmbedderStatus({ loaded: false, error: '无法连接到服务器' })
    }
  }

  const preloadEmbedder = async () => {
    setPreloading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/embedder/preload`, {
        method: 'POST',
        signal: AbortSignal.timeout(120000)
      })
      if (response.ok) {
        const data = await response.json()
        message.success(`嵌入模型已加载，维度: ${data.dimension}`)
        checkEmbedderStatus()
      } else {
        const error = await response.json()
        message.error(error.detail || '预加载失败')
      }
    } catch (error: any) {
      message.error(error.message || '预加载失败')
    } finally {
      setPreloading(false)
    }
  }

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.pdf,.docx,.doc,.txt,.md,.markdown',
    beforeUpload: (file) => {
      const validTypes = ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown']
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      
      if (!validTypes.includes(ext)) {
        message.error(`不支持的文件格式：${ext}`)
        return false
      }
      
      if (file.size > 50 * 1024 * 1024) {
        message.error('文件大小不能超过 50MB')
        return false
      }
      
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      setUploadProgress(0)
      setUploadStatus('准备上传...')
      
      const controller = new AbortController()
      const timeoutId = setTimeout(() => {
        controller.abort()
        message.error('上传超时，请检查服务器状态或尝试较小的文件')
        setUploading(false)
        setUploadProgress(0)
        setUploadStatus('')
      }, 60000)

      try {
        const progressInterval = setInterval(() => {
          setUploadProgress(prev => {
            if (prev >= 85) return prev
            return prev + 5
          })
        }, 1000)

        const formData = new FormData()
        formData.append('collection_id', collectionId)
        formData.append('file', file as File)
        
        setUploadStatus('正在上传文件...')
        
        const response = await fetch(`${API_BASE_URL}/knowledge/upload`, {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        })
        
        clearInterval(progressInterval)
        clearTimeout(timeoutId)
        
        if (!response.ok) {
          let errorMessage = '上传失败'
          try {
            const errorData = await response.json()
            errorMessage = errorData.detail || errorMessage
          } catch {
            errorMessage = `服务器错误: ${response.status}`
          }
          throw new Error(errorMessage)
        }
        
        setUploadProgress(90)
        setUploadStatus('正在处理文档...')
        
        const result = await response.json()
        setUploadProgress(100)
        setUploadStatus('上传成功!')
        
        message.success(`文档上传成功：${result.file_name}, ${result.chunk_count} 个文本块`)
        
        loadCollectionInfo()
        
        onSuccess?.(result)
      } catch (error: any) {
        clearTimeout(timeoutId)
        if (error.name === 'AbortError') {
          message.error('上传超时，请检查服务器状态')
        } else {
          message.error(error.message || '上传失败')
        }
        onError?.(error)
      } finally {
        setTimeout(() => {
          setUploading(false)
          setUploadProgress(0)
          setUploadStatus('')
        }, 1000)
      }
    },
  }

  const loadCollectionInfo = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections/${collectionId}`, {
        signal: AbortSignal.timeout(10000)
      })
      if (response.ok) {
        const data = await response.json()
        setCollectionInfo(data)
      }
    } catch (error) {
      console.error('Failed to load collection info:', error)
    }
  }

  const handleDelete = async (docId: string) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/knowledge/collections/${collectionId}/documents/${docId}`,
        { method: 'DELETE' }
      )
      
      if (response.ok) {
        message.success('文档已删除')
        loadCollectionInfo()
      } else {
        message.error('删除失败')
      }
    } catch (error) {
      message.error('删除失败')
    }
  }

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">RAG 知识库</div>

        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {embedderStatus && !embedderStatus.loaded && (
            <Alert
              message="嵌入模型未加载"
              description={
                <Space direction="vertical">
                  <span>首次上传文档需要加载嵌入模型（约 400MB），这可能需要几分钟时间。</span>
                  <span style={{ color: '#999' }}>{embedderStatus.error}</span>
                </Space>
              }
              type="warning"
              showIcon
              action={
                <Button size="small" type="primary" onClick={preloadEmbedder} loading={preloading}>
                  {preloading ? '加载中...' : '预加载模型'}
                </Button>
              }
            />
          )}

          {embedderStatus && embedderStatus.loaded && (
            <Alert
              message={`嵌入模型已就绪 (${embedderStatus.model_name}, ${embedderStatus.dimension}维)`}
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
            />
          )}

          <Card title="上传文档" variant="borderless">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <Text>工作空间 ID:</Text>
                <input
                  value={collectionId}
                  onChange={(e) => setCollectionId(e.target.value)}
                  style={{ padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                  placeholder="输入工作空间 ID"
                />
              </Space>
              
              <Dragger {...uploadProps} disabled={uploading}>
                <p className="ant-upload-drag-icon">
                  {uploading ? <LoadingOutlined /> : <InboxOutlined />}
                </p>
                <p className="ant-upload-text">
                  {uploading ? '上传处理中...' : '点击或拖拽文件到此区域上传'}
                </p>
                <p className="ant-upload-hint">
                  支持格式：PDF, DOCX, TXT, MD | 最大 50MB
                </p>
              </Dragger>
              
              {uploading && (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Progress percent={uploadProgress} status="active" />
                  <Text type="secondary">{uploadStatus}</Text>
                </Space>
              )}
            </Space>
          </Card>

          <Card 
            title="文档列表" 
            variant="borderless"
            extra={
              <Button onClick={loadCollectionInfo}>刷新</Button>
            }
          >
            {collectionInfo && collectionInfo.documents.length > 0 ? (
              <List
                dataSource={collectionInfo.documents}
                renderItem={(doc) => (
                  <List.Item
                    actions={[
                      <Button
                        key="delete"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(doc.doc_id)}
                      >
                        删除
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <FileTextOutlined />
                          <span>{doc.source}</span>
                          <Tag color="blue">{doc.chunk_count} 块</Tag>
                        </Space>
                      }
                      description={
                        <div>
                          <div>ID: {doc.doc_id}</div>
                          <div>上传时间：{new Date(doc.uploaded_at).toLocaleString('zh-CN')}</div>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                暂无文档，请上传
              </div>
            )}
          </Card>

          <Card title="使用说明" variant="borderless" size="small">
            <div style={{ color: '#666', fontSize: 13 }}>
              <p><strong>1. 上传文档:</strong> 选择工作空间 ID，上传 PDF/DOCX/TXT/MD 文件</p>
              <p><strong>2. 自动处理:</strong> 系统会自动解析文档、分块、向量化并存储</p>
              <p><strong>3. 语义搜索:</strong> 使用自然语言查询，系统会检索相关文档片段</p>
              <p><strong>4. RAG 聊天:</strong> 在聊天时使用 RAG 增强，基于知识库内容回答</p>
              <p><strong>注意:</strong> 首次上传需要下载嵌入模型，请耐心等待</p>
            </div>
          </Card>
        </Space>
      </div>
    </div>
  )
}
