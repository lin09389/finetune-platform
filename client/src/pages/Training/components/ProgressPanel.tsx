import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  HourglassOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Badge, Progress, Steps } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import React from 'react';
import NeumorphicButton from '../../../components/shared/NeumorphicButton';
import styles from './ProgressPanel.module.css';

interface TrainingProgress {
  epoch: number;
  step: number;
  totalSteps: number;
  loss?: number;
  lr?: number;
  vramUsed?: number;
  elapsedTime?: number;
  message?: string;
  status?: string;
  queuePosition?: number;
  estimatedWaitSeconds?: number;
  errorCategory?: string;
  actionableSuggestions?: string[];
}

interface ProgressPanelProps {
  status: 'idle' | 'queued' | 'loading' | 'training' | 'stopping' | 'completed' | 'failed';
  progress: TrainingProgress | null;
  connectionState?: 'connected' | 'degraded' | 'disconnected';
  onReset: () => void;
}

const ProgressPanel: React.FC<ProgressPanelProps> = ({
  status,
  progress,
  connectionState = 'disconnected',
  onReset,
}) => {
  const getStepsCurrent = (currentStatus: string): number => {
    if (currentStatus === 'queued') return 0;
    if (currentStatus === 'loading') return 1;
    if (currentStatus === 'training' || currentStatus === 'stopping') return 2;
    if (currentStatus === 'completed' || currentStatus === 'failed') return 3;
    return 0;
  };

  return (
    <div className={styles.container} style={{ position: 'relative' }}>
      {/* 链路状态指示器 */}
      {status !== 'idle' && status !== 'completed' && status !== 'failed' && (
        <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 10 }}>
          <div
            title={
              connectionState === 'connected'
                ? 'V2 实时事件流 (主通道在线)'
                : connectionState === 'degraded'
                  ? '轮询同步 (网络波动，已降级备用通道)'
                  : '链路连接中'
            }
          >
            <Badge
              status={
                connectionState === 'connected'
                  ? 'processing'
                  : connectionState === 'degraded'
                    ? 'warning'
                    : 'default'
              }
              text={
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {connectionState === 'connected'
                    ? 'SSE 在线'
                    : connectionState === 'degraded'
                      ? '降级轮询'
                      : '连接中'}
                </span>
              }
            />
          </div>
        </div>
      )}

      <AnimatePresence mode="wait">
        {status === 'idle' && (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.emptyState}
          >
            <div className={styles.emptyIcon}>
              <ThunderboltOutlined />
            </div>
            <h4 className={styles.emptyTitle}>等待训练</h4>
            <p className={styles.emptyDesc}>选择模型和数据集后即可开始训练。</p>
          </motion.div>
        )}

        {status === 'queued' && (
          <motion.div
            key="queued"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.loadingState}
          >
            <div className={styles.loadingIcon} style={{ color: 'var(--accent-primary)' }}>
              <HourglassOutlined spin />
            </div>
            <h4 className={styles.loadingTitle}>任务排队中</h4>
            <p className={styles.loadingDesc}>
              {progress?.message || '资源紧张，任务正在队列中等待调度。'}
            </p>
            {progress?.queuePosition ? (
              <div style={{ marginTop: 'var(--space-6)', textAlign: 'center' }}>
                <div style={{ fontSize: '1.2em' }}>
                  队列前方排队：
                  <strong style={{ color: 'var(--accent-primary)', fontSize: '1.5em' }}>
                    {progress.queuePosition}
                  </strong>{' '}
                  人
                </div>
                <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>
                  预计仍需等待 {Math.max(0, Math.floor((progress.estimatedWaitSeconds || 0) / 60))}{' '}
                  分钟
                </div>
              </div>
            ) : null}
            <Steps
              current={getStepsCurrent(status)}
              size="small"
              className={styles.steps}
              style={{ marginTop: 'var(--space-8)' }}
              items={[
                { title: '排队', icon: <HourglassOutlined /> },
                { title: '加载', icon: <ClockCircleOutlined /> },
                { title: '训练', icon: <ThunderboltOutlined /> },
                { title: '完成', icon: <CheckCircleOutlined /> },
              ]}
            />
          </motion.div>
        )}

        {status === 'loading' && (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.loadingState}
          >
            <div className={styles.loadingIcon}>
              <LoadingOutlined spin />
            </div>
            <h4 className={styles.loadingTitle}>正在加载模型...</h4>
            <p className={styles.loadingDesc}>
              {progress?.message || '正在准备训练环境，请稍候。'}
            </p>
            <Steps
              current={getStepsCurrent(status)}
              size="small"
              className={styles.steps}
              style={{ marginTop: 'var(--space-8)' }}
              items={[
                { title: '排队', icon: <HourglassOutlined /> },
                { title: '加载', icon: <ClockCircleOutlined /> },
                { title: '训练', icon: <ThunderboltOutlined /> },
                { title: '完成', icon: <CheckCircleOutlined /> },
              ]}
            />
          </motion.div>
        )}

        {status === 'training' && progress && (
          <motion.div
            key="training"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.trainingState}
          >
            <div className={styles.progressCircle}>
              <Progress
                type="circle"
                percent={Math.round((progress.step / (progress.totalSteps || 1)) * 100)}
                strokeColor="var(--accent-primary)"
                strokeWidth={8}
                size={160}
                format={(percent) => (
                  <div className={styles.circleContent}>
                    <span className={styles.percentText}>{percent}%</span>
                    <span className={styles.stepText}>
                      {progress.step} / {progress.totalSteps}
                    </span>
                  </div>
                )}
              />
            </div>

            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <label>Loss</label>
                <div className={styles.statValue} style={{ color: 'var(--accent-primary)' }}>
                  {progress.loss?.toFixed(4) || '--'}
                </div>
              </div>
              <div className={styles.statItem}>
                <label>Learning Rate</label>
                <div className={styles.statValue}>{progress.lr?.toExponential(2) || '--'}</div>
              </div>
              <div className={styles.statItem}>
                <label>显存使用</label>
                <div className={styles.statValue}>{progress.vramUsed?.toFixed(1) || 0} GB</div>
              </div>
              <div className={styles.statItem}>
                <label>已用时间</label>
                <div className={styles.statValue}>
                  {Math.floor((progress.elapsedTime || 0) / 60)} 分钟
                </div>
              </div>
            </div>

            <Steps
              current={getStepsCurrent(status)}
              size="small"
              className={styles.steps}
              items={[
                { title: '排队', icon: <HourglassOutlined /> },
                { title: '加载', icon: <ClockCircleOutlined /> },
                { title: '训练', icon: <ThunderboltOutlined /> },
                { title: '完成', icon: <CheckCircleOutlined /> },
              ]}
            />
          </motion.div>
        )}

        {status === 'stopping' && (
          <motion.div
            key="stopping"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.loadingState}
          >
            <div className={styles.loadingIcon}>
              <LoadingOutlined spin />
            </div>
            <h4 className={styles.loadingTitle}>正在安全停止训练...</h4>
            <p className={styles.loadingDesc}>
              {progress?.message || '已收到停止请求，等待当前步骤完成。'}
            </p>
          </motion.div>
        )}

        {status === 'completed' && (
          <motion.div
            key="completed"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className={styles.resultState}
          >
            <div className={styles.successIcon}>
              <CheckCircleOutlined />
            </div>
            <h3 className={styles.resultTitle}>训练已完成</h3>
            <div className={styles.resultSummary}>
              <div className={styles.summaryItem}>
                最终 Loss: <strong>{progress?.loss?.toFixed(4)}</strong>
              </div>
              <div className={styles.summaryItem}>
                总步数: <strong>{progress?.step}</strong>
              </div>
              <div className={styles.summaryItem}>
                总耗时: <strong>{Math.floor((progress?.elapsedTime || 0) / 60)} 分钟</strong>
              </div>
            </div>
            <NeumorphicButton variant="primary" onClick={onReset}>
              开始新训练
            </NeumorphicButton>
          </motion.div>
        )}

        {status === 'failed' && (
          <motion.div
            key="failed"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={styles.resultState}
          >
            <Alert
              type="error"
              message="训练失败中止"
              description={
                progress?.message || '训练过程中发生异常，您可以查看下方的诊断建议进行恢复。'
              }
              showIcon
              style={{ width: '100%', marginBottom: 'var(--space-6)' }}
            />
            {Array.isArray(progress?.actionableSuggestions) &&
            progress?.actionableSuggestions.length > 0 ? (
              <div className={styles.suggestionBox}>
                {progress.actionableSuggestions.map((item, idx) => (
                  <div key={`${item}-${idx}`}>• {item}</div>
                ))}
              </div>
            ) : null}
            <NeumorphicButton variant="secondary" onClick={onReset}>
              重新配置
            </NeumorphicButton>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ProgressPanel;
