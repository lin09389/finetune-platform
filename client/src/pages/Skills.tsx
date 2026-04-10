import { useState, useEffect } from 'react'
import { App } from 'antd'
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  CodeOutlined,
  FileOutlined,
  CloudOutlined,
  DatabaseOutlined,
  SettingOutlined,
  ToolOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { API_BASE_URL } from '../services/api'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './Skills.module.css'

interface SkillParameter {
  name: string
  type: string
  description: string
  required: boolean
  default?: any
}

interface Skill {
  name: string
  description: string
  category: string
  version: string
  tags: string[]
  parameters: SkillParameter[]
  priority: string
  enabled: boolean
}

interface ExecutionResult {
  execution_id: string
  skill_name: string
  status: string
  result?: any
  error?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
}

interface Stats {
  total_skills: number
  total_executions: number
  categories: Record<string, number>
  tags: Record<string, number>
}

const categoryIcons: Record<string, React.ReactNode> = {
  file: <FileOutlined />,
  network: <CloudOutlined />,
  data: <DatabaseOutlined />,
  code: <CodeOutlined />,
  system: <SettingOutlined />,
  utility: <ToolOutlined />,
  ai: <ApiOutlined />,
  custom: <AppstoreOutlined />,
}

const categoryTagCls: Record<string, string> = {
  file: 'tagBlue',
  network: 'tagGreen',
  data: 'tagOrange',
  code: 'tagPurple',
  system: 'tagRed',
  utility: 'tagCyan',
  ai: 'tagMagenta',
  custom: 'tagGray',
}

const priorityTagCls: Record<string, string> = {
  low: 'tagGray',
  normal: 'tagBlue',
  high: 'tagOrange',
  critical: 'tagRed',
}

