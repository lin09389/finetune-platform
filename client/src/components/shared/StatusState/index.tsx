import {
  DisconnectOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Alert, Button } from 'antd';
import React, { memo } from 'react';
import styles from './StatusState.module.css';

export type StatusTone = 'error' | 'offline' | 'warning' | 'info';

export interface StatusStateProps {
  tone: StatusTone;
  title: string;
  description: React.ReactNode;
  action?: {
    text: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
  className?: string;
}

const statusConfig: Record<StatusTone, { type: 'error' | 'warning' | 'info'; icon: React.ReactNode }> = {
  error: { type: 'error', icon: <ExclamationCircleOutlined /> },
  offline: { type: 'warning', icon: <DisconnectOutlined /> },
  warning: { type: 'warning', icon: <ExclamationCircleOutlined /> },
  info: { type: 'info', icon: <InfoCircleOutlined /> },
};

const StatusState: React.FC<StatusStateProps> = memo(({ tone, title, description, action, className }) => {
  const config = statusConfig[tone];

  return (
    <Alert
      className={`${styles.statusState}${className ? ` ${className}` : ''}`}
      type={config.type}
      showIcon
      icon={config.icon}
      message={title}
      description={description}
      action={
        action ? (
          <Button size="small" type="primary" icon={action.icon || <ReloadOutlined aria-hidden />} onClick={action.onClick}>
            {action.text}
          </Button>
        ) : undefined
      }
    />
  );
});

StatusState.displayName = 'StatusState';

export default StatusState;
