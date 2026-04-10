import { useEffect, useState } from 'react'
import { App, Modal } from 'antd'
import {
  BankOutlined,
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  SettingOutlined,
  SyncOutlined,
  TrophyOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { API_BASE_URL } from '../services/api'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './SkillMemory.module.css'

interface SkillMemoryConfig {
  skill_name: string
  memory_enabled: boolean
  context_injection: boolean
  result_storage: boolean
  preference_learning: boolean
  max_memories: number
  relevance_threshold: number
}

interface UserPreference {
  key: string
  value: string
  learned_at: string
  confidence: number
}

interface OperationHistory {
  skill_name: string
  timestamp: string
  success: boolean
  duration: number
  params: Record<string, unknown>
}

const TABS = [
  { key: 'configs', label: '技能配置', icon: <SettingOutlined /> },
  { key: 'preferences', label: '用户偏好', icon: <TrophyOutlined /> },
  { key: 'history', label: '操作历史', icon: <HistoryOutlined /> },
]

export default function SkillMemory() {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState('configs')
  const [configs, setConfigs] = useState<SkillMemoryConfig[]>([])
  const [preferences, setPreferences] = useState<UserPreference[]>([])
  const [history, setHistory] = useState<OperationHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingConfig, setEditingConfig] = useState<SkillMemoryConfig | null>(null)
  const [editForm, setEditForm] = useState<Partial<SkillMemoryConfig>>({})

  useEffect(() => {
    void fetchConfigs()
    void fetchPreferences()
    void fetchHistory()
  }, [])

  const fetchConfigs = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/configs`)
      if (!response.ok) { message.error('加载技能配置失败'); return }
      const data = await response.json()
      setConfigs(data.configs || [])
    } catch (error) {
      console.error('Failed to fetch configs:', error)
      message.error('加载技能配置失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchPreferences = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/preferences`)
      if (!response.ok) { message.error('加载用户偏好失败'); return }
      const data = await response.json()
      setPreferences(data.preferences || [])
    } catch (error) {
      console.error('Failed to fetch preferences:', error)
      message.error('加载用户偏好失败')
    }
  }

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/history`)
      if (!response.ok) { message.error('加载操作历史失败'); return }
      const data = await response.json()
      setHistory(data.history || [])
    } catch (error) {
      console.error('Failed to fetch history:', error)
      message.error('加载操作历史失败')
    }
  }

  const handleUpdateConfig = async () => {
    if (!editingConfig) return
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/configs/${editingConfig.skill_name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      })
      if (!response.ok) { message.error('更新配置失败'); return }
      await fetchConfigs()
      setEditModalVisible(false)
      message.success('配置已更新')
    } catch (error) {
      console.error('Failed to update config:', error)
      message.error('更新配置失败')
    }
  }

  const handleDeletePreference = async (key: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/skills/memory/preferences/${key}`, { method: 'DELETE' })
      if (!response.ok) { message.error('删除偏好失败'); return }
      await fetchPreferences()
      message.success('偏好已删除')
    } catch (error) {
      console.error('Failed to delete preference:', error)
      message.error('删除偏好失败')
    }
  }

  const handleClearHistory = () => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空全部操作历史吗？',
      onOk: async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/skills/memory/history`, { method: 'DELETE' })
          if (!response.ok) { message.error('清空历史失败'); return }
          setHistory([])
          message.success('历史已清空')
        } catch (error) {
          console.error('Failed to clear history:', error)
          message.error('清空历史失败')
        }
      },
    })
  }

  const openEditModal = (config: SkillMemoryConfig) => {
    setEditingConfig(config)
    setEditForm({ ...config })
    setEditModalVisible(true)
  }

  const successRate = history.length > 0
    ? (history.filter((item) => item.success).length / history.length) * 100
    : 0

  // Switch view helper
  const SwitchView = ({ checked }: { checked: boolean }) => (
    <div className={styles.switchView}>
      <div className={`${styles.switchPill} ${checked ? styles.switchPillOn : styles.switchPillOff}`} />
      <span style={{ color: checked ? '#4ade80' : 'var(--text-muted)' }}>{checked ? '开' : '关'}</span>
    </div>
  )

  return (
    <MotionList className={styles.page} stagger={0.08}>
      <MotionItem>
      <h2 className={styles.pageTitle}><BankOutlined /> 记忆-技能配置</h2>

      {/* Stats */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><SettingOutlined style={{ color: 'var(--primary)' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>已配置技能</div>
            <div className={styles.statValue}>{configs.length}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><TrophyOutlined style={{ color: '#faad14' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>用户偏好</div>
            <div className={styles.statValue}>{preferences.length}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}><HistoryOutlined style={{ color: '#818cf8' }} /></div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>操作历史</div>
            <div className={styles.statValue}>{history.length}</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}
            style={{ background: successRate > 80 ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)' }}>
            <span style={{ color: successRate > 80 ? '#4ade80' : '#f87171', fontSize: 18, fontWeight: 700 }}>%</span>
          </div>
          <div className={styles.statInfo}>
            <div className={styles.statLabel}>成功率</div>
            <div className={styles.statValue} style={{ color: successRate > 80 ? '#4ade80' : '#f87171' }}>
              {successRate.toFixed(1)}<span className={styles.statSuffix}>%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabsWrapper}>
        <div className={styles.tabList}>
          {TABS.map((tab) => (
            <div
              key={tab.key}
              className={`${styles.tabItem} ${activeTab === tab.key ? styles.tabItemActive : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.icon} {tab.label}
            </div>
          ))}
        </div>

        <div className={styles.tabContent}>
          {/* Configs tab */}
          {activeTab === 'configs' && (
            <>
              <div className={styles.toolbar}>
                <button className={`${styles.btn} ${styles.btnDefault}`} onClick={() => void fetchConfigs()}>
                  <SyncOutlined /> 刷新
                </button>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>技能名称</th>
                      <th>记忆启用</th>
                      <th>上下文注入</th>
                      <th>结果存储</th>
                      <th>偏好学习</th>
                      <th>最大记忆数</th>
                      <th>相关性阈值</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan={8} className={styles.emptyCell}>加载中...</td></tr>
                    ) : configs.length === 0 ? (
                      <tr><td colSpan={8} className={styles.emptyCell}>暂无配置</td></tr>
                    ) : configs.map((config) => (
                      <tr key={config.skill_name}>
                        <td><span className={`${styles.tag} ${styles.tagBlue}`}>{config.skill_name}</span></td>
                        <td>
                          <span className={styles.statusDot}>
                            <span className={`${styles.dot} ${config.memory_enabled ? styles.dotGreen : styles.dotGray}`} />
                            {config.memory_enabled ? '启用' : '禁用'}
                          </span>
                        </td>
                        <td><SwitchView checked={config.context_injection} /></td>
                        <td><SwitchView checked={config.result_storage} /></td>
                        <td><SwitchView checked={config.preference_learning} /></td>
                        <td>{config.max_memories}</td>
                        <td>{(config.relevance_threshold * 100).toFixed(0)}%</td>
                        <td>
                          <button className={styles.iconBtn}
                            data-testid={`skill-config-edit-${config.skill_name}`}
                            onClick={() => openEditModal(config)}>
                            <EditOutlined />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Preferences tab */}
          {activeTab === 'preferences' && (
            <>
              <div className={styles.toolbar}>
                <button className={`${styles.btn} ${styles.btnDefault}`}
                  data-testid="skill-tab-preferences"
                  onClick={() => void fetchPreferences()}>
                  <SyncOutlined /> 刷新
                </button>
              </div>
              {preferences.length === 0 ? (
                <div className={styles.emptyCell}>暂无用户偏好</div>
              ) : (
                <div className={styles.tableWrap}>
                  <table className={styles.dataTable}>
                    <thead>
                      <tr><th>偏好键</th><th>偏好值</th><th>学习时间</th><th>置信度</th><th>操作</th></tr>
                    </thead>
                    <tbody>
                      {preferences.map((pref) => (
                        <tr key={pref.key}>
                          <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{pref.key}</td>
                          <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {pref.value}
                          </td>
                          <td>{new Date(pref.learned_at).toLocaleString()}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <div className={styles.progressBar}>
                                <div
                                  className={`${styles.progressFill} ${pref.confidence > 0.8 ? styles.progressFillGood : ''}`}
                                  style={{ width: `${pref.confidence * 100}%` }}
                                />
                              </div>
                              <span className={styles.progressLabel}>{(pref.confidence * 100).toFixed(0)}%</span>
                            </div>
                          </td>
                          <td>
                            <button className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                              onClick={() => handleDeletePreference(pref.key)}>
                              <DeleteOutlined />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {/* History tab */}
          {activeTab === 'history' && (
            <>
              <div className={styles.toolbar}>
                <button className={`${styles.btn} ${styles.btnDefault}`}
                  data-testid="skill-tab-history"
                  onClick={() => void fetchHistory()}>
                  <SyncOutlined /> 刷新
                </button>
                <button className={`${styles.btn} ${styles.btnDanger}`} onClick={() => void handleClearHistory()}>
                  <DeleteOutlined /> 清除历史
                </button>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr><th>技能</th><th>时间</th><th>状态</th><th>耗时</th></tr>
                  </thead>
                  <tbody>
                    {history.length === 0 ? (
                      <tr><td colSpan={4} className={styles.emptyCell}>暂无历史记录</td></tr>
                    ) : history.map((record) => (
                      <tr key={`${record.skill_name}-${record.timestamp}-${record.duration}`}>
                        <td><span className={`${styles.tag} ${styles.tagGray}`}>{record.skill_name}</span></td>
                        <td>{new Date(record.timestamp).toLocaleString()}</td>
                        <td>
                          <span className={styles.statusDot}>
                            <span className={`${styles.dot} ${record.success ? styles.dotGreen : styles.dotRed}`} />
                            {record.success ? '成功' : '失败'}
                          </span>
                        </td>
                        <td>{record.duration.toFixed(2)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Edit modal */}
      {editModalVisible && editingConfig && (
        <div className={styles.modalOverlay} onClick={() => setEditModalVisible(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>编辑技能配置</span>
              <button className={styles.closeBtn} onClick={() => setEditModalVisible(false)}><CloseOutlined /></button>
            </div>
            <div className={styles.modalBody}>
              {(['memory_enabled', 'context_injection', 'result_storage', 'preference_learning'] as const).map((field) => {
                const labels: Record<string, string> = {
                  memory_enabled: '启用记忆',
                  context_injection: '上下文注入',
                  result_storage: '结果存储',
                  preference_learning: '偏好学习',
                }
                return (
                  <div key={field} className={styles.formRow}>
                    <span className={styles.formLabel}>{labels[field]}</span>
                    <label className={styles.toggle}>
                      <input type="checkbox" checked={!!editForm[field]}
                        onChange={(e) => setEditForm({ ...editForm, [field]: e.target.checked })} />
                      <span className={styles.toggleSlider} />
                    </label>
                  </div>
                )
              })}
              <div className={styles.formRow}>
                <span className={styles.formLabel}>最大记忆数</span>
                <input type="number" className={styles.formInputNum}
                  min={1} max={100} value={editForm.max_memories ?? 50}
                  onChange={(e) => setEditForm({ ...editForm, max_memories: Number(e.target.value) })} />
              </div>
              <div className={styles.formRow}>
                <span className={styles.formLabel}>相关性阈值</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="range" min={0} max={1} step={0.1}
                    value={editForm.relevance_threshold ?? 0.7}
                    onChange={(e) => setEditForm({ ...editForm, relevance_threshold: Number(e.target.value) })}
                    style={{ width: 100, accentColor: 'var(--primary)' }} />
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 32 }}>
                    {((editForm.relevance_threshold ?? 0.7) * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
            <div className={styles.modalFooter}>
              <button className={`${styles.btn} ${styles.btnDefault}`} onClick={() => setEditModalVisible(false)}>取消</button>
              <button className={`${styles.btnPrimary}`} onClick={handleUpdateConfig}>保存</button>
            </div>
          </div>
        </div>
      )}
      </MotionItem>
    </MotionList>
  )
}
