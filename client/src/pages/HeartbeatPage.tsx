import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  DashboardOutlined,
  DeleteOutlined,
  DesktopOutlined,
  HddOutlined,
  HeartOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  ScheduleOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Form, Switch, message } from 'antd';
import { useEffect, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { apiClient } from '../services/api';
import styles from './HeartbeatPage.module.css';

interface Task {
  id: string;
  name: string;
  description: string;
  schedule: string;
  task_type: string;
  enabled: boolean;
  status?: string;
  last_run?: string;
  next_run?: string;
}

interface TaskResult {
  task_id: string;
  status: string;
  result?: any;
  error?: string;
  duration_ms?: number;
  executed_at: string;
}

interface HeartbeatStatus {
  tier?: string;
  available?: boolean;
  runtime_status?: string;
  dependency_status?: string;
  failure_mode?: string;
  message?: string;
  scheduler: {
    running: boolean;
    total_tasks: number;
    enabled_tasks: number;
  };
  executor: {
    total_executed: number;
    success_count: number;
    failure_count: number;
  };
}

export default function HeartbeatPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [results, setResults] = useState<TaskResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<HeartbeatStatus | null>(null);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [statusNotice, setStatusNotice] = useState('');

  useEffect(() => {
    fetchHeartbeatData();
    const interval = setInterval(fetchHeartbeatData, 5000);
    return () => clearInterval(interval);
  }, []);

  const getApiErrorMessage = (error: any, fallback: string) =>
    error?.response?.data?.detail || error?.response?.data?.message || fallback;

  const fetchHeartbeatData = async () => {
    setLoading(true);
    try {
      const [statusRes, tasksRes, resultsRes] = await Promise.all([
        apiClient.get('/heartbeat/status').catch(() => ({ data: null })),
        apiClient.get('/heartbeat/tasks').catch(() => ({ data: { tasks: [] } })),
        apiClient.get('/heartbeat/results?limit=20').catch(() => ({ data: { results: [] } })),
      ]);
      setStatus(statusRes.data);
      setStatusNotice(
        statusRes.data
          ? ''
          : 'Heartbeat 状态接口当前不可用，任务列表仍可显示，但不代表调度器和执行器已经稳定运行。',
      );
      setTasks(tasksRes.data?.tasks || []);
      setResults(resultsRes.data?.results || []);
    } catch (error) {
      console.error('Failed to fetch heartbeat data:', error);
      setStatusNotice('Heartbeat 数据获取失败，当前页面无法确认实验调度能力是否可用。');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTask = async (values: any) => {
    try {
      const response = await apiClient.post('/heartbeat/tasks', {
        name: values.name,
        description: values.description || '',
        schedule: values.schedule,
        task_type: values.task_type || 'check',
        enabled: true,
        config: {},
      });
      if (response.data?.success) {
        message.success('任务创建成功');
        setCreateModalVisible(false);
        createForm.resetFields();
        fetchHeartbeatData();
      } else {
        message.error(response.data?.message || '创建失败');
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '创建失败'));
    }
  };

  const handleToggleTask = async (taskId: string, enabled: boolean) => {
    try {
      const endpoint = enabled ? '/heartbeat/tasks/{id}/enable' : '/heartbeat/tasks/{id}/disable';
      const response = await apiClient.post(endpoint.replace('{id}', taskId));
      if (!response.data?.success) {
        message.error(response.data?.message || '操作失败');
        return;
      }
      message.success(enabled ? '任务已启用' : '任务已禁用');
      fetchHeartbeatData();
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '操作失败'));
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      const response = await apiClient.delete(`/heartbeat/tasks/${taskId}`);
      if (!response.data?.success) {
        message.error(response.data?.message || '删除失败');
        return;
      }
      message.success('任务已删除');
      fetchHeartbeatData();
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '删除失败'));
    }
  };

  const handleStartScheduler = async () => {
    try {
      const response = await apiClient.post('/heartbeat/start');
      if (response.data?.success) {
        message.success('调度器已启动');
        fetchHeartbeatData();
      } else {
        message.warning(response.data?.message || '启动失败');
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '启动失败'));
    }
  };

  const handleStopScheduler = async () => {
    try {
      const response = await apiClient.post('/heartbeat/stop');
      if (response.data?.success) {
        message.success('调度器已停止');
        fetchHeartbeatData();
      } else {
        message.warning(response.data?.message || '停止失败');
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, '停止失败'));
    }
  };

  const getTaskTypeInfo = (type: string) => {
    const map: Record<string, { cls: string | undefined; text: string }> = {
      check: { cls: styles.tagBlue, text: '检查' },
      report: { cls: styles.tagGreen, text: '汇报' },
      reminder: { cls: styles.tagOrange, text: '提醒' },
      custom: { cls: styles.tagPurple, text: '自定义' },
    };
    return map[type] || { cls: styles.tagGray, text: type };
  };

  const getStatusInfo = (s: string) => {
    const map: Record<string, { dotCls: string | undefined; text: string }> = {
      completed: { dotCls: styles.dotGreen, text: '已完成' },
      running: { dotCls: styles.dotBlue, text: '运行中' },
      failed: { dotCls: styles.dotRed, text: '失败' },
      pending: { dotCls: styles.dotGray, text: '待执行' },
    };
    return map[s] || { dotCls: styles.dotGray, text: s };
  };

  const successRate = status?.executor
    ? Math.round(
        (status.executor.success_count / Math.max(status.executor.total_executed, 1)) * 100,
      )
    : 0;

  return (
    <MotionList className={styles.page} stagger={0.08}>
      <MotionItem>
        {/* Experiment banner */}
        <div className={styles.experimentBanner}>
          <WarningOutlined />
          <p>
            <strong>实验功能</strong> — Heartbeat
            当前仍处于实验阶段，任务执行成功与否应以实际调度结果和任务记录为准。
          </p>
        </div>
        <div
          data-testid="heartbeat-runtime-status"
          className={styles.experimentBanner}
          style={{
            marginTop: 12,
            background:
              status?.runtime_status === 'ready'
                ? 'rgba(74,222,128,0.12)'
                : 'rgba(250,173,20,0.14)',
            borderColor:
              status?.runtime_status === 'ready'
                ? 'rgba(74,222,128,0.28)'
                : 'rgba(250,173,20,0.28)',
          }}
        >
          <WarningOutlined />
          <p>
            <strong>
              {status?.runtime_status === 'ready' ? '调度能力已启动' : '调度能力受限'}
            </strong>
            {' — '}
            {statusNotice || status?.message || '尚未拿到 Heartbeat 运行状态。'}
            {status?.dependency_status ? ` 依赖状态：${status.dependency_status}。` : ''}
          </p>
        </div>

        <h2 className={styles.pageTitle}>
          <HeartOutlined /> Heartbeat 任务调度（实验）
        </h2>

        {/* Stats */}
        <div className={styles.statsRow}>
          <div className={styles.statCard}>
            <div
              className={styles.statIcon}
              style={{
                background: status?.scheduler?.running
                  ? 'rgba(74,222,128,0.12)'
                  : 'rgba(248,113,113,0.12)',
              }}
            >
              {status?.scheduler?.running ? (
                <PlayCircleOutlined style={{ color: '#4ade80' }} />
              ) : (
                <PauseCircleOutlined style={{ color: '#f87171' }} />
              )}
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>调度器状态</div>
              <div
                className={styles.statValue}
                style={{ color: status?.scheduler?.running ? '#4ade80' : '#f87171', fontSize: 16 }}
              >
                {status?.scheduler?.running ? '运行中' : '已停止'}
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <ScheduleOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>任务总数</div>
              <div className={styles.statValue}>
                {status?.scheduler?.total_tasks || 0}
                <span className={styles.statSuffix}>
                  / {status?.scheduler?.enabled_tasks || 0} 启用
                </span>
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <SyncOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>执行次数</div>
              <div className={styles.statValue}>{status?.executor?.total_executed || 0}</div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div
              className={styles.statIcon}
              style={{
                background:
                  successRate >= 90
                    ? 'rgba(74,222,128,0.12)'
                    : successRate >= 70
                      ? 'rgba(250,173,20,0.12)'
                      : 'rgba(248,113,113,0.12)',
              }}
            >
              <CheckCircleOutlined
                style={{
                  color: successRate >= 90 ? '#4ade80' : successRate >= 70 ? '#faad14' : '#f87171',
                }}
              />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>成功率</div>
              <div
                className={styles.statValue}
                style={{
                  color: successRate >= 90 ? '#4ade80' : successRate >= 70 ? '#faad14' : '#f87171',
                }}
              >
                {successRate}
                <span className={styles.statSuffix}>%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Main layout */}
        <div className={styles.mainLayout}>
          {/* Task list */}
          <div className={styles.glassCard}>
            <div className={styles.cardHeader}>
              <span className={styles.cardTitle}>
                <ScheduleOutlined /> 任务列表
              </span>
              <div className={styles.cardActions}>
                {status?.scheduler?.running ? (
                  <button
                    className={`${styles.btn} ${styles.btnDanger}`}
                    onClick={handleStopScheduler}
                  >
                    <PauseCircleOutlined /> 停止调度
                  </button>
                ) : (
                  <button
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    onClick={handleStartScheduler}
                  >
                    <PlayCircleOutlined /> 启动调度
                  </button>
                )}
                <button
                  className={`${styles.btn} ${styles.btnDefault}`}
                  onClick={() => setCreateModalVisible(true)}
                >
                  <PlusOutlined /> 创建任务
                </button>
                <button
                  className={`${styles.btn} ${styles.btnDefault}`}
                  onClick={fetchHeartbeatData}
                  disabled={loading}
                >
                  <ReloadOutlined /> 刷新
                </button>
              </div>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>任务名称</th>
                    <th>类型</th>
                    <th>调度周期</th>
                    <th>状态</th>
                    <th>上次执行</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.length === 0 ? (
                    <tr>
                      <td colSpan={6} className={styles.emptyCell}>
                        暂无任务
                      </td>
                    </tr>
                  ) : (
                    tasks.map((task) => {
                      const typeInfo = getTaskTypeInfo(task.task_type);
                      const statusInfo = task.status ? getStatusInfo(task.status) : null;
                      return (
                        <tr key={task.id}>
                          <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                            {task.name}
                            {!task.enabled && (
                              <span
                                className={`${styles.tag} ${styles.tagGray}`}
                                style={{ marginLeft: 6 }}
                              >
                                已禁用
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`${styles.tag} ${typeInfo.cls}`}>{typeInfo.text}</span>
                          </td>
                          <td>
                            <span className={`${styles.tag} ${styles.tagGray}`}>
                              <ClockCircleOutlined /> {task.schedule}
                            </span>
                          </td>
                          <td>
                            {statusInfo ? (
                              <span className={styles.statusDot}>
                                <span className={`${styles.dot} ${statusInfo.dotCls}`} />
                                {statusInfo.text}
                              </span>
                            ) : (
                              '-'
                            )}
                          </td>
                          <td>{task.last_run ? new Date(task.last_run).toLocaleString() : '-'}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Switch
                                size="small"
                                checked={task.enabled}
                                onChange={(checked) => handleToggleTask(task.id, checked)}
                              />
                              <button
                                className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                                onClick={() => handleDeleteTask(task.id)}
                              >
                                <DeleteOutlined />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Timeline */}
          <div className={styles.timelineCard}>
            <div className={styles.cardHeader}>
              <span className={styles.cardTitle}>执行历史</span>
            </div>
            <div className={styles.timeline}>
              {results.length === 0 ? (
                <div className={styles.timelineEmpty}>暂无执行记录</div>
              ) : (
                results.slice(0, 10).map((result, idx) => {
                  const dotCls =
                    result.status === 'completed'
                      ? styles.timelineDotGreen
                      : result.status === 'failed'
                        ? styles.timelineDotRed
                        : styles.timelineDotBlue;
                  return (
                    <div key={idx} className={styles.timelineItem}>
                      <span className={`${styles.timelineDot} ${dotCls}`} />
                      <div className={styles.timelineContent}>
                        <div className={styles.timelineTitle}>{result.task_id}</div>
                        <div className={styles.timelineMeta}>
                          {new Date(result.executed_at).toLocaleString()}
                          {result.duration_ms && ` · ${result.duration_ms}ms`}
                        </div>
                        {result.error && <div className={styles.timelineError}>{result.error}</div>}
                        {result.result?.metrics && (
                          <div className={styles.resultMetricsRow}>
                            <div className={styles.resultMetricTag}>
                              <DashboardOutlined /> CPU
                              <span className={styles.resultMetricValue}>
                                {result.result.metrics.cpu_percent?.toFixed(1)}%
                              </span>
                            </div>
                            <div className={styles.resultMetricTag}>
                              <DesktopOutlined /> 内存
                              <span className={styles.resultMetricValue}>
                                {result.result.metrics.memory_percent?.toFixed(1)}%
                              </span>
                            </div>
                            <div className={styles.resultMetricTag}>
                              <HddOutlined /> 磁盘
                              <span className={styles.resultMetricValue}>
                                {result.result.metrics.disk_percent?.toFixed(1)}%
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Create task modal */}
        {createModalVisible && (
          <div className={styles.modalOverlay} onClick={() => setCreateModalVisible(false)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              <div className={styles.modalHeader}>
                <span className={styles.modalTitle}>创建任务</span>
                <button className={styles.closeBtn} onClick={() => setCreateModalVisible(false)}>
                  <CloseOutlined />
                </button>
              </div>
              <Form form={createForm} layout="vertical" onFinish={handleCreateTask}>
                <div className={styles.modalBody}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>任务名称 *</label>
                    <Form.Item
                      name="name"
                      noStyle
                      rules={[{ required: true, message: '请输入任务名称' }]}
                    >
                      <input className={styles.formInput} placeholder="例如: 定期检查 GPU 状态" />
                    </Form.Item>
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>描述</label>
                    <Form.Item name="description" noStyle>
                      <input className={styles.formInput} placeholder="任务描述（可选）" />
                    </Form.Item>
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>任务类型 *</label>
                    <Form.Item
                      name="task_type"
                      noStyle
                      rules={[{ required: true, message: '请选择任务类型' }]}
                    >
                      <select className={styles.formSelect}>
                        <option value="">请选择</option>
                        <option value="check">检查任务</option>
                        <option value="report">汇报任务</option>
                        <option value="reminder">提醒任务</option>
                        <option value="custom">自定义任务</option>
                      </select>
                    </Form.Item>
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>调度周期 *</label>
                    <Form.Item
                      name="schedule"
                      noStyle
                      rules={[{ required: true, message: '请输入调度周期' }]}
                    >
                      <input className={styles.formInput} placeholder="例如: 60 或 '0 * * * *'" />
                    </Form.Item>
                    <span className={styles.formHint}>
                      支持秒数（如 60）或 Cron 表达式（如 '0 * * * *'）
                    </span>
                  </div>
                </div>
                <div className={styles.modalFooter}>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnDefault}`}
                    onClick={() => setCreateModalVisible(false)}
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    onClick={() => createForm.submit()}
                  >
                    创建
                  </button>
                </div>
              </Form>
            </div>
          </div>
        )}
      </MotionItem>
    </MotionList>
  );
}
