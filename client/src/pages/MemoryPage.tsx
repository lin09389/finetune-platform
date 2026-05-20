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
    icon: '🗄️',
    name: '长期记忆',
    desc: '保存用户偏好、项目事实和长期设定，可被聊天上下文按需检索。',
  },
  {
    icon: '🔎',
    name: '上下文检索',
    desc: '记忆只提供候选结果，最终上下文由统一 context builder 拼装。',
  },
  {
    icon: '🧹',
    name: '可治理数据',
    desc: '支持查看、搜索、编辑、删除和导入导出，避免记忆系统继续膨胀。',
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
              长期用户记忆已收口为独立数据源，RAG、项目上下文和聊天拼装由 context 层统一负责
            </p>
          </div>
        </div>

        {/* 记忆边界说明 */}
        <div className={styles.tiersCard}>
          <div className={styles.sectionTitle}>当前边界</div>
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
              查看、搜索、创建、编辑、删除长期记忆条目
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
