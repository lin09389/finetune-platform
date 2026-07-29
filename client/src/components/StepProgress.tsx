import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { AnimatePresence, motion } from 'framer-motion';
import React, { memo, useMemo } from 'react';

interface Step {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  description?: string;
}

interface StepProgressProps {
  steps: Step[];
  currentStep: number;
}

const statusConfig = {
  pending: {
    icon: <ClockCircleOutlined />,
    color: 'var(--text-tertiary)',
    bgColor: 'var(--bg-elevated)',
    borderColor: 'var(--border-color)',
  },
  running: {
    icon: <LoadingOutlined />,
    color: 'var(--primary-500)',
    bgColor: 'var(--primary-500)',
    borderColor: 'var(--primary-500)',
  },
  completed: {
    icon: <CheckCircleOutlined />,
    color: 'var(--success)',
    bgColor: 'var(--success)',
    borderColor: 'var(--success)',
  },
  error: {
    icon: <CloseCircleOutlined />,
    color: 'var(--error)',
    bgColor: 'var(--error)',
    borderColor: 'var(--error)',
  },
};

const StepProgress: React.FC<StepProgressProps> = memo(({ steps, currentStep }) => {
  const progress = useMemo(() => {
    const completedSteps = steps.filter((s) => s.status === 'completed').length;
    const runningStep = steps.findIndex((s) => s.status === 'running');
    const partialProgress = runningStep >= 0 ? 0.5 : 0;
    return ((completedSteps + partialProgress) / steps.length) * 100;
  }, [steps]);

  const overallStatus = useMemo(() => {
    if (steps.some((s) => s.status === 'error')) return 'error';
    if (steps.every((s) => s.status === 'completed')) return 'completed';
    if (steps.some((s) => s.status === 'running')) return 'running';
    return 'pending';
  }, [steps]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        padding: '16px 20px',
        background: 'var(--bg-secondary)',
        borderRadius: 12,
        border: '1px solid var(--border-color)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          执行进度
        </span>
        <span
          style={{
            fontSize: 13,
            color: statusConfig[overallStatus].color,
            fontWeight: 500,
          }}
        >
          {Math.round(progress)}%
        </span>
      </div>

      <div
        style={{
          position: 'relative',
          height: 6,
          background: 'var(--bg-color)',
          borderRadius: 3,
          overflow: 'hidden',
        }}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            background:
              overallStatus === 'error'
                ? 'var(--error)'
                : 'linear-gradient(90deg, var(--primary-500) 0%, var(--accent-primary) 100%)',
            borderRadius: 3,
          }}
        />
        {overallStatus === 'running' && (
          <motion.div
            animate={{
              x: ['-100%', '400%'],
            }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              width: '25%',
              height: '100%',
              background: 'linear-gradient(90deg, transparent, var(--shimmer-overlay), transparent)',
            }}
          />
        )}
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {steps.map((step, index) => {
          const config = statusConfig[step.status];
          const isLast = index === steps.length - 1;

          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05 }}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                }}
              >
                <motion.div
                  animate={
                    step.status === 'running'
                      ? {
                          scale: [1, 1.1, 1],
                        }
                      : {}
                  }
                  transition={{
                    duration: 1,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: config.bgColor,
                    border: `2px solid ${config.borderColor}`,
                    color: step.status === 'pending' ? config.color : 'var(--text-inverse)',
                    flexShrink: 0,
                  }}
                >
                  {step.status === 'running' ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    >
                      {config.icon}
                    </motion.div>
                  ) : (
                    config.icon
                  )}
                </motion.div>

                {!isLast && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: 24 }}
                    transition={{ duration: 0.3, delay: index * 0.05 }}
                    style={{
                      width: 2,
                      background: index < currentStep ? 'var(--success)' : 'var(--border-color)',
                      marginTop: 4,
                    }}
                  />
                )}
              </div>

              <div
                style={{
                  flex: 1,
                  paddingTop: 4,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color:
                        step.status === 'pending' ? 'var(--text-tertiary)' : 'var(--text-primary)',
                    }}
                  >
                    {step.name}
                  </span>

                  <AnimatePresence>
                    {step.status === 'running' && (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        style={{
                          fontSize: 10,
                          padding: '2px 6px',
                          background: 'var(--primary-50)',
                          color: 'var(--primary-500)',
                          borderRadius: 4,
                          fontWeight: 500,
                        }}
                      >
                        进行中
                      </motion.span>
                    )}
                  </AnimatePresence>
                </div>

                <AnimatePresence>
                  {step.description && step.status !== 'pending' && (
                    <motion.p
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      style={{
                        fontSize: 12,
                        color: 'var(--text-secondary)',
                        margin: '4px 0 0',
                        lineHeight: 1.5,
                      }}
                    >
                      {step.description}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          );
        })}
      </div>

      {overallStatus === 'running' && (
        <motion.div
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '8px 12px',
            background: 'var(--primary-50)',
            borderRadius: 8,
            marginTop: 4,
          }}
        >
          <LoadingOutlined style={{ fontSize: 12, color: 'var(--primary-500)' }} />
          <span
            style={{
              fontSize: 12,
              color: 'var(--primary-500)',
              fontWeight: 500,
            }}
          >
            正在处理，请稍候...
          </span>
        </motion.div>
      )}

      {overallStatus === 'completed' && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '8px 12px',
            background: 'rgba(34, 197, 94, 0.1)',
            borderRadius: 8,
            marginTop: 4,
          }}
        >
          <CheckCircleOutlined style={{ fontSize: 14, color: 'var(--success)' }} />
          <span
            style={{
              fontSize: 12,
              color: 'var(--success)',
              fontWeight: 500,
            }}
          >
            所有步骤已完成
          </span>
        </motion.div>
      )}

      {overallStatus === 'error' && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '8px 12px',
            background: 'rgba(239, 68, 68, 0.1)',
            borderRadius: 8,
            marginTop: 4,
          }}
        >
          <CloseCircleOutlined style={{ fontSize: 14, color: 'var(--error)' }} />
          <span
            style={{
              fontSize: 12,
              color: 'var(--error)',
              fontWeight: 500,
            }}
          >
            执行过程中出现错误
          </span>
        </motion.div>
      )}
    </div>
  );
});

StepProgress.displayName = 'StepProgress';

export default StepProgress;
