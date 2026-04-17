import React from 'react';
import styles from './PageSkeleton.module.css';

interface PageSkeletonProps {
  cards?: number;
  rows?: number;
}

const PageSkeleton: React.FC<PageSkeletonProps> = ({ cards = 4, rows = 4 }) => {
  return (
    <div className={styles.pageSkeleton} role="status" aria-label="页面加载中">
      <div className={styles.header}>
        <div className={styles.orb} />
        <div className={styles.titleBlock}>
          <div className={`${styles.bar} ${styles.title}`} />
          <div className={`${styles.bar} ${styles.subtitle}`} />
        </div>
      </div>

      <div className={styles.grid}>
        {Array.from({ length: cards }).map((_, idx) => (
          <div key={`card-${idx}`} className={styles.card} style={{ gridColumn: 'span 3' }}>
            <div className={styles.metricTop}>
              <div className={`${styles.bar}`} style={{ width: '42%', height: 10 }} />
              <div className={styles.metricDot} />
            </div>
            <div className={`${styles.bar}`} style={{ width: '56%', height: 18 }} />
            <div className={`${styles.bar}`} style={{ width: '100%', height: 4 }} />
          </div>
        ))}
      </div>

      <div className={styles.table}>
        <div className={`${styles.tableRow} ${styles.tableRowHead}`}>
          <div className={styles.bar} style={{ width: '40%', height: 10 }} />
          <div className={styles.bar} style={{ width: '34%', height: 10 }} />
          <div className={styles.bar} style={{ width: '36%', height: 10 }} />
          <div className={styles.bar} style={{ width: '32%', height: 10 }} />
        </div>
        {Array.from({ length: rows }).map((_, idx) => (
          <div key={`row-${idx}`} className={styles.tableRow}>
            <div className={styles.bar} style={{ width: `${68 - idx * 4}%`, height: 10 }} />
            <div className={styles.bar} style={{ width: `${52 - idx * 3}%`, height: 10 }} />
            <div className={styles.bar} style={{ width: `${46 - idx * 2}%`, height: 10 }} />
            <div className={styles.bar} style={{ width: `${38 - idx}%`, height: 10 }} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default PageSkeleton;
