import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Area, AreaChart,
  Tooltip as RechartsTooltip, ResponsiveContainer,
} from 'recharts';
import {
  CodeOutlined, SaveOutlined,
  RocketOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ThunderboltOutlined, PauseCircleOutlined, PlayCircleOutlined,
  CopyOutlined, FilterOutlined,
} from '@ant-design/icons';
import { AnimatePresence, motion } from 'framer-motion';
import { Tag, Tooltip, message } from 'antd';
import styles from './TrainingDashboard.module.css';
import type { TrainingProgress as TrainingProgressType } from '../../../types';
import { getTrainingCheckpoints, subscribeTrainingLogs } from '../../../services/trainingApi';

interface CheckpointInfo {
  name: string;
  path: string;
  step: number;
  created: string;
  metadata: Record<string, unknown>;
  valid: boolean;
}

interface TrainingDashboardProps {
  progress: TrainingProgressType | null;
  chartData: { step: number; loss: number; lr: number; vram?: number }[];
  status: 'idle' | 'queued' | 'loading' | 'training' | 'saving' | 'stopping' | 'completed' | 'failed';
  selectedModel?: string;
  selectedDataset?: string;
  selectedMethod?: string;
  onReset?: () => void;
  phaseDurations?: Record<string, number>;
  currentPhase?: string;
  retryCount?: number;
  currentTaskId?: string | null;
  onResume?: (taskId: string, checkpointName: string) => void;
}

const formatCheckpointTime = (value: unknown) => {
  if (typeof value === 'string' || typeof value === 'number' || value instanceof Date) {
    return new Date(value).toLocaleString();
  }
  return '';
};

/* ── Animated Metric Value ── */
const AnimatedValue = ({ value, className }: { value: string; className?: string }) => (
  <AnimatePresence mode="wait">
    <motion.div
      key={value}
      className={className}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      {value}
    </motion.div>
  </AnimatePresence>
);

/* ── Terminal with Syntax Highlighting ── */
const highlightLog = (log: string) =>
  log
    .replace(/\[METRIC\]/g, `<span class="${styles.tokenMetric}">[METRIC]</span>`)
    .replace(/\[ERROR\]/g, `<span class="${styles.tokenError}">[ERROR]</span>`)
    .replace(/\[WARN\]/g, `<span class="${styles.tokenWarn}">[WARN]</span>`)
    .replace(/\[STATE\]/g, `<span class="${styles.tokenState}">[STATE]</span>`)
    .replace(/\[VRAM\]/g, `<span class="${styles.tokenMetric}">[VRAM]</span>`)
    .replace(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/g, `<span class="${styles.tokenTime}">$1</span>`)
    .replace(/(\|\s*(?:INFO|WARNING|ERROR|DEBUG)\s*\|)/g, (match) => {
      if (match.includes('ERROR')) return `<span class="${styles.tokenError}">${match}</span>`;
      if (match.includes('WARN')) return `<span class="${styles.tokenWarn}">${match}</span>`;
      return `<span class="${styles.tokenState}">${match}</span>`;
    })
    .replace(/(\[\d{2}:\d{2}:\d{2}\])/g, `<span class="${styles.tokenTime}">$1</span>`);

