import React, { memo } from 'react'
import { Tag } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  SyncOutlined,
  PauseCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'

export type StatusType =
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'processing'
  | 'pending'
  | 'stopped'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'running'
  | 'cancelled'

export interface StatusBadgeProps {
  status: StatusType
  text?: string
  size?: 'small' | 'default'
  showIcon?: boolean
  className?: string
  style?: React.CSSProperties
}

const statusConfig: Record<
  StatusType,
  {
    icon: React.ReactNode
    label: string
    color: string
    bgColor: string
    borderColor: string
  }
> = {
  success: {
    icon: <CheckCircleOutlined />,
    label: '成功',
    color: 'var(--success)',
    bgColor: 'var(--success-light)',
    borderColor: 'var(--success)',
  },
  completed: {
    icon: <CheckCircleOutlined />,
    label: '已完成',
    color: 'var(--success)',
    bgColor: 'var(--success-light)',
    borderColor: 'var(--success)',
  },
  error: {
    icon: <CloseCircleOutlined />,
    label: '错误',
    color: 'var(--error)',
    bgColor: 'var(--error-light)',
    borderColor: 'var(--error)',
  },
  failed: {
    icon: <CloseCircleOutlined />,
    label: '失败',
    color: 'var(--error)',
    bgColor: 'var(--error-light)',
    borderColor: 'var(--error)',
  },
  warning: {
    icon: <ExclamationCircleOutlined />,
    label: '警告',
    color: 'var(--warning)',
    bgColor: 'var(--warning-light)',
    borderColor: 'var(--warning)',
  },
  info: {
    icon: <ClockCircleOutlined />,
    label: '信息',
    color: 'var(--info)',
    bgColor: 'var(--info-light)',
    borderColor: 'var(--info)',
  },
  processing: {
    icon: <SyncOutlined spin />,
    label: '处理中',
    color: 'var(--accent-primary)',
    bgColor: 'var(--primary-100)',
    borderColor: 'var(--accent-primary)',
  },
  running: {
    icon: <LoadingOutlined />,
    label: '运行中',
    color: 'var(--accent-primary)',
    bgColor: 'var(--primary-100)',
    borderColor: 'var(--accent-primary)',
  },
  pending: {
    icon: <ClockCircleOutlined />,
    label: '等待中',
    color: 'var(--text-secondary)',
    bgColor: 'var(--bg-elevated)',
    borderColor: 'var(--border-color)',
  },
  stopped: {
    icon: <StopOutlined />,
    label: '已停止',
    color: 'var(--warning)',
    bgColor: 'var(--warning-light)',
    borderColor: 'var(--warning)',
  },
  paused: {
    icon: <PauseCircleOutlined />,
    label: '已暂停',
    color: 'var(--warning)',
    bgColor: 'var(--warning-light)',
    borderColor: 'var(--warning)',
  },
  cancelled: {
    icon: <CloseCircleOutlined />,
    label: '已取消',
    color: 'var(--text-tertiary)',
    bgColor: 'var(--bg-elevated)',
    borderColor: 'var(--border-color)',
  },
}

const StatusBadge: React.FC<StatusBadgeProps> = memo(
  ({ status, text, size = 'default', showIcon = true, className, style }) => {
    const config = statusConfig[status] || statusConfig.info
    const displayText = text || config.label

    return (
      <Tag
        icon={showIcon ? config.icon : undefined}
        className={className}
        style={{
          borderRadius: 'var(--radius-sm)',
          fontWeight: 500,
          background: config.bgColor,
          borderColor: config.borderColor,
          color: config.color,
          fontSize: size === 'small' ? 'var(--text-xs)' : 'var(--text-sm)',
          padding: size === 'small' ? '0 6px' : '2px 8px',
          lineHeight: size === 'small' ? '18px' : '20px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          ...style,
        }}
      >
        {displayText}
      </Tag>
    )
  }
)

StatusBadge.displayName = 'StatusBadge'

export default StatusBadge

export function getStatusBadge(status: string, text?: string): React.ReactNode {
  const normalizedStatus = status.toLowerCase() as StatusType
  return <StatusBadge status={normalizedStatus} text={text} />
}

export const TrainingStatusBadge: React.FC<{
  status: 'completed' | 'failed' | 'stopped' | 'running' | 'pending'
  text?: string
}> = memo(({ status, text }) => {
  const statusMap: Record<string, StatusType> = {
    completed: 'completed',
    failed: 'failed',
    stopped: 'stopped',
    running: 'running',
    pending: 'pending',
  }
  return <StatusBadge status={statusMap[status] || 'info'} text={text} />
})

TrainingStatusBadge.displayName = 'TrainingStatusBadge'

export const ConnectionStatusBadge: React.FC<{
  status: 'connected' | 'disconnected' | 'connecting'
}> = memo(({ status }) => {
  const statusMap: Record<string, StatusType> = {
    connected: 'success',
    disconnected: 'error',
    connecting: 'processing',
  }
  const labelMap: Record<string, string> = {
    connected: '已连接',
    disconnected: '未连接',
    connecting: '连接中',
  }
  return <StatusBadge status={statusMap[status] || 'info'} text={labelMap[status]} />
})

ConnectionStatusBadge.displayName = 'ConnectionStatusBadge'