export default function Skills() {
  const { message: appMessage } = App.useApp()
  const [skills, setSkills] = useState<Skill[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [executeModalOpen, setExecuteModalOpen] = useState(false)
  const [resultModalOpen, setResultModalOpen] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [executing, setExecuting] = useState(false)
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null)
  const [executeParams, setExecuteParams] = useState('{}')
  const [executePriority, setExecutePriority] = useState('normal')

  useEffect(() => {
    loadSkills()
    loadStats()
  }, [])

  const loadSkills = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills`)
      if (response.ok) {
        const data = await response.json()
        setSkills(data.skills || [])
      }
    } catch (error) {
      console.error('Failed to load skills:', error)
      appMessage.error('加载技能列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/stats`)
      if (response.ok) {
        const data = await response.json()
        setStats(data)
      }
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleScan = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/scan`, { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          appMessage.success(`扫描完成，发现 ${data.discovered} 个技能，注册 ${data.registered?.length || 0} 个`)
          loadSkills()
          loadStats()
        } else {
          appMessage.error(data.error || '扫描失败')
        }
      }
    } catch (error) {
      appMessage.error('扫描技能失败')
    }
  }

  const handleExecute = async () => {
    if (!selectedSkill) return
    let parsedParams: any = {}
    try { parsedParams = JSON.parse(executeParams) } catch {
      appMessage.error('请输入有效的 JSON')
      return
    }

    setExecuting(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_name: selectedSkill.name,
          parameters: parsedParams,
          priority: executePriority,
        }),
      })
      if (response.ok) {
        const data = await response.json()
        setExecutionResult(data)
        setResultModalOpen(true)
        setExecuteModalOpen(false)
        if (data.status === 'completed') {
          appMessage.success('技能执行成功')
        } else {
          appMessage.warning(`技能执行状态: ${data.status}`)
        }
      } else {
        const error = await response.json()
        appMessage.error(error.detail || '执行失败')
      }
    } catch (error) {
      appMessage.error('执行技能失败')
    } finally {
      setExecuting(false)
    }
  }

  const showDetail = (skill: Skill) => {
    setSelectedSkill(skill)
    setDetailModalOpen(true)
  }

  const showExecute = (skill: Skill) => {
    setSelectedSkill(skill)
    const defaultParams: Record<string, any> = {}
    skill.parameters.forEach((p) => {
      if (p.default !== undefined) defaultParams[p.name] = p.default
    })
    setExecuteParams(Object.keys(defaultParams).length > 0 ? JSON.stringify(defaultParams, null, 2) : '{}')
    setExecutePriority('normal')
    setExecuteModalOpen(true)
  }

  const filteredSkills = skills.filter((skill) => {
    const matchSearch = !searchText ||
      skill.name.toLowerCase().includes(searchText.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchText.toLowerCase()) ||
      skill.tags.some((t) => t.toLowerCase().includes(searchText.toLowerCase()))
    const matchCategory = !categoryFilter || skill.category === categoryFilter
    return matchSearch && matchCategory
  })

  const getTagCls = (map: Record<string, string>, key: string) => (styles as any)[map[key] || 'tagGray'] || styles.tagGray

  return (
    <MotionList className={styles.page} stagger={0.08}>
      <MotionItem>
      <div className={styles.pageHeader}>
        <h2 className={styles.pageTitle}><ThunderboltOutlined /> 技能管理</h2>
        <p className={styles.pageSubtitle}>管理和执行系统技能，支持文件操作、网络请求、代码执行等功能</p>
      </div>

      {/* Stats */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><ToolOutlined style={{ color: 'var(--primary)' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>总技能数</div>
            <div className={styles.statValue}>{stats?.total_skills || 0}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><PlayCircleOutlined style={{ color: 'var(--primary)' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>总执行次数</div>
            <div className={styles.statValue}>{stats?.total_executions || 0}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><AppstoreOutlined style={{ color: 'var(--primary)' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>类别数</div>
            <div className={styles.statValue}>{Object.keys(stats?.categories || {}).length}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><ThunderboltOutlined style={{ color: 'var(--primary)' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>标签数</div>
            <div className={styles.statValue}>{Object.keys(stats?.tags || {}).length}</div>
          </div>
        </div>
      </div>

      {/* Table card */}
      <div className={styles.glassCard}>
        <div className={styles.filterBar}>
          <div className={styles.searchInput}>
            <SearchOutlined />
            <input placeholder="搜索技能..." value={searchText} onChange={(e) => setSearchText(e.target.value)} />
          </div>
          <select className={styles.filterSelect} value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="">全部类别</option>
            <option value="file">文件</option>
            <option value="network">网络</option>
            <option value="data">数据</option>
            <option value="code">代码</option>
            <option value="system">系统</option>
            <option value="utility">工具</option>
            <option value="ai">AI</option>
            <option value="custom">自定义</option>
          </select>
          <div className={styles.filterActions}>
            <button className={`${styles.btn} ${styles.btnDefault}`} onClick={loadSkills}>
              <ReloadOutlined /> 刷新
            </button>
            <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleScan}>
              <SearchOutlined /> 扫描新技能
            </button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>技能名称</th>
                <th>描述</th>
                <th>类别</th>
                <th>版本</th>
                <th>标签</th>
                <th>参数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className={styles.emptyCell}>加载中...</td></tr>
              ) : filteredSkills.length === 0 ? (
                <tr><td colSpan={7} className={styles.emptyCell}>暂无技能</td></tr>
              ) : filteredSkills.map((skill) => (
                <tr key={skill.name}>
                  <td>
                    <div className={styles.skillName}>
                      <span className={styles.skillCategoryIcon}
                        style={{ background: 'rgba(99,102,241,0.12)', color: 'var(--primary)' }}>
                        {categoryIcons[skill.category] || <ToolOutlined />}
                      </span>
                      {skill.name}
                    </div>
                  </td>
                  <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {skill.description}
                  </td>
                  <td>
                    <span className={`${styles.tag} ${getTagCls(categoryTagCls, skill.category)}`}>
                      {skill.category}
                    </span>
                  </td>
                  <td>{skill.version}</td>
                  <td>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                      {skill.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className={`${styles.tag} ${styles.tagGray}`}>{tag}</span>
                      ))}
                      {skill.tags.length > 3 && (
                        <span className={`${styles.tag} ${styles.tagGray}`}>+{skill.tags.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={styles.paramBadge}>{skill.parameters.length}</span>
                  </td>
                  <td>
                    <div className={styles.rowActions}>
                      <button className={`${styles.iconBtn} ${styles.iconBtnPrimary}`} title="执行" onClick={() => showExecute(skill)}>
                        <PlayCircleOutlined />
                      </button>
                      <button className={styles.iconBtn} title="详情" onClick={() => showDetail(skill)}>
                        <InfoCircleOutlined />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail modal */}
      {detailModalOpen && selectedSkill && (
        <div className={styles.modalOverlay} onClick={() => setDetailModalOpen(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>技能详情 - {selectedSkill.name}</span>
              <button className={styles.closeBtn} onClick={() => setDetailModalOpen(false)}><CloseOutlined /></button>
            </div>
            <div className={styles.modalBody}>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>名称</span>
                  <span className={styles.detailValue}>{selectedSkill.name}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>版本</span>
                  <span className={styles.detailValue}>{selectedSkill.version}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>类别</span>
                  <span className={`${styles.tag} ${getTagCls(categoryTagCls, selectedSkill.category)}`}>
                    {selectedSkill.category}
                  </span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>优先级</span>
                  <span className={`${styles.tag} ${getTagCls(priorityTagCls, selectedSkill.priority)}`}>
                    {selectedSkill.priority}
                  </span>
                </div>
                <div className={`${styles.detailItem} ${styles.detailItemFull}`}>
                  <span className={styles.detailLabel}>描述</span>
                  <span className={styles.detailValue}>{selectedSkill.description}</span>
                </div>
                <div className={`${styles.detailItem} ${styles.detailItemFull}`}>
                  <span className={styles.detailLabel}>标签</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                    {selectedSkill.tags.map((tag) => (
                      <span key={tag} className={`${styles.tag} ${styles.tagGray}`}>{tag}</span>
                    ))}
                  </div>
                </div>
              </div>

              {selectedSkill.parameters.length > 0 && (
                <>
                  <hr className={styles.sectionDivider} />
                  <p className={styles.sectionTitle}>参数</p>
                  <div className={styles.tableWrap}>
                    <table className={styles.dataTable}>
                      <thead>
                        <tr><th>参数名</th><th>类型</th><th>必填</th><th>默认值</th><th>描述</th></tr>
                      </thead>
                      <tbody>
                        {selectedSkill.parameters.map((param) => (
                          <tr key={param.name}>
                            <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{param.name}</td>
                            <td><span className={`${styles.tag} ${styles.tagPurple}`}>{param.type}</span></td>
                            <td>
                              <span className={`${styles.tag} ${param.required ? styles.tagRed : styles.tagGray}`}>
                                {param.required ? '是' : '否'}
                              </span>
                            </td>
                            <td>{param.default !== undefined ? JSON.stringify(param.default) : '-'}</td>
                            <td>{param.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
            <div className={styles.modalFooter}>
              <button className={`${styles.btn} ${styles.btnDefault}`} onClick={() => setDetailModalOpen(false)}>关闭</button>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => {
                setDetailModalOpen(false)
                showExecute(selectedSkill)
              }}>
                <PlayCircleOutlined /> 执行
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execute modal */}
      {executeModalOpen && selectedSkill && (
        <div className={styles.modalOverlay} onClick={() => setExecuteModalOpen(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>执行技能 - {selectedSkill.name}</span>
              <button className={styles.closeBtn} onClick={() => setExecuteModalOpen(false)}><CloseOutlined /></button>
            </div>
            <div className={styles.modalBody}>
              <div className={styles.formField}>
                <label className={styles.formLabel}>参数 (JSON 格式)</label>
                <textarea className={styles.codeTextarea} rows={8} value={executeParams}
                  onChange={(e) => setExecuteParams(e.target.value)} placeholder='{"key": "value"}' />
              </div>
              <div className={styles.formField}>
                <label className={styles.formLabel}>优先级</label>
                <select className={styles.formSelect} value={executePriority}
                  onChange={(e) => setExecutePriority(e.target.value)}>
                  <option value="low">低</option>
                  <option value="normal">普通</option>
                  <option value="high">高</option>
                  <option value="critical">紧急</option>
                </select>
              </div>
            </div>
            <div className={styles.modalFooter}>
              <button className={`${styles.btn} ${styles.btnDefault}`} onClick={() => setExecuteModalOpen(false)}>取消</button>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleExecute} disabled={executing}>
                {executing ? '执行中...' : '执行'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Result modal */}
      {resultModalOpen && executionResult && (
        <div className={styles.modalOverlay} onClick={() => setResultModalOpen(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>执行结果</span>
              <button className={styles.closeBtn} onClick={() => setResultModalOpen(false)}><CloseOutlined /></button>
            </div>
            <div className={styles.modalBody}>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>执行 ID</span>
                  <span className={styles.detailValue} style={{ fontSize: 12, fontFamily: 'monospace' }}>
                    {executionResult.execution_id}
                  </span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>技能名称</span>
                  <span className={styles.detailValue}>{executionResult.skill_name}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>状态</span>
                  <span className={`${styles.tag} ${executionResult.status === 'completed' ? styles.tagGreen : executionResult.status === 'failed' ? styles.tagRed : styles.tagBlue}`}>
                    {executionResult.status}
                  </span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>耗时</span>
                  <span className={styles.detailValue}>
                    {executionResult.duration_ms ? `${executionResult.duration_ms.toFixed(2)} ms` : '-'}
                  </span>
                </div>
                {executionResult.started_at && (
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>开始时间</span>
                    <span className={styles.detailValue}>{new Date(executionResult.started_at).toLocaleString()}</span>
                  </div>
                )}
                {executionResult.completed_at && (
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>完成时间</span>
                    <span className={styles.detailValue}>{new Date(executionResult.completed_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
              {executionResult.error && (
                <>
                  <hr className={styles.sectionDivider} />
                  <p style={{ color: '#f87171', fontSize: 13 }}>{executionResult.error}</p>
                </>
              )}
              {executionResult.result && (
                <>
                  <hr className={styles.sectionDivider} />
                  <p className={styles.sectionTitle}>返回结果</p>
                  <pre className={styles.resultPre}>{JSON.stringify(executionResult.result, null, 2)}</pre>
                </>
              )}
            </div>
            <div className={styles.modalFooter}>
              <button className={`${styles.btn} ${styles.btnDefault}`} onClick={() => setResultModalOpen(false)}>关闭</button>
            </div>
          </div>
        </div>
      )}
      </MotionItem>
    </MotionList>
  )
}