const TerminalStream = React.memo(({ logs = [] }: { logs: string[] }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const htmlCache = useRef<Map<string, string>>(new Map());
  const counterRef = useRef(0);
  const keysRef = useRef<number[]>([]);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<'ALL' | 'ERROR' | 'WARN' | 'INFO'>('ALL');

  // Build stable keys: reuse existing keys for unchanged lines, assign new ones for appended lines
  const prevLen = keysRef.current.length;
  if (logs.length > prevLen) {
    for (let i = prevLen; i < logs.length; i++) {
      keysRef.current[i] = ++counterRef.current;
    }
  } else if (logs.length < prevLen) {
    keysRef.current.length = logs.length;
  }

  // Pre-compute highlighted HTML for all lines (cached for unchanged lines)
  const htmls: string[] = new Array(logs.length);
  for (let i = 0; i < logs.length; i++) {
    const log = logs[i]!;
    let cached = htmlCache.current.get(log);
    if (cached === undefined) {
      cached = highlightLog(log);
      if (htmlCache.current.size > 300) {
        const first = htmlCache.current.keys().next().value;
        if (first !== undefined) htmlCache.current.delete(first);
      }
      htmlCache.current.set(log, cached);
    }
    htmls[i] = cached;
  }

  // Filter logs by level
  const filteredIndices = useMemo(() => {
    return logs.reduce<number[]>((acc, log, i) => {
      if (filter === 'ALL') { acc.push(i); return acc; }
      const upper = log.toUpperCase();
      if (filter === 'ERROR' && (upper.includes('[ERROR]') || upper.includes('| ERROR |'))) acc.push(i);
      else if (filter === 'WARN' && (upper.includes('[WARN]') || upper.includes('| WARNING |'))) acc.push(i);
      else if (filter === 'INFO' && !upper.includes('[ERROR]') && !upper.includes('[WARN]') && !upper.includes('| ERROR |') && !upper.includes('| WARNING |')) acc.push(i);
      return acc;
    }, []);
  }, [logs, filter]);

  // Auto-scroll unless paused
  useEffect(() => {
    if (!paused && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs.length, paused]);

  const handleCopy = useCallback(() => {
    const text = logs.join('\n');
    navigator.clipboard.writeText(text).then(() => message.success('日志已复制', 1.5)).catch(() => message.error('复制失败'));
  }, [logs]);

  const filterLabels: Array<'ALL' | 'ERROR' | 'WARN' | 'INFO'> = ['ALL', 'ERROR', 'WARN', 'INFO'];
  const filterColors: Record<string, string> = {
    ALL: '#94a3b8',
    ERROR: '#ef4444',
    WARN: '#f59e0b',
    INFO: '#22c55e',
  };

  return (
    <div className={styles.terminalContainer}>
      <div className={styles.terminalHeader}>
        <div className={styles.terminalDots}>
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
        </div>
        <CodeOutlined style={{ fontSize: 11 }} />
        <span style={{ flex: 1 }}>系统输出</span>
        {/* Log level filter */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <FilterOutlined style={{ fontSize: 10, color: '#64748b', marginRight: 2 }} />
          {filterLabels.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                fontSize: 9, padding: '1px 6px', borderRadius: 3,
                border: `1px solid ${filter === f ? filterColors[f] : 'rgba(255,255,255,0.08)'}`,
                background: filter === f ? `${filterColors[f]}22` : 'transparent',
                color: filter === f ? filterColors[f] : '#64748b',
                cursor: 'pointer', fontWeight: 600, letterSpacing: '0.03em',
                transition: 'all 0.2s',
              }}
            >{f}</button>
          ))}
        </div>
        {/* Pause scroll toggle */}
        <Tooltip title={paused ? '恢复自动滚动' : '暂停自动滚动'} placement="top">
          <button
            onClick={() => setPaused(p => !p)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px',
              color: paused ? '#f59e0b' : '#475569', fontSize: 13, lineHeight: 1,
              transition: 'color 0.2s',
            }}
            aria-label={paused ? '恢复滚动' : '暂停滚动'}
          >
            {paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
          </button>
        </Tooltip>
        {/* Copy all logs */}
        <Tooltip title="复制全部日志" placement="top">
          <button
            onClick={handleCopy}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px',
              color: '#475569', fontSize: 12, lineHeight: 1,
              transition: 'color 0.2s',
            }}
            aria-label="复制日志"
          >
            <CopyOutlined />
          </button>
        </Tooltip>
      </div>
      <div className={styles.terminalBody} ref={terminalRef}>
        {filteredIndices.length > 0 ? (
          filteredIndices.map(i => (
            <div
              key={keysRef.current[i]}
              className={styles.logLine}
              dangerouslySetInnerHTML={{ __html: htmls[i] ?? '' }}
            />
          ))
        ) : (
          <div className={styles.logLine}>
            {logs.length === 0 ? '$ 等待训练进程...' : `无 ${filter} 级别日志`}
          </div>
        )}
      </div>
    </div>
  );
});


