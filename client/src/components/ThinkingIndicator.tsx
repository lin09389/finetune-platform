import {
  BulbOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { AnimatePresence, motion } from 'framer-motion';
import React, { memo, useMemo } from 'react';

interface ThinkingIndicatorProps {
  steps?: string[];
  currentStep?: number;
  className?: string;
}

const defaultSteps = ['分析问题', '检索知识', '生成回答'];

const stepIcons = [
  <BulbOutlined key="bulb" />,
  <ThunderboltOutlined key="thunder" />,
  <CheckCircleOutlined key="check" />,
];

const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = memo(
  ({ steps = defaultSteps, currentStep = 0, className }) => {
    const progress = useMemo(() => {
      if (steps.length === 0) return 0;
      return ((currentStep + 0.5) / steps.length) * 100;
    }, [currentStep, steps.length]);

    const currentStepText = useMemo(() => {
      if (currentStep >= 0 && currentStep < steps.length) {
        return steps[currentStep];
      }
      return '思考中...';
    }, [currentStep, steps]);

    return (
      <div
        className={className}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          padding: '16px 20px',
          background: 'linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-elevated) 100%)',
          borderRadius: 12,
          border: '1px solid var(--border-color)',
          minWidth: 280,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 24,
              height: 24,
            }}
          >
            <LoadingOutlined style={{ fontSize: 18, color: 'var(--primary-500)' }} />
          </motion.div>

          <AnimatePresence mode="wait">
            <motion.span
              key={currentStep}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--text-primary)',
              }}
            >
              {currentStepText}
            </motion.span>
          </AnimatePresence>
        </div>

        <div
          style={{
            position: 'relative',
            height: 4,
            background: 'var(--bg-color)',
            borderRadius: 2,
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
                'linear-gradient(90deg, var(--primary-500) 0%, var(--accent-primary) 100%)',
              borderRadius: 2,
            }}
          />
          <motion.div
            animate={{
              x: ['0%', '100%'],
              opacity: [0, 0.5, 0],
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
              width: '30%',
              height: '100%',
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)',
            }}
          />
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          {steps.map((step, index) => {
            const isCompleted = index < currentStep;
            const isCurrent = index === currentStep;
            const isPending = index > currentStep;
            const IconComponent = stepIcons[index % stepIcons.length];

            return (
              <motion.div
                key={index}
                initial={{ opacity: 0.5, scale: 0.95 }}
                animate={{
                  opacity: isPending ? 0.5 : 1,
                  scale: isCurrent ? 1.05 : 1,
                }}
                transition={{ duration: 0.3 }}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  flex: 1,
                }}
              >
                <motion.div
                  animate={
                    isCurrent
                      ? {
                          boxShadow: [
                            '0 0 0 0 rgba(var(--primary-500-rgb), 0.4)',
                            '0 0 0 8px rgba(var(--primary-500-rgb), 0)',
                          ],
                        }
                      : {}
                  }
                  transition={{ duration: 1.5, repeat: Infinity }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    background: isCompleted
                      ? 'var(--success)'
                      : isCurrent
                        ? 'var(--primary-500)'
                        : 'var(--bg-elevated)',
                    border: `2px solid ${
                      isCompleted
                        ? 'var(--success)'
                        : isCurrent
                          ? 'var(--primary-500)'
                          : 'var(--border-color)'
                    }`,
                    color: isCompleted || isCurrent ? '#fff' : 'var(--text-tertiary)',
                  }}
                >
                  {isCompleted ? (
                    <CheckCircleOutlined style={{ fontSize: 14 }} />
                  ) : (
                    <span style={{ fontSize: 12 }}>{IconComponent}</span>
                  )}
                </motion.div>

                <span
                  style={{
                    fontSize: 11,
                    color: isCompleted
                      ? 'var(--success)'
                      : isCurrent
                        ? 'var(--primary-500)'
                        : 'var(--text-tertiary)',
                    fontWeight: isCurrent ? 600 : 400,
                    textAlign: 'center',
                    lineHeight: 1.2,
                  }}
                >
                  {step}
                </span>
              </motion.div>
            );
          })}
        </div>

        <motion.div
          animate={{
            opacity: [0.3, 0.7, 0.3],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            marginTop: 4,
          }}
        >
          {[0, 1, 2, 3, 4].map((i) => (
            <motion.span
              key={i}
              animate={{
                scale: [1, 1.3, 1],
                opacity: [0.4, 1, 0.4],
              }}
              transition={{
                duration: 1,
                repeat: Infinity,
                delay: i * 0.1,
                ease: 'easeInOut',
              }}
              style={{
                width: 4,
                height: 4,
                borderRadius: '50%',
                background: 'var(--primary-500)',
              }}
            />
          ))}
        </motion.div>
      </div>
    );
  },
);

ThinkingIndicator.displayName = 'ThinkingIndicator';

export default ThinkingIndicator;
