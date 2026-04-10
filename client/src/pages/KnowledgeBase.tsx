import { useState, useEffect } from 'react'
import { Button, Upload, Progress, Tag, App } from 'antd'
import { InboxOutlined, DeleteOutlined, FileTextOutlined, CheckCircleOutlined, LoadingOutlined, BookOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd/es/upload/interface'
import { API_BASE_URL } from '../services/api'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './KnowledgeBase.module.css'
import glassStyles from '../components/shared/GlassCard.module.css'

const { Dragger } = Upload

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
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
      {/* 标题栏 */}
      <div className={`${glassStyles.glassCard} ${styles.headerCard}`}>
        <h1 className={styles.title}>
          <BookOutlined />
          RAG 知识库
        </h1>
        {embedderStatus && (
          <div className={`${styles.statusBanner} ${embedderStatus.loaded ? styles.statusBannerSuccess : styles.statusBannerWarning}`}>
            {embedderStatus.loaded ? (
              <>
                <CheckCircleOutlined />
                <span>嵌入模型就绪 · {embedderStatus.model_name} · {embedderStatus.dimension}维</span>
              </>
            ) : (
              <>
                <WarningOutlined />
                <span>嵌入模型未加载</span>
                <Button size="small" type="primary" onClick={preloadEmbedder} loading={preloading} style={{ marginLeft: 8 }}>
                  {preloading ? '加载中...' : '立即加载'}
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {/* 上传文档 */}
      <div className={`${glassStyles.glassCard} ${styles.card}`}>
        <div className={styles.cardTitle}>上传文档</div>

        <div className={styles.workspaceInput}>
          <span>工作空间 ID：</span>
          <input
            value={collectionId}
            onChange={(e) => setCollectionId(e.target.value)}
            placeholder="输入工作空间 ID"
          />
        </div>

        <div className={styles.draggerWrap}>
          <Dragger {...uploadProps} disabled={uploading}>
            <p className="ant-upload-drag-icon">
              {uploading ? <LoadingOutlined style={{ fontSize: 40, color: 'var(--accent-primary)' }} /> : <InboxOutlined style={{ fontSize: 40, color: 'var(--accent-primary)' }} />}
            </p>
            <p className="ant-upload-text" style={{ color: 'var(--text-primary)', fontSize: 16 }}>
              {uploading ? '上传处理中...' : '点击或拖拽文件到此区域上传'}
            </p>
            <p className="ant-upload-hint" style={{ color: 'var(--text-secondary)' }}>
              支持格式：PDF, DOCX, TXT, MD | 最大 50MB
            </p>
          </Dragger>
        </div>

        {uploading && (
          <div className={styles.progressArea}>
            <Progress percent={uploadProgress} status="active" strokeColor="var(--accent-primary)" />
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 8, textAlign: 'center' }}>{uploadStatus}</div>
          </div>
        )}
      </div>

      {/* 文档列表 */}
      <div className={`${glassStyles.glassCard} ${styles.card}`}>
        <div className={styles.cardTitle}>
          <span>文档列表</span>
          <Button icon={<ReloadOutlined />} onClick={loadCollectionInfo} size="small">刷新</Button>
        </div>

        {collectionInfo && collectionInfo.documents.length > 0 ? (
          collectionInfo.documents.map((doc) => (
            <div key={doc.doc_id} className={styles.docItem}>
              <div className={styles.docItemInfo}>
                <div className={styles.docItemName}>
                  <FileTextOutlined style={{ color: 'var(--accent-primary)' }} />
                  <span>{doc.source}</span>
                  <Tag color="blue" style={{ borderRadius: 4 }}>{doc.chunk_count} 块</Tag>
                </div>
                <div className={styles.docItemMeta}>
                  <span>ID: {doc.doc_id}</span>
                  <span>上传于 {new Date(doc.uploaded_at).toLocaleString('zh-CN')}</span>
                </div>
              </div>
              <Button
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(doc.doc_id)}
                size="small"
              >
                删除
              </Button>
            </div>
          ))
        ) : (
          <div className={styles.emptyState}>暂无文档，请上传知识库文件</div>
        )}
      </div>

      {/* 使用说明 */}
      <div className={`${glassStyles.glassCard} ${styles.helpCard}`}>
        <div className={styles.cardTitle} style={{ marginBottom: 16 }}>使用说明</div>
        <ol className={styles.helpList}>
          <li><strong>上传文档：</strong>选择工作空间 ID，上传 PDF / DOCX / TXT / MD 文件</li>
          <li><strong>自动处理：</strong>系统自动解析文档、分块、向量化并存储</li>
          <li><strong>语义搜索：</strong>使用自然语言查询，检索相关文档片段</li>
          <li><strong>RAG 聊天：</strong>在聊天时启用 RAG 增强，基于知识库内容回答</li>
          <li><strong>注意：</strong>首次上传需要下载嵌入模型（约 400MB），请耐心等待</li>
        </ol>
      </div>
      </MotionItem>
    </MotionList>
  )
}
