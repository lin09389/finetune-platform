import React from 'react'
import { Progress, Steps, Alert } from 'antd'
import { 
  CheckCircleOutlined, 
  ClockCircleOutlined, 
  ThunderboltOutlined,
  LoadingOutlined
} from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import NeumorphicButton from '../../../components/shared/NeumorphicButton'
import styles from './ProgressPanel.module.css'

interface TrainingProgress {
  epoch: number
  step: number
  totalSteps: number
  loss?: number
  lr?: number
  vramUsed?: number
  elapsedTime?: number
  message?: string
  status?: string
}

interface ProgressPanelProps {
  status: 'idle' | 'loading' | 'training' | 'completed' | 'failed'
  progress: TrainingProgress | null
  onReset: () => void
}

const ProgressPanel: React.FC<ProgressPanelProps> = ({
  status,
  progress,
  onReset,
}) => {
  const getStepsCurrent = (s: string): number => {
    if (s === 'completed' || s === 'failed') return 2
    if (s === 'training' || s === 'loading') return 1
    return 0
  }

  return (
    <div className={styles.container}>
      <AnimatePresence mode="wait">
        {status === 'idle' && (
          <motion.div 
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={styles.emptyState}
          >
            <div className={styles.emptyIcon}><ThunderboltOutlined /></div>
            <h4 className={styles.emptyTitle}>待训练</h4>
            <p className={styles.emptyDesc}>选择模型和数据集后开始训练</p>
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
            <div className={styles.loadingIcon}><LoadingOutlined spin /></div>
            <h4 className={styles.loadingTitle}>正在加载模型...</h4>
            <p className={styles.loadingDesc}>{progress?.message || '正在准备环境，请稍候'}</p>
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
                format={(p) => (
                  <div className={styles.circleContent}>
                    <span className={styles.percentText}>{p}%</span>
                    <span className={styles.stepText}>{progress.step} / {progress.totalSteps}</span>
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
                <div className={styles.statValue}>
                  {progress.lr?.toExponential(2) || '--'}
                </div>
              </div>
              <div className={styles.statItem}>
                <label>显存使用</label>
                <div className={styles.statValue}>
                  {progress.vramUsed?.toFixed(1) || 0} GB
                </div>
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
                { title: '加载', icon: <ClockCircleOutlined /> },
                { title: '训练', icon: <ThunderboltOutlined /> },
                { title: '完成', icon: <CheckCircleOutlined /> },
              ]}
            />
          </motion.div>
        )}

        {status === 'completed' && (
          <motion.div 
            key="completed"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className={styles.resultState}
          >
            <div className={styles.successIcon}><CheckCircleOutlined /></div>
            <h3 className={styles.resultTitle}>训练圆满完成</h3>
            <div className={styles.resultSummary}>
              <div className={styles.summaryItem}>最终 Loss: <strong>{progress?.loss?.toFixed(4)}</strong></div>
              <div className={styles.summaryItem}>总步数: <strong>{progress?.step}</strong></div>
              <div className={styles.summaryItem}>总耗时: <strong>{Math.floor((progress?.elapsedTime || 0) / 60)} 分钟</strong></div>
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
              message="训练失败"
              description={progress?.message || '训练过程中发生异常，请检查日志。'}
              showIcon
              style={{ width: '100%', marginBottom: 'var(--space-6)' }}
            />
            <NeumorphicButton variant="secondary" onClick={onReset}>
              重新配置
            </NeumorphicButton>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default ProgressPanel
