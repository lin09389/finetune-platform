import { useState } from 'react'
import { Card, Button, Upload, Space, Progress, Tag, List, Typography, App } from 'antd'
import { InboxOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons'
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

export default function KnowledgeBase() {
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [collectionId, setCollectionId] = useState('default')
  const [collectionInfo, setCollectionInfo] = useState<CollectionInfo | null>(null)

  // 上传文件
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
      
      if (file.size > 10 * 1024 * 1024) {
        message.error('文件大小不能超过 10MB')
        return false
      }
      
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      setUploadProgress(0)
      
      try {
        // 模拟进度
        const interval = setInterval(() => {
          setUploadProgress(prev => {
            if (prev >= 90) {
              clearInterval(interval)
              return 90
            }
            return prev + 10
          })
        }, 200)
        
        const formData = new FormData()
        formData.append('collection_id', collectionId)
        formData.append('file', file as File)
        
        const response = await fetch(`${API_BASE_URL}/v2/knowledge/upload`, {
          method: 'POST',
          body: formData,
        })
        
        clearInterval(interval)
        
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || '上传失败')
        }
        
        const result = await response.json()
        setUploadProgress(100)
        
        message.success(`文档上传成功：${result.file_name}, ${result.chunk_count} 个文本块`)
        
        // 刷新集合信息
        loadCollectionInfo()
        
        onSuccess?.(result)
      } catch (error: any) {
        message.error(error.message || '上传失败')
        onError?.(error)
      } finally {
        setTimeout(() => {
          setUploading(false)
          setUploadProgress(0)
        }, 500)
      }
    },
  }

  // 加载集合信息
  const loadCollectionInfo = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/v2/knowledge/collections/${collectionId}`)
      if (response.ok) {
        const data = await response.json()
        setCollectionInfo(data)
      }
    } catch (error) {
      console.error('Failed to load collection info:', error)
    }
  }

  // 删除文档
  const handleDelete = async (docId: string) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/v2/knowledge/collections/${collectionId}/documents/${docId}`,
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
          {/* 上传区域 */}
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
              
              <Dragger {...uploadProps}>
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                <p className="ant-upload-hint">
                  支持格式：PDF, DOCX, TXT, MD | 最大 10MB
                </p>
              </Dragger>
              
              {uploading && (
                <Progress percent={uploadProgress} status="active" />
              )}
            </Space>
          </Card>

          {/* 文档列表 */}
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

          {/* 使用说明 */}
          <Card title="使用说明" variant="borderless" size="small">
            <div style={{ color: '#666', fontSize: 13 }}>
              <p><strong>1. 上传文档:</strong> 选择工作空间 ID，上传 PDF/DOCX/TXT/MD 文件</p>
              <p><strong>2. 自动处理:</strong> 系统会自动解析文档、分块、向量化并存储</p>
              <p><strong>3. 语义搜索:</strong> 使用自然语言查询，系统会检索相关文档片段</p>
              <p><strong>4. RAG 聊天:</strong> 在聊天时使用 RAG 增强，基于知识库内容回答</p>
            </div>
          </Card>
        </Space>
      </div>
    </div>
  )
}
