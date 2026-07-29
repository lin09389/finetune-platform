import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  FolderOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { motion } from 'framer-motion';
import { memo, useMemo } from 'react';
import { useMotionConfig } from '../../components/motion';
import EmptyState from '../../components/shared/EmptyState';
import GlassCard from '../../components/shared/GlassCard';
import { staggerItem } from '../../theme/motion-tokens';
import type { Checkpoint, DatasetInfo, ModelInfo, TrainingRecord } from '../../types';
import styles from '../Dashboard.module.css';

interface TrainingHistoryTableProps {
  recentTrainings: TrainingRecord[];
  models: ModelInfo[];
  datasets: DatasetInfo[];
  latestCheckpoints: Record<string, Checkpoint>;
  onGoHistory: () => void;
  onGoTraining: () => void;
}

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'completed':
      return (
        <Tag
          icon={<CheckCircleOutlined />}
          style={{
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            background: 'var(--success-light)',
            borderColor: 'var(--success-border)',
            color: 'var(--success)',
            padding: '2px 8px',
          }}
        >
          完成
        </Tag>
      );
    case 'failed':
      return (
        <Tag
          icon={<CloseCircleOutlined />}
          style={{
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            background: 'var(--error-light)',
            borderColor: 'var(--error-border)',
            color: 'var(--error)',
            padding: '2px 8px',
          }}
        >
          失败
        </Tag>
      );
    case 'stopped':
      return (
        <Tag
          icon={<ExclamationCircleOutlined />}
          style={{
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            background: 'var(--warning-light)',
            borderColor: 'var(--warning-border)',
            color: 'var(--warning)',
            padding: '2px 8px',
          }}
        >
          停止
        </Tag>
      );
    default:
      return (
        <Tag
          icon={<ClockCircleOutlined spin />}
          style={{
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            background: 'var(--info-light)',
            borderColor: 'var(--info-border)',
            color: 'var(--info)',
            padding: '2px 8px',
          }}
        >
          训练中
        </Tag>
      );
  }
};

/** 最近训练记录表格（columns 已 memo 化，避免每次父级渲染重建） */
function TrainingHistoryTable({
  recentTrainings,
  models,
  datasets,
  latestCheckpoints,
  onGoHistory,
  onGoTraining,
}: TrainingHistoryTableProps) {
  const { getSafeVariants } = useMotionConfig();

  const trainingColumns = useMemo<ColumnsType<TrainingRecord>>(() => [
    {
      title: '模型',
      key: 'model',
      render: (_: unknown, record: TrainingRecord) => {
        const id = record.baseModelId || record.config?.modelId || record.modelName;
        const model = models.find((m) => m.id === id);
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <FolderOutlined style={{ color: 'var(--accent-primary)', fontSize: 'var(--text-base)' }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {model?.name || id}
            </span>
          </div>
        );
      },
    },
    {
      title: '数据集',
      key: 'dataset',
      render: (_: unknown, record: TrainingRecord) => {
        const id = record.datasetId || record.config?.datasetId || record.datasetName;
        const dataset = datasets.find((d) => d.id === id);
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <DatabaseOutlined style={{ color: 'var(--accent-secondary)', fontSize: 'var(--text-base)' }} />
            <span style={{ color: 'var(--text-secondary)' }}>{dataset?.name || id}</span>
          </div>
        );
      },
    },
    {
      title: '方法',
      key: 'method',
      render: (_: unknown, record: TrainingRecord) => {
        const method = record.method || record.config?.method || 'qlora';
        return (
          <Tag
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: method === 'qlora' ? 'var(--success-light)' : 'var(--info-light)',
              borderColor: method === 'qlora' ? 'var(--success)' : 'var(--info)',
              color: method === 'qlora' ? 'var(--success)' : 'var(--info)',
              padding: '2px 8px',
            }}
          >
            {method.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusBadge(status),
    },
    {
      title: '时间',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (date: string) => (
        <span
          style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', fontWeight: 500 }}
        >
          {new Date(date).toLocaleString('zh-CN')}
        </span>
      ),
    },
    {
      title: '最新检查点',
      key: 'checkpoint',
      render: (_: unknown, record: TrainingRecord) => {
        const cp = latestCheckpoints[record.id];
        if (!cp) return <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>-</span>;
        return (
          <div>
            <Tag
              style={{
                borderRadius: 'var(--radius-sm)',
                fontWeight: 600,
                background: 'var(--accent-primary-light)',
                borderColor: 'var(--accent-primary)',
                color: 'var(--accent-primary)',
              }}
            >
              step {cp.step}
            </Tag>
            {cp.metadata?.loss !== undefined && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: 'var(--space-0-5)' }}>
                loss {cp.metadata.loss.toFixed(4)}
              </div>
            )}
          </div>
        );
      },
    },
  ], [models, datasets, latestCheckpoints]);

  return (
    <motion.div variants={getSafeVariants(staggerItem)}>
      <GlassCard className={styles.historyCard} intensity="medium" noHover>
        <div className={styles.historyHeader}>
          <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
            <ClockCircleOutlined style={{ color: 'var(--accent-primary)' }} />
            最近训练
          </span>
          <Button
            type="text"
            icon={<ArrowRightOutlined />}
            onClick={onGoHistory}
            style={{ fontWeight: 600, color: 'var(--accent-primary)' }}
          >
            查看全部
          </Button>
        </div>

        <div className={styles.tableWrapper} style={{ marginTop: 'var(--space-6)' }}>
          {recentTrainings.length === 0 ? (
            <EmptyState
              compact
              title="暂无训练记录"
              description="创建一次训练后，结果会显示在这里。"
              action={{
                text: '开始训练',
                onClick: onGoTraining,
                icon: <PlusOutlined />,
              }}
              style={{ padding: 'var(--space-8) 0' }}
            />
          ) : (
            <Table
              columns={trainingColumns}
              dataSource={recentTrainings}
              rowKey="id"
              pagination={false}
              size="middle"
            />
          )}
        </div>
      </GlassCard>
    </motion.div>
  );
}

export default memo(TrainingHistoryTable);
