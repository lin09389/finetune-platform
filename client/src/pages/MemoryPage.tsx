/**
 * 记忆管理页面
 */
import { BulbOutlined, PlusOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useState } from 'react';

import MemoryManager from '../components/MemoryManager';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import styles from './MemoryPage.module.css';

const tiers = [
  {
    icon: '⚡',
    name: '工作记忆',
    desc: '当前对话上下文，实时感知用户意图，会话结束后自动清除。',
  },
  {
    icon: '🧠',
    name: '短期记忆',
    desc: '近期交互摘要，跨会话保留重要信息，定期压缩归档。',
  },
  {
    icon: '🗄️',
    name: '长期记忆',
    desc: '语义化知识图谱，持久存储核心知识；对外集成能力仍在持续收口。',
  },
];

export default function MemoryPage() {
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false);

  return (
    <MotionList className={styles.container} stagger={0.1}>
      <MotionItem>
        {/* 标题栏 */}
        <div className={styles.headerCard}>
          <div className={styles.headerIcon}>
            <BulbOutlined />
          </div>
          <div>
            <h2 className={styles.headerTitle}>智能记忆系统</h2>
            <p className={styles.headerSubtitle}>
              Beta 能力：三级记忆架构已可试用，但跨能力集成和外部接入仍在持续收口
            </p>
          </div>
        </div>

        {/* 三层记忆架构说明 */}
        <div className={styles.tiersCard}>
          <div className={styles.sectionTitle}>记忆层级</div>
          <div className={styles.tiersGrid}>
            {tiers.map((tier) => (
              <div key={tier.name} className={styles.tierItem}>
                <div className={styles.tierIcon}>{tier.icon}</div>
                <div className={styles.tierName}>{tier.name}</div>
                <div className={styles.tierDesc}>{tier.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 操作入口 */}
        <div className={styles.actionCard}>
          <div className={styles.actionInfo}>
            <div className={styles.actionTitle}>记忆管理</div>
            <div className={styles.actionDesc}>
              查看、编辑、删除各层记忆条目，管理知识图谱节点与关联关系
            </div>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setMemoryManagerOpen(true)}>
            打开记忆管理
          </Button>
        </div>

        <MemoryManager open={memoryManagerOpen} onClose={() => setMemoryManagerOpen(false)} />
      </MotionItem>
    </MotionList>
  );
}
