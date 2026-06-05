import { Button, Empty, Select, Space, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';
import type { AgentWorkspaceArtifact } from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

interface AgentArtifactLedgerProps {
  artifacts: AgentWorkspaceArtifact[];
  onSelectArtifact?: (artifactId: string) => void;
  onOpenFile?: (path: string) => void | Promise<void>;
}

const typeLabel: Record<string, string> = {
  summary: '摘要',
  run_summary: '摘要',
  finding: '发现',
  findings: '发现',
  risk: '风险',
  risks: '风险',
  decision: '决策',
  question: '问题',
  research_note: '研究',
  file_change: '文件',
  command_result: '命令',
  test_result: '验证',
  subtask_result: '子任务',
};

export default function AgentArtifactLedger({
  artifacts,
  onSelectArtifact,
  onOpenFile,
}: AgentArtifactLedgerProps) {
  const [typeFilter, setTypeFilter] = useState('all');
  const options = useMemo(() => {
    const types = Array.from(new Set(artifacts.map((artifact) => artifact.type || artifact.artifact_type))).sort();
    return [
      { value: 'all', label: '全部产物' },
      ...types.map((type) => ({ value: type, label: typeLabel[type] || type })),
    ];
  }, [artifacts]);
  const filtered = typeFilter === 'all'
    ? artifacts
    : artifacts.filter((artifact) => (artifact.type || artifact.artifact_type) === typeFilter);

  if (!artifacts.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Agent 产物" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Artifact Ledger</Typography.Text>
          <Typography.Text type="secondary">Agent 运行过程中沉淀的通用产物</Typography.Text>
        </div>
        <Select size="small" value={typeFilter} options={options} onChange={setTypeFilter} />
      </div>
      <div className={styles.artifactList}>
        {filtered.map((artifact) => {
          const artifactType = artifact.type || artifact.artifact_type;
          const path = String(artifact.payload?.path || '');
          return (
            <div key={artifact.id} className={styles.artifactItem}>
              <div className={styles.artifactBody}>
                <Space size={6} wrap>
                  <Typography.Text strong>{artifact.title}</Typography.Text>
                  <Tag>{typeLabel[artifactType] || artifactType}</Tag>
                  {artifact.status ? <Tag color={artifact.status === 'failed' ? 'error' : 'default'}>{artifact.status}</Tag> : null}
                </Space>
                {artifact.summary ? <Typography.Text type="secondary">{artifact.summary}</Typography.Text> : null}
                <div className={styles.metaRow}>
                  {artifact.source?.kind ? <span>{artifact.source.kind}</span> : null}
                  {artifact.source_part_id ? <span>part {artifact.source_part_id}</span> : null}
                  {artifact.source_task_id ? <span>task {artifact.source_task_id}</span> : null}
                  {artifact.producer_agent ? <span>{artifact.producer_agent}</span> : null}
                </div>
              </div>
              <Space size={6}>
                {path ? <Button size="small" onClick={() => void onOpenFile?.(path)}>打开文件</Button> : null}
                <Button size="small" onClick={() => onSelectArtifact?.(artifact.id)}>详情</Button>
              </Space>
            </div>
          );
        })}
      </div>
    </div>
  );
}
