import { useState, useEffect } from 'react'
import { Card, Button, Input, Space, List, Tag, Typography, message, Alert, Popconfirm, Progress } from 'antd'
import { FolderOutlined, CodeOutlined, DeleteOutlined, SyncOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { API_BASE_URL } from '../services/api'

const { Text } = Typography

const API_BASE = API_BASE_URL  // 保持向后兼容

interface Project {
  name: string
  path: string
  tech_stack: {
    language: string
    frameworks: string[]
    libraries: string[]
    ui_frameworks: string[]
  }
  indexed_at?: string
}

interface IndexingStatus {
  status: 'idle' | 'scanning' | 'indexing' | 'completed' | 'error'
  message: string
  progress: number
}

export default function ProjectContext() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [searchPath, setSearchPath] = useState('')
  const [indexingStatus, setIndexingStatus] = useState<IndexingStatus>({
    status: 'idle',
    message: '',
    progress: 0
  })

  // 加载已索引的项目
  const loadProjects = async () => {
    try {
      const response = await fetch(`${API_BASE}/context/projects`)
      const data = await response.json()
      if (data.success) {
        setProjects(data.projects || [])
      }
    } catch (error) {
      console.error('加载项目失败:', error)
    }
  }

  useEffect(() => {
    loadProjects()
  }, [])

  // 扫描并索引项目
  const handleScanProject = async () => {
    if (!searchPath.trim()) {
      message.error('请输入项目路径')
      return
    }

    setLoading(true)
    setIndexingStatus({ status: 'scanning', message: '正在扫描项目...', progress: 30 })

    try {
      // 1. 扫描项目
      const scanResponse = await fetch(`${API_BASE}/context/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: searchPath })
      })
      const scanData = await scanResponse.json()

      if (!scanData.success) {
        throw new Error(scanData.message || '扫描失败')
      }

      setIndexingStatus({ status: 'indexing', message: '正在构建索引...', progress: 60 })

      // 2. 索引项目
      const indexResponse = await fetch(`${API_BASE}/context/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          project_path: searchPath,
          force_reindex: false 
        })
      })
      const indexData = await indexResponse.json()

      if (!indexData.success) {
        throw new Error(indexData.message || '索引失败')
      }

      setIndexingStatus({ 
        status: 'completed', 
        message: `索引完成！${indexData.summary?.files_indexed || 0} 个文件`,
        progress: 100 
      })

      message.success(`项目索引成功：${indexData.summary?.files_indexed || 0} 个文件，${indexData.summary?.symbols_found || 0} 个符号`)
      loadProjects()
      setSearchPath('')

      // 3 秒后重置状态
      setTimeout(() => {
        setIndexingStatus({ status: 'idle', message: '', progress: 0 })
      }, 3000)

    } catch (error: any) {
      setIndexingStatus({ status: 'error', message: error.message, progress: 0 })
      message.error(`操作失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  // 移除项目
  const handleRemoveProject = async (path: string) => {
    try {
      const response = await fetch(`${API_BASE}/context/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: path })
      })
      const data = await response.json()

      if (data.success) {
        message.success('已移除项目索引')
        loadProjects()
      } else {
        message.error('移除失败')
      }
    } catch (error) {
      console.error('移除项目失败:', error)
      message.error('操作失败')
    }
  }

  // 格式化时间
  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '未知'
    return new Date(timeStr).toLocaleString('zh-CN')
  }

  return (
    <div style={{ padding: 24 }}>
      <Card 
        title={
          <Space>
            <CodeOutlined />
            <span>项目上下文管理</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
          <Input
            placeholder="项目路径，例如：C:/Users/JHJ/Desktop/finetune-platform"
            value={searchPath}
            onChange={(e) => setSearchPath(e.target.value)}
            onPressEnter={handleScanProject}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<FolderOutlined />}
            onClick={handleScanProject}
            loading={loading}
          >
            扫描项目
          </Button>
        </Space.Compact>

        {/* 索引状态 */}
        {indexingStatus.status !== 'idle' && (
          <Alert
            message={indexingStatus.message}
            type={indexingStatus.status === 'error' ? 'error' : indexingStatus.status === 'completed' ? 'success' : 'info'}
            showIcon
            icon={indexingStatus.status === 'completed' ? <CheckCircleOutlined /> : indexingStatus.status === 'error' ? undefined : <SyncOutlined spin />}
            style={{ marginTop: 12 }}
          />
        )}

        {indexingStatus.status === 'scanning' || indexingStatus.status === 'indexing' ? (
          <Progress 
            percent={indexingStatus.progress} 
            status="active" 
            style={{ marginTop: 12 }} 
          />
        ) : null}
      </Card>

      {/* 已索引的项目列表 */}
      <Card title={`已索引的项目 (${projects.length})`}>
        {projects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
            <CodeOutlined style={{ fontSize: 48, marginBottom: 16, display: 'block' }} />
            <Text>暂无已索引的项目</Text>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">输入项目路径并点击"扫描项目"开始</Text>
            </div>
          </div>
        ) : (
          <List
            dataSource={projects}
            renderItem={(project) => (
              <List.Item
                actions={[
                  <Popconfirm
                    title="确定要移除该项目索引吗？"
                    onConfirm={() => handleRemoveProject(project.path)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      移除
                    </Button>
                  </Popconfirm>
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <CodeOutlined />
                      <Text strong>{project.name}</Text>
                    </Space>
                  }
                  description={
                    <div style={{ marginTop: 8 }}>
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>{project.path}</Text>
                        <Space wrap>
                          <Tag color="blue">{project.tech_stack?.language || 'unknown'}</Tag>
                          {project.tech_stack?.frameworks?.map((fw: string) => (
                            <Tag key={fw} color="green">{fw}</Tag>
                          ))}
                          {project.tech_stack?.ui_frameworks?.map((fw: string) => (
                            <Tag key={fw} color="purple">{fw}</Tag>
                          ))}
                          {project.tech_stack?.libraries?.slice(0, 3).map((lib: string) => (
                            <Tag key={lib} color="orange">{lib}</Tag>
                          ))}
                        </Space>
                        {project.indexed_at && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            索引时间：{formatTime(project.indexed_at)}
                          </Text>
                        )}
                      </Space>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 使用说明 */}
      <Card title="使用说明" style={{ marginTop: 16 }}>
        <Typography>
          <ul>
            <li>输入项目根目录路径，点击"扫描项目"开始分析</li>
            <li>系统会自动检测技术栈、分析项目结构、提取代码符号</li>
            <li>索引完成后，在聊天时启用"项目上下文"开关，AI 将了解你的项目</li>
            <li>支持的语言：Python, JavaScript, TypeScript, Java 等</li>
            <li>AI 会根据你的问题，智能检索相关代码文件和项目信息</li>
          </ul>
        </Typography>
      </Card>
    </div>
  )
}
