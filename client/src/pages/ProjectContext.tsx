import { useState, useEffect } from 'react'
import { Button, Input, Tag, message, Popconfirm, Progress } from 'antd'
import {
  FolderOutlined,
  CodeOutlined,
  DeleteOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { API_BASE_URL } from '../services/api'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './ProjectContext.module.css'

const API_BASE = API_BASE_URL

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
    progress: 0,
  })

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

  const handleScanProject = async () => {
    if (!searchPath.trim()) {
      message.error('请输入项目路径')
      return
    }

    setLoading(true)
    setIndexingStatus({ status: 'scanning', message: '正在扫描项目...', progress: 30 })

    try {
      const scanResponse = await fetch(`${API_BASE}/context/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: searchPath }),
      })
      const scanData = await scanResponse.json()
      if (!scanData.success) throw new Error(scanData.message || '扫描失败')

      setIndexingStatus({ status: 'indexing', message: '正在构建索引...', progress: 60 })

      const indexResponse = await fetch(`${API_BASE}/context/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: searchPath, force_reindex: false }),
      })
      const indexData = await indexResponse.json()
      if (!indexData.success) throw new Error(indexData.message || '索引失败')

      setIndexingStatus({
        status: 'completed',
        message: `索引完成！${indexData.summary?.files_indexed || 0} 个文件`,
        progress: 100,
      })
      message.success(
        `项目索引成功：${indexData.summary?.files_indexed || 0} 个文件，${indexData.summary?.symbols_found || 0} 个符号`
      )
      loadProjects()
      setSearchPath('')
      setTimeout(() => setIndexingStatus({ status: 'idle', message: '', progress: 0 }), 3000)
    } catch (error: any) {
      setIndexingStatus({ status: 'error', message: error.message, progress: 0 })
      message.error(`操作失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleRemoveProject = async (path: string) => {
    try {
      const response = await fetch(`${API_BASE}/context/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: path }),
      })
      const data = await response.json()
      if (data.success) {
        message.success('已移除项目索引')
        loadProjects()
      } else {
        message.error('移除失败')
      }
    } catch (error) {
      message.error('操作失败')
    }
  }

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '未知'
    return new Date(timeStr).toLocaleString('zh-CN')
  }

  const statusClass =
    indexingStatus.status === 'error'
      ? styles.error
      : indexingStatus.status === 'completed'
      ? styles.success
      : styles.info

  const statusIcon =
    indexingStatus.status === 'completed' ? (
      <CheckCircleOutlined />
    ) : indexingStatus.status === 'error' ? (
      <WarningOutlined />
    ) : (
      <SyncOutlined spin />
    )

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
      {/* 标题栏 */}
      <div className={styles.headerCard}>
        <div className={styles.headerIcon}>
          <CodeOutlined />
        </div>
        <div>
          <h2 className={styles.headerTitle}>项目上下文管理</h2>
          <p className={styles.headerSubtitle}>Beta 能力：扫描并索引本地项目，但理解质量仍受仓库规模、语言和索引状态影响</p>
        </div>
      </div>

      {/* 扫描卡片 */}
      <div className={styles.scanCard}>
        <div className={styles.sectionTitle}>
          <FolderOutlined /> 扫描项目
        </div>
        <div style={{ marginBottom: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
          页面可用不代表索引一定完整；请以扫描结果、索引进度和后续检索效果为准。
        </div>
        <Input.Search
          placeholder="项目路径，例如：C:/Users/JHJ/Desktop/finetune-platform"
          value={searchPath}
          onChange={(e) => setSearchPath(e.target.value)}
          onPressEnter={handleScanProject}
          disabled={loading}
          enterButton={
            <Button type="primary" icon={<FolderOutlined />} loading={loading}>
              扫描项目
            </Button>
          }
          onSearch={handleScanProject}
          size="large"
        />

        {indexingStatus.status !== 'idle' && (
          <div className={`${styles.statusBanner} ${statusClass}`}>
            {statusIcon}
            <span>{indexingStatus.message}</span>
          </div>
        )}

        {(indexingStatus.status === 'scanning' || indexingStatus.status === 'indexing') && (
          <Progress percent={indexingStatus.progress} status="active" style={{ marginTop: 12 }} />
        )}
      </div>

      {/* 已索引项目列表 */}
      <div className={styles.projectsCard}>
        <div className={styles.cardTitleRow}>
          <div className={styles.sectionTitle} style={{ marginBottom: 0 }}>
            <CodeOutlined /> 已索引的项目（{projects.length}）
          </div>
        </div>

        {projects.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>📂</div>
            <div>暂无已索引的项目</div>
            <div style={{ fontSize: 13, marginTop: 4 }}>输入项目路径并点击"扫描项目"开始</div>
          </div>
        ) : (
          projects.map((project) => (
            <div key={project.path} className={styles.projectItem}>
              <div className={styles.projectInfo}>
                <div className={styles.projectName}>
                  <CodeOutlined />
                  <span>{project.name}</span>
                </div>
                <div className={styles.projectPath}>{project.path}</div>
                <div className={styles.projectTags}>
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
                </div>
                {project.indexed_at && (
                  <div className={styles.projectTime}>索引时间：{formatTime(project.indexed_at)}</div>
                )}
              </div>
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
            </div>
          ))
        )}
      </div>

      {/* 使用说明 */}
      <div className={styles.helpCard}>
        <div className={styles.sectionTitle}>使用说明</div>
        <ul className={styles.helpList}>
          <li>输入项目根目录路径，点击"扫描项目"开始分析</li>
          <li>系统会自动检测技术栈、分析项目结构、提取代码符号</li>
          <li>索引完成后，在聊天时启用"项目上下文"开关，AI 会基于已建立的索引理解你的项目</li>
          <li>支持的语言：Python、JavaScript、TypeScript、Java 等</li>
          <li>AI 会根据你的问题检索相关代码文件和项目信息，但结果覆盖度取决于索引质量</li>
        </ul>
      </div>
      </MotionItem>
    </MotionList>
  )
}
