import { ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Progress, Skeleton } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  getAgentEvalOverview,
  type AgentEvalMode,
  type AgentEvalOverview,
} from '../../services/agentEvalApi';
import styles from './AgentCapabilityScorecard.module.css';

const MODE_LABELS: Record<AgentEvalMode, string> = {
  coding: 'Coding',
  training: '训练',
  hybrid: '混合',
};

function percent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}

export default function AgentCapabilityScorecard() {
  const [overview, setOverview] = useState<AgentEvalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getAgentEvalOverview());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '暂时无法读取能力基线');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const report = overview?.latest_report;
  const score = report ? percent(report.summary.weighted_score) : null;
  const coverage = report ? percent(report.summary.coverage) : null;

  return (
    <section className={styles.section} aria-labelledby="agent-capability-scorecard-title">
      <header className={styles.header}>
        <ExperimentOutlined />
        <div className={styles.headingCopy}>
          <div className={styles.titleLine}>
            <h3 id="agent-capability-scorecard-title">Agent 能力基线</h3>
            <span className={styles.version}>Eval v1</span>
          </div>
          <p>本地、版本化的 Coding 与训练协作能力评测</p>
        </div>
        <Button
          type="text"
          size="small"
          icon={<ReloadOutlined />}
          loading={loading && overview !== null}
          aria-label="刷新 Agent 能力基线"
          onClick={() => void load()}
        />
      </header>

      {loading && !overview ? <Skeleton active paragraph={{ rows: 2 }} title={false} /> : null}

      {overview ? (
        <>
          <div className={styles.metrics}>
            <div className={styles.scoreBlock}>
              <Progress
                type="circle"
                size={60}
                percent={score ?? 0}
                format={() => (score === null ? '—' : score)}
                strokeColor="var(--accent-primary)"
                trailColor="var(--border-color)"
              />
              <div>
                <strong>{score === null ? '等待首次评测' : '综合能力分'}</strong>
                <span>
                  {score === null
                    ? '真实模型评测默认不会自动运行'
                    : `${report?.summary.eligible_total ?? 0} 个有效场景 · ${coverage}% 覆盖`}
                </span>
              </div>
            </div>
            <div className={styles.catalogMeta}>
              <span>基线场景</span>
              <strong>{overview.catalog.scenario_count}</strong>
            </div>
          </div>

          <div className={styles.modeGrid}>
            {(Object.keys(MODE_LABELS) as AgentEvalMode[]).map((mode) => (
              <div key={mode}>
                <span>{MODE_LABELS[mode]}</span>
                <strong>{overview.catalog.by_mode[mode] ?? 0}</strong>
              </div>
            ))}
          </div>

          <div className={styles.safetyNote}>
            <span className={overview.live_model.enabled ? styles.enabledDot : styles.disabledDot} />
            {overview.live_model.enabled
              ? '真实模型入口已启用，仍需逐次明确确认'
              : '真实模型入口关闭；当前仅展示本地安全基线'}
          </div>
        </>
      ) : null}

      {error ? <div className={styles.error} role="alert">{error}</div> : null}
    </section>
  );
}
