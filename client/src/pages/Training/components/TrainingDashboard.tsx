import React, { useEffect, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer,
} from 'recharts';
import {
  CodeOutlined, SaveOutlined,
  RocketOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import { AnimatePresence, motion } from 'framer-motion';
import styles from './TrainingDashboard.module.css';
import type { TrainingProgress as TrainingProgressType } from '../../../types';

interface TrainingDashboardProps {
  progress: TrainingProgressType | null;
  chartData: { step: number; loss: number; lr: number }[];
  status: 'idle' | 'queued' | 'loading' | 'training' | 'stopping' | 'completed' | 'failed';
  selectedModel?: string;
  selectedDataset?: string;
  selectedMethod?: string;
  onReset?: () => void;
}

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
const TerminalStream = ({ logs = [] }: { logs: string[] }) => {
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  const highlightLog = (log: string) => {
    return log
      .replace(/\[METRIC\]/g, `<span class="${styles.tokenMetric}">[METRIC]</span>`)
      .replace(/\[ERROR\]/g, `<span class="${styles.tokenError}">[ERROR]</span>`)
      .replace(/\[WARN\]/g, `<span class="${styles.tokenWarn}">[WARN]</span>`)
      .replace(/\[STATE\]/g, `<span class="${styles.tokenState}">[STATE]</span>`)
      .replace(/\[VRAM\]/g, `<span class="${styles.tokenMetric}">[VRAM]</span>`)
      .replace(/(\[\d{2}:\d{2}:\d{2}\])/g, `<span class="${styles.tokenTime}">$1</span>`);
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
        <span>系统输出</span>
      </div>
      <div className={styles.terminalBody} ref={terminalRef}>
        {logs.length > 0 ? (
          logs.map((log, i) => (
            <div
              key={i}
              className={styles.logLine}
              dangerouslySetInnerHTML={{ __html: highlightLog(log) }}
            />
          ))
        ) : (
          <div className={styles.logLine}>$ 等待训练进程...</div>
        )}
      </div>
    </div>
  );
};

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

/* ── Main Dashboard ── */
const TrainingDashboard: React.FC<TrainingDashboardProps> = ({
  progress,
  chartData,
  status,
  selectedModel,
  selectedDataset,
  selectedMethod,
  onReset,
}) => {
  const fakeLogs = progress
    ? [
        `[${new Date().toLocaleTimeString()}] Training step ${progress.step}/${progress.totalSteps || '?'}`,
        `[METRIC] Loss: ${progress.loss?.toFixed(4) ?? '--'} | LR: ${progress.lr?.toExponential(2) ?? '--'}`,
        `[VRAM] Usage: ${progress.vramUsed?.toFixed(2) ?? '--'} GB`,
        ...(progress.message ? [`[STATE] ${progress.message}`] : []),
      ]
    : [];

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
    return (
      <div className={styles.dashboardContainer}>
        <div className={styles.loadingContainer}>
          <div className={styles.loadingSpinner} />
          <div className={styles.loadingTitle}>
            {status === 'queued' ? '任务已入队' : '正在加载模型...'}
          </div>
          <div className={styles.loadingDesc}>
            {progress?.message ||
              (status === 'queued'
                ? '资源繁忙。您的任务已入队，将自动开始。'
                : '正在准备训练环境，请稍候。')}
          </div>
          {status === 'queued' && progress?.queuePosition && (
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#00FFC2', fontFamily: 'var(--font-mono)' }}>
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
        </div>
      </div>
    );
  }

  /* ── TRAINING (active) ── */
  return (
    <div className={styles.dashboardContainer}>
      <div className={styles.dashboardContent}>
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
            <div className={styles.statLabel}>预计剩余</div>
            <AnimatedValue
              value={progress?.eta ? `${Math.floor(progress.eta / 60)}m` : '--'}
              className={styles.statValueWhite}
            />
          </div>
        </div>

        {/* Step Progress Bar */}
        <div>
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

        {/* Chart */}
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
                  tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)' }}
                  axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                />
                <YAxis
                  yAxisId="left"
                  stroke="transparent"
                  tick={{ fill: 'rgba(255, 107, 107, 0.5)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)' }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="transparent"
                  tick={{ fill: 'rgba(0, 255, 194, 0.5)', fontSize: 10, fontFamily: 'var(--font-mono, monospace)' }}
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
                  stroke="#00FFC2" strokeWidth={1.5} dot={false}
                  strokeDasharray="4 4"
                  activeDot={{ r: 4, fill: '#00FFC2', stroke: 'rgba(0,255,194,0.3)', strokeWidth: 6 }}
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

        {/* Terminal */}
        <TerminalStream logs={fakeLogs} />

        {/* Checkpoints */}
        <div className={styles.snapshotLibrary}>
          <div className={styles.snapshotHeader}>
            <SaveOutlined style={{ fontSize: 12 }} />
            <span>检查点库 (Checkpoints)</span>
          </div>
          <div className={styles.snapshotGrid}>
            {chartData.length === 0 ? (
              <div className={styles.snapshotEmpty}>暂无检查点</div>
            ) : (
              [1, 2, 3]
                .filter((i) => i * 500 <= (progress?.step || 0))
                .map((i) => (
                  <div key={i} className={styles.snapshotCard}>
                    <div className={styles.snapshotStep}>步数 {i * 500}</div>
                    <div className={styles.snapshotMetrics}>
                      {(1.5 - i * 0.2).toFixed(4)}
                    </div>
                  </div>
                ))
            )}
            {chartData.length > 0 && ![1, 2, 3].some((i) => i * 500 <= (progress?.step || 0)) && (
              <div className={styles.snapshotEmpty}>将在 500 步时自动保存...</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TrainingDashboard;
