import { CheckCircleOutlined, DownOutlined, RightOutlined } from '@ant-design/icons';
import { useState } from 'react';
import type { CodingDiffReviewPayload } from '../protocol/agentProtocol';
import type { CodingDiffReviewGroup } from '../selectors/workbenchSelectors';
import styles from './AgentDiffReviewCard.module.css';

function changeKindLabel(kind: CodingDiffReviewPayload['changeKind']): string {
  return { added: '新增', modified: '修改', deleted: '删除' }[kind];
}

function isLongDiff(diff: string | undefined): boolean {
  return Boolean(diff && (diff.length > 1200 || diff.split('\n').length > 20));
}

export default function AgentDiffReviewCard({ group }: { group: CodingDiffReviewGroup }) {
  const entries = group.entries;
  const latest = entries[entries.length - 1]!;
  const { payload } = latest;
  const [expanded, setExpanded] = useState(!isLongDiff(payload.unifiedDiff));
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const detailsId = `coding-diff-${latest.item.id}`;
  const diff = payload.unifiedDiff || '';

  return (
    <section className={styles.card} aria-label={`Diff 审阅：${group.path}`}>
      <button
        type="button"
        className={styles.header}
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={`${expanded ? '收起' : '展开'} ${group.path} 的 Diff 审阅`}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? <DownOutlined /> : <RightOutlined />}
        <span className={styles.path} title={group.path}>
          {group.path}
        </span>
        <span className={styles.stats}>
          <span className={styles.additions}>+{payload.additions}</span>
          <span className={styles.deletions}>-{payload.deletions}</span>
        </span>
      </button>
      {expanded ? (
        <div className={styles.details} id={detailsId}>
          <div className={styles.notices}>
            <span className={styles.status} data-kind={payload.changeKind}>
              <CheckCircleOutlined /> {changeKindLabel(payload.changeKind)} · 审阅材料已就绪
            </span>
            {payload.binary ? (
              <span className={styles.notice}>二进制文件：不提供内联 Diff。</span>
            ) : null}
            {payload.truncated ? (
              <span className={styles.notice}>Diff 已按服务端上限截断，仅显示可审阅的片段。</span>
            ) : null}
          </div>
          {!payload.binary && diff ? <pre className={styles.diff}>{diff}</pre> : null}
          {!payload.binary && !diff ? (
            <span className={styles.notice}>此记录没有可内联展示的 Diff。</span>
          ) : null}
          {entries.length > 1 ? (
            <>
              <button
                type="button"
                className={styles.historyToggle}
                aria-expanded={historyExpanded}
                onClick={() => setHistoryExpanded((current) => !current)}
              >
                {historyExpanded ? '收起' : '查看'}此前 {entries.length - 1} 次写入
              </button>
              {historyExpanded ? (
                <div className={styles.history} aria-label={`${group.path} 的写入历史`}>
                  {entries
                    .slice(0, -1)
                    .reverse()
                    .map(({ item, payload: entry }) => (
                      <div className={styles.historyItem} key={item.id}>
                        <span>
                          {changeKindLabel(entry.changeKind)}{' '}
                          <span className={styles.additions}>+{entry.additions}</span>{' '}
                          <span className={styles.deletions}>-{entry.deletions}</span>
                        </span>
                        <span className={styles.sequence}>写入 #{entry.writeSequence}</span>
                      </div>
                    ))}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