/* ── Pulse Gauge for VRAM ── */
const PulseGauge = ({ value, label }: { value: number; label: string }) => (
  <div className={styles.statCard}>
    <div className={styles.statLabel}>{label}</div>
    <div className={styles.pulseRing}>
      <AnimatedValue value={String(value)} className={styles.statValue} />
    </div>
  </div>
);

/* ── Idle State ── */
const IdleView = ({
  selectedModel,
  selectedDataset,
  selectedMethod,
}: {
  selectedModel?: string;
  selectedDataset?: string;
  selectedMethod?: string;
}) => (
  <div className={styles.idleContainer}>
    <div className={styles.idleHero}>
      <div className={styles.idleOrb}>
        <RocketOutlined />
      </div>
      <div className={styles.idleTitle}>准备就绪</div>
      <div className={styles.idleSubtitle}>
        在左侧面板配置超参数，运行预检，然后开始训练。
      </div>
    </div>
    <div className={styles.summaryGrid}>
      <div className={styles.summaryCard}>
        <div className={styles.summaryLabel}>模型</div>
        <div className={selectedModel ? styles.summaryValueCyan : styles.summaryValue}>
          {selectedModel ? selectedModel.split('/').pop() || selectedModel : '—'}
        </div>
      </div>
      <div className={styles.summaryCard}>
        <div className={styles.summaryLabel}>数据集</div>
        <div className={selectedDataset ? styles.summaryValueCyan : styles.summaryValue}>
          {selectedDataset || '—'}
        </div>
      </div>
      <div className={styles.summaryCard}>
        <div className={styles.summaryLabel}>方法</div>
        <div className={selectedMethod ? styles.summaryValueCyan : styles.summaryValue}>
          {(selectedMethod || '—').toUpperCase()}
        </div>
      </div>
    </div>
  </div>
);

/* ── Phase Stepper ── */
const PHASE_ORDER = ['setup', 'load_model', 'load_dataset', 'build_trainer', 'train', 'save', 'cleanup'];
const PHASE_LABELS: Record<string, string> = {
  setup: '初始化',
  load_model: '加载模型',
  load_dataset: '加载数据',
  build_trainer: '构建训练器',
  train: '训练中',
  save: '保存结果',
  cleanup: '清理',
};

