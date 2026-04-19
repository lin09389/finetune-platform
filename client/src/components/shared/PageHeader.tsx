import { QuestionCircleOutlined } from '@ant-design/icons';
import { Space, Tag, Tooltip } from 'antd';
import React from 'react';
import glassStyles from './GlassCard.module.css';
import styles from './PageHeader.module.css';

export interface PageHeaderProps {
  title: React.ReactNode;
  icon?: React.ReactNode;
  status?: {
    text: string;
    color?: string;
  };
  primaryAction?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  extraActions?: React.ReactNode;
  helpTooltip?: string;
  className?: string;
  style?: React.CSSProperties;
}

export default function PageHeader({
  title,
  icon,
  status,
  primaryAction,
  secondaryAction,
  extraActions,
  helpTooltip,
  className = '',
  style,
}: PageHeaderProps) {
  return (
    <div className={`${glassStyles.glassCard} ${styles.headerCard} ${className}`} style={style}>
      <div className={styles.left}>
        <h1 className={styles.title}>
          {icon}
          {title}
        </h1>
        {status && (
          <Tag color={status.color || 'blue'} className={styles.status}>
            {status.text}
          </Tag>
        )}
        {helpTooltip && (
          <Tooltip title={helpTooltip}>
            <div className={styles.helpIcon}>
              <QuestionCircleOutlined />
            </div>
          </Tooltip>
        )}
      </div>
      <div className={styles.right}>
        <Space>
          {extraActions}
          {secondaryAction}
          {primaryAction}
        </Space>
      </div>
    </div>
  );
}