const PhaseStepper = ({ currentPhase, phaseDurations }: { currentPhase?: string; phaseDurations?: Record<string, number> }) => {
  const currentIndex = currentPhase ? PHASE_ORDER.indexOf(currentPhase) : -1;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 16, flexWrap: 'wrap' }}>
      {PHASE_ORDER.map((phase, index) => {
        const isActive = index === currentIndex;
        const isCompleted = index < currentIndex;
        const duration = phaseDurations?.[phase];
        return (
          <React.Fragment key={phase}>
            <div
              style={{
                padding: '4px 10px',
                borderRadius: 6,
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                background: isActive ? 'rgba(201,100,66,0.15)' : isCompleted ? 'rgba(255,255,255,0.06)' : 'transparent',
                color: isActive ? 'var(--accent-primary)' : isCompleted ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)',
                border: `1px solid ${isActive ? 'rgba(201,100,66,0.3)' : isCompleted ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.05)'}`,
                transition: 'all 0.3s ease',
                whiteSpace: 'nowrap',
              }}
            >
              {PHASE_LABELS[phase]}
              {duration !== undefined && duration > 0 && (
                <span style={{ marginLeft: 4, opacity: 0.6 }}>{Math.round(duration)}s</span>
              )}
            </div>
            {index < PHASE_ORDER.length - 1 && (
              <div style={{ width: 12, height: 1, background: isCompleted ? 'rgba(201,100,66,0.3)' : 'rgba(255,255,255,0.08)' }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};

/* ── Checkpoints Section ── */
const CheckpointsSection = ({
  checkpoints,
  currentTaskId,
  status,
  onResume,
}: {
  checkpoints: CheckpointInfo[];
  currentTaskId?: string | null;
  status: TrainingDashboardProps['status'];
  onResume?: (taskId: string, checkpointName: string) => void;
}) => (
  <div className={styles.snapshotLibrary}>
    <div className={styles.snapshotHeader}>
      <SaveOutlined style={{ fontSize: 12 }} />
      <span>检查点库 (Checkpoints)</span>
    </div>
    <div className={styles.snapshotGrid}>
      {checkpoints.length === 0 ? (
        <div className={styles.snapshotEmpty}>
          {status === 'training' || status === 'loading'
            ? '检查点将在训练过程中自动保存...'
            : '暂无检查点'}
        </div>
      ) : (
        checkpoints.map((cp) => (
          <div
            key={cp.name}
            className={styles.snapshotCard}
            style={!cp.valid ? { opacity: 0.5 } : undefined}
          >
            <div className={styles.snapshotStep}>
              步数 {cp.step}
              {!cp.valid && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--error)' }}>无效</span>}
            </div>
            <div className={styles.snapshotMetrics}>
              {cp.metadata?.loss != null ? `Loss: ${Number(cp.metadata.loss).toFixed(4)}` : '--'}
            </div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>
              {formatCheckpointTime(cp.metadata?.saved_at) || formatCheckpointTime(cp.created)}
            </div>
            {onResume && currentTaskId && cp.valid && (status === 'idle' || status === 'completed' || status === 'failed') && (
              <button
                className={styles.resultBtn}
                style={{ marginTop: 6, fontSize: 11, padding: '4px 10px' }}
                onClick={() => onResume(currentTaskId, cp.name)}
              >
                从此恢复
              </button>
            )}
          </div>
        ))
      )}
    </div>
  </div>
);

/* ── Main Dashboard ── */
const TrainingDashboard: React.FC<TrainingDashboardProps> = ({
  progress,
  chartData,
  status,
  selectedModel,
  selectedDataset,
  selectedMethod,
  onReset,
  phaseDurations,
  currentPhase,
  retryCount,
  currentTaskId,
  onResume,
}) => {
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const logsRef = useRef<string[]>([]);
  const logBufferRef = useRef<string[]>([]);
  const logFlushTimerRef = useRef<number | null>(null);

  // Fetch real checkpoints (with in-flight guard)
  const checkpointsInFlightRef = useRef(false);
  const fetchCheckpoints = useCallback(async () => {
    if (!currentTaskId || checkpointsInFlightRef.current) { if (!currentTaskId) setCheckpoints([]); return; }
    checkpointsInFlightRef.current = true;
    try {
      const data = await getTrainingCheckpoints(currentTaskId);
      if (Array.isArray(data)) setCheckpoints(data);
    } catch { /* ignore */ } finally {
      checkpointsInFlightRef.current = false;
    }
  }, [currentTaskId]);

  useEffect(() => {
    fetchCheckpoints();
    if (currentTaskId && (status === 'training' || status === 'loading' || status === 'saving')) {
      const timer = setInterval(fetchCheckpoints, 10000);
      return () => clearInterval(timer);
    }
  }, [currentTaskId, status, fetchCheckpoints]);

  // Stream real training logs (batched updates)
  useEffect(() => {
    if (!currentTaskId || (status !== 'training' && status !== 'loading')) {
      return;
    }
    const unsub = subscribeTrainingLogs(
      currentTaskId,
      (line: string) => {
        logBufferRef.current.push(line);
        if (logFlushTimerRef.current === null) {
          logFlushTimerRef.current = requestAnimationFrame(() => {
            logFlushTimerRef.current = null;
            const buf = logBufferRef.current;
            if (buf.length === 0) return;
            logBufferRef.current = [];
            const updated = [...logsRef.current, ...buf].slice(-200);
            logsRef.current = updated;
            setLogs(updated);
          });
        }
      },
      undefined,
      50,
    );
    return () => {
      unsub();
      if (logFlushTimerRef.current !== null) {
        cancelAnimationFrame(logFlushTimerRef.current);
        logFlushTimerRef.current = null;
      }
      // Flush remaining buffer
      const buf = logBufferRef.current;
      if (buf.length > 0) {
        logBufferRef.current = [];
        const updated = [...logsRef.current, ...buf].slice(-200);
        logsRef.current = updated;
        setLogs(updated);
      }
    };
  }, [currentTaskId, status]);

  // Reset logs when task changes
  useEffect(() => {
    logsRef.current = [];
    logBufferRef.current = [];
    setLogs([]);
  }, [currentTaskId]);

  const pct = progress?.totalSteps
    ? Math.round((progress.step / progress.totalSteps) * 100)
    : 0;

  /* ── IDLE ── */
  if (status === 'idle') {
    return (
      <div className={styles.dashboardContainer}>
        <IdleView
          selectedModel={selectedModel}
          selectedDataset={selectedDataset}
          selectedMethod={selectedMethod}
        />
      </div>
    );
  }

  /* ── LOADING / QUEUED ── */
  if (status === 'loading' || status === 'queued') {
    // elapsed_time 由后端心跳线程每5秒更新一次
    const elapsedSec = progress?.elapsedTime ? Math.round(progress.elapsedTime) : null;
    const elapsedLabel =
      elapsedSec !== null
        ? elapsedSec >= 60
          ? `${Math.floor(elapsedSec / 60)}m ${elapsedSec % 60}s`
          : `${elapsedSec}s`
        : null;

    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.loadingContainer}>
          <div className={styles.loadingSpinner} />
          <div className={styles.loadingTitle}>
            {status === 'queued' ? '任务已入队' : '正在初始化训练环境'}
          </div>

          {/* 阶段指示器 */}
          {currentPhase && status === 'loading' && (
            <div style={{ marginTop: 12, marginBottom: 4 }}>
              <PhaseStepper currentPhase={currentPhase} phaseDurations={phaseDurations} />
            </div>
          )}

          {/* 后端心跳推送的实时 message */}
          <div className={styles.loadingDesc}>
            {progress?.message ||
              (status === 'queued'
                ? '资源繁忙。您的任务已入队，将自动开始。'
                : '正在准备训练环境，请稍候。')}
          </div>

          {/* elapsed time —— 心跳线程驱动，每5s更新 */}
          {elapsedLabel && status === 'loading' && (
            <div style={{
              marginTop: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontFamily: 'var(--font-mono)',
              color: 'rgba(255,255,255,0.35)',
              fontSize: 12,
            }}>
              <span style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--accent-primary)',
                boxShadow: '0 0 6px var(--accent-primary)',
                animation: 'pulse 1.5s ease-in-out infinite',
              }} />
              已等待 <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{elapsedLabel}</span>
              &nbsp;· 模型首次加载通常需要 1–5 分钟
            </div>
          )}

          {/* 队列位置 */}
          {status === 'queued' && progress?.queuePosition && (
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)' }}>
                #{progress.queuePosition}
              </div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                队列位置
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ── STOPPING ── */
  if (status === 'stopping') {
    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.stoppingContainer}>
          <div className={styles.stoppingSpinner} />
          <div className={styles.loadingTitle}>正在平滑关闭</div>
          <div className={styles.loadingDesc}>
            {progress?.message || '正在等待当前步骤完成以安全停止。'}
          </div>
        </div>
      </div>
    );
  }

  /* ── SAVING ── */
  if (status === 'saving') {
    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.stoppingContainer}>
          <div className={styles.stoppingSpinner} />
          <div className={styles.loadingTitle}>模型保存中</div>
          <div className={styles.loadingDesc}>
            训练已完成，正在保存模型到磁盘...
          </div>
        </div>
      </div>
    );
  }

  /* ── COMPLETED ── */
  if (status === 'completed') {
    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.resultContainer}>
          <CheckCircleOutlined className={styles.resultIconSuccess} />
          <div className={styles.resultTitle}>训练完成</div>
          <div className={styles.resultSummary}>
            <div className={styles.resultStat}>
              <div className={styles.resultStatLabel}>最终损失 (Loss)</div>
              <div className={styles.resultStatValue}>
                {progress?.loss?.toFixed(4) ?? '--'}
              </div>
            </div>
            <div className={styles.resultStat}>
              <div className={styles.resultStatLabel}>总步数</div>
              <div className={styles.resultStatValue}>{progress?.step ?? '--'}</div>
            </div>
            <div className={styles.resultStat}>
              <div className={styles.resultStatLabel}>耗时</div>
              <div className={styles.resultStatValue}>
                {progress?.elapsedTime ? `${Math.floor(progress.elapsedTime / 60)}m` : '--'}
              </div>
            </div>
          </div>
          {onReset && (
            <div className={styles.resultActions}>
              <button className={styles.resultBtn} onClick={onReset}>
                开启新训练
              </button>
            </div>
          )}
          <CheckpointsSection checkpoints={checkpoints} currentTaskId={currentTaskId} status={status} onResume={onResume} />
        </div>
      </div>
    );
  }

  /* ── FAILED ── */
  if (status === 'failed') {
    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.resultContainer}>
          <CloseCircleOutlined className={styles.resultIconFail} />
          <div className={styles.resultTitle}>训练失败</div>
          <div className={styles.resultMessage}>
            {progress?.message || '训练过程中发生错误。请检查日志以获取详细信息。'}
          </div>
          {Array.isArray(progress?.actionableSuggestions) && progress.actionableSuggestions.length > 0 && (
            <div style={{
              background: 'rgba(255,107,107,0.06)',
              border: '1px solid rgba(255,107,107,0.15)',
              borderRadius: 8,
              padding: '12px 16px',
              maxWidth: 420,
              width: '100%',
            }}>
              {progress.actionableSuggestions.map((s, i) => (
                <div key={i} style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
                  • {s}
                </div>
              ))}
            </div>
          )}
          {onReset && (
            <div className={styles.resultActions}>
              <button className={styles.resultBtn} onClick={onReset}>
                重新配置
              </button>
            </div>
          )}
          <CheckpointsSection checkpoints={checkpoints} currentTaskId={currentTaskId} status={status} onResume={onResume} />
        </div>
      </div>
    );
  }

  /* ── TRAINING (active) ── */
  return (
    <div className={styles.dashboardContainer}>
      <div className={styles.dashboardContent}>
        {/* Phase Stepper */}
        <PhaseStepper currentPhase={currentPhase} phaseDurations={phaseDurations} />

        {/* Retry indicator */}
        {retryCount !== undefined && retryCount > 0 && (
          <div style={{ marginBottom: 8 }}>
            <Tag color="warning" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              <ThunderboltOutlined style={{ marginRight: 4 }} />
              自动重试中 ({retryCount})
            </Tag>
          </div>
        )}

        {/* Stats Grid */}
        <div className={styles.statsRow}>
          <PulseGauge
            value={progress?.vramUsed ? Number(progress.vramUsed.toFixed(1)) : 0}
            label="显存 (GB)"
          />
          <div className={styles.statCard}>
            <div className={styles.statLabel}>损失 (Loss)</div>
            <AnimatedValue
              value={progress?.loss ? progress.loss.toFixed(4) : '--'}
              className={styles.statValueLoss}
            />
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>轮数 (Epoch)</div>
            <AnimatedValue
              value={progress?.epoch ? progress.epoch.toFixed(2) : '--'}
              className={styles.statValueNeon}
            />
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>速度</div>
            <AnimatedValue
              value={progress?.speed ? `${progress.speed.toFixed(1)} s/s` : '--'}
              className={styles.statValueWhite}
            />
          </div>
        </div>

        {/* Secondary Stats Row */}
        <div className={styles.statsRow} style={{ marginTop: 8 }}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>样本/秒</div>
            <AnimatedValue
              value={progress?.samplesPerSec ? `${progress.samplesPerSec.toFixed(1)}` : '--'}
              className={styles.statValueWhite}
            />
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>梯度范数</div>
            <AnimatedValue
              value={progress?.gradNorm ? progress.gradNorm.toFixed(3) : '--'}
              className={styles.statValueWhite}
            />
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>预计剩余</div>
            <AnimatedValue
              value={progress?.eta ? `${Math.floor(progress.eta / 60)}m ${Math.floor(progress.eta % 60)}s` : '--'}
              className={styles.statValueWhite}
            />
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>学习率</div>
            <AnimatedValue
              value={progress?.lr ? progress.lr.toExponential(2) : '--'}
              className={styles.statValueWhite}
            />
          </div>
        </div>

        {/* Step Progress Bar */}
        <div style={{ marginTop: 16 }}>
          <div className={styles.progressBarContainer}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
          <div className={styles.progressText}>
            <span className={styles.progressLabel}>
              当前步数 {progress?.step || 0} / {progress?.totalSteps || '?'}
            </span>
            <span className={styles.progressPercent}>{pct}%</span>
          </div>
        </div>

        {/* Chart Tabs - Loss/LR + VRAM */}
        <div className={styles.chartWrapper}>
          <div className={styles.chartHeader}>
            <span className={styles.chartTitle}>训练指标回顾</span>
            <div className={styles.chartLegend}>
              <div className={styles.legendItem}>
                <span className={`${styles.legendDot} ${styles.legendDotLoss}`} />
                损失 (Loss)
              </div>
              <div className={styles.legendItem}>
                <span className={`${styles.legendDot} ${styles.legendDotLr}`} />
                学习率 (LR)
              </div>
            </div>
          </div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <defs>
                  <linearGradient id="lossGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#FF6B6B" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#FF6B6B" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                <XAxis
                  dataKey="step"
                  stroke="rgba(255,255,255,0.1)"
                  tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', style: { fontVariantNumeric: 'tabular-nums' } }}
                  axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                />
                <YAxis
                  yAxisId="left"
                  stroke="transparent"
                  tick={{ fill: 'rgba(255, 107, 107, 0.5)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', style: { fontVariantNumeric: 'tabular-nums' } }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="transparent"
                  tick={{ fill: 'rgba(201, 100, 66, 0.5)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', style: { fontVariantNumeric: 'tabular-nums' } }}
                />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: 'rgba(0,0,0,0.9)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '8px',
                    fontFamily: 'var(--font-mono, monospace)',
                    fontSize: 11,
                    boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    padding: '10px 14px',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                  labelStyle={{ color: 'rgba(255,255,255,0.4)', marginBottom: 4 }}
                />
                <Line
                  yAxisId="left" type="monotone" dataKey="loss"
                  stroke="#FF6B6B" strokeWidth={2} dot={false}
                  activeDot={{ r: 4, fill: '#FF6B6B', stroke: 'rgba(255,107,107,0.3)', strokeWidth: 6 }}
                />
                <Line
                  yAxisId="right" type="monotone" dataKey="lr"
                  stroke="#c96442" strokeWidth={1.5} dot={false}
                  strokeDasharray="4 4"
                  activeDot={{ r: 4, fill: '#c96442', stroke: 'rgba(201,100,66,0.3)', strokeWidth: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{
              height: 220,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.12)',
              fontSize: 11,
              fontFamily: 'var(--font-mono, monospace)',
            }}>
              正在等待数据点...
            </div>
          )}
        </div>

        {/* VRAM Chart */}
        {chartData.some((d) => d.vram !== undefined && d.vram > 0) && (
          <div className={styles.chartWrapper} style={{ marginTop: 12 }}>
            <div className={styles.chartHeader}>
              <span className={styles.chartTitle}>显存使用趋势</span>
              <div className={styles.chartLegend}>
                <div className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: '#7B61FF' }} />
                  VRAM (GB)
                </div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <defs>
                  <linearGradient id="vramGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7B61FF" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#7B61FF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                <XAxis
                  dataKey="step"
                  stroke="rgba(255,255,255,0.1)"
                  tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', style: { fontVariantNumeric: 'tabular-nums' } }}
                  axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                />
                <YAxis
                  stroke="transparent"
                  tick={{ fill: 'rgba(123, 97, 255, 0.5)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', style: { fontVariantNumeric: 'tabular-nums' } }}
                />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: 'rgba(0,0,0,0.9)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '8px',
                    fontFamily: 'var(--font-mono, monospace)',
                    fontSize: 11,
                    boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    padding: '10px 14px',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                  labelStyle={{ color: 'rgba(255,255,255,0.4)', marginBottom: 4 }}
                />
                <Area
                  type="monotone"
                  dataKey="vram"
                  stroke="#7B61FF"
                  strokeWidth={2}
                  fill="url(#vramGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: '#7B61FF', stroke: 'rgba(123,97,255,0.3)', strokeWidth: 6 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Terminal */}
        <TerminalStream logs={logs} />

        {/* Checkpoints */}
        <CheckpointsSection checkpoints={checkpoints} currentTaskId={currentTaskId} status={status} onResume={onResume} />
      </div>
    </div>
  );
};

export default TrainingDashboard;
