import { Button, Empty, Spin, Tag, Typography } from 'antd';
import { useState } from 'react';
import { extractApiErrorMessage, readAgentMemoryFile, type AgentMemoryFile } from '../../services/api';
import type { AgentWorkspaceRuntimeContext } from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

interface AgentRuntimePanelProps {
  runtime?: AgentWorkspaceRuntimeContext | null;
  sessionId?: string | null;
}

export default function AgentRuntimePanel({ runtime, sessionId }: AgentRuntimePanelProps) {
  const [selectedMemoryFile, setSelectedMemoryFile] = useState<AgentMemoryFile | null>(null);
  const [loadingMemoryPath, setLoadingMemoryPath] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState('');

  if (!runtime) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行时上下文" />;
  }
  const policy = runtime.policy;
  const resourceProfile = runtime.resource_profile || policy?.resource_profile;
  const executionPlan = runtime.execution_plan || policy?.execution_plan;

  const openMemoryFile = async (path: string) => {
    if (!sessionId) return;
    setLoadingMemoryPath(path);
    setMemoryError('');
    try {
      const file = await readAgentMemoryFile(sessionId, path);
      setSelectedMemoryFile(file);
    } catch (error: any) {
      setMemoryError(extractApiErrorMessage(error, '读取 memory 文件失败'));
    } finally {
      setLoadingMemoryPath(null);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Runtime Policy</Typography.Text>
          <Typography.Text type="secondary">{policy?.schema_version || 'legacy runtime context'}</Typography.Text>
        </div>
        <div className={styles.tagRow}>
          <Tag color={policy?.readonly ? 'default' : 'processing'}>{policy?.readonly ? '只读' : '可写'}</Tag>
          <Tag>{executionPlan?.backend_mode || 'workspace'}</Tag>
        </div>
      </div>

      <section className={styles.section}>
        <Typography.Text strong>Execution Plan</Typography.Text>
        <div className={styles.compactList}>
          <div className={styles.compactItem}>
            <span>Workspace</span>
            <Typography.Text code>{policy?.workspace_root || runtime.workspace_root || '未绑定'}</Typography.Text>
          </div>
          <div className={styles.compactItem}>
            <span>Agent</span>
            <Typography.Text code>{resourceProfile?.agent?.id || policy?.agent_id || 'unknown'}</Typography.Text>
            <div className={styles.tagRow}>
              <Tag>{resourceProfile?.agent?.mode || policy?.mode || 'all'}</Tag>
              <Tag>{policy?.filesystem_profile || 'unknown'}</Tag>
            </div>
          </div>
          <div className={styles.compactItem}>
            <span>Resources</span>
            <Typography.Text code>{resourceProfile?.schema_version || 'legacy'}</Typography.Text>
            <div className={styles.tagRow}>
              <Tag>{resourceProfile?.memory?.namespaces?.length ?? 0} memory</Tag>
              <Tag>{resourceProfile?.skills?.sources?.length ?? runtime.skill_sources.length} skills</Tag>
              <Tag>{resourceProfile?.mounts?.length ?? runtime.vfs_mounts.length} mounts</Tag>
            </div>
          </div>
          <div className={styles.compactItem}>
            <span>Runtime</span>
            <Typography.Text code>{executionPlan?.runtime || 'deepagents'}</Typography.Text>
            <div className={styles.tagRow}>
              <Tag>limit {executionPlan?.recursion_limit ?? 'auto'}</Tag>
              <Tag color={executionPlan?.checkpointer === false ? 'default' : 'processing'}>
                {executionPlan?.checkpointer === false ? 'no checkpoint' : 'checkpoint'}
              </Tag>
            </div>
          </div>
          <div className={styles.compactItem}>
            <span>Output</span>
            <Typography.Text code>{policy?.output_contract?.format || 'plain_text'}</Typography.Text>
            <div className={styles.tagRow}>
              <Tag color={policy?.output_contract?.enforced_in_prompt ? 'processing' : 'default'}>
                {policy?.output_contract?.enforced_in_prompt ? 'prompt enforced' : 'default'}
              </Tag>
            </div>
          </div>
          <div className={styles.compactItem}>
            <span>Recovery</span>
            <Typography.Text code>{policy?.recovery_policy?.failure_status || 'failed'}</Typography.Text>
            <div className={styles.tagRow}>
              <Tag color={policy?.recovery_policy?.resume_after_permission ? 'processing' : 'default'}>
                {policy?.recovery_policy?.resume_after_permission ? 'resume' : 'no resume'}
              </Tag>
              <Tag color={policy?.recovery_policy?.restart_recovery ? 'processing' : 'default'}>
                {policy?.recovery_policy?.restart_recovery ? 'restart recovery' : 'no restart recovery'}
              </Tag>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <Typography.Text strong>VFS Mounts</Typography.Text>
        <div className={styles.mountList}>
          {runtime.vfs_mounts.map((mount) => (
            <div key={`${mount.kind}:${mount.path}`} className={styles.mountItem}>
              <div>
                <Typography.Text code>{mount.path}</Typography.Text>
                <Typography.Text type="secondary">{mount.description}</Typography.Text>
              </div>
              <div className={styles.tagRow}>
                <Tag>{mount.kind}</Tag>
                <Tag color={mount.writable ? 'processing' : 'default'}>{mount.writable ? '可写' : '只读'}</Tag>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <Typography.Text strong>Skills</Typography.Text>
        {runtime.skill_sources.length ? (
          <div className={styles.compactList}>
            {runtime.skill_sources.map((source) => (
              <div key={source.virtual_path} className={styles.compactItem}>
                <span>{source.name}</span>
                <Typography.Text code>{source.virtual_path}</Typography.Text>
                <div className={styles.tagRow}>
                  <Tag color={source.available ? 'success' : 'default'}>{source.available ? '可用' : '未挂载'}</Tag>
                  <Tag color={source.enabled === false ? 'default' : 'processing'}>{source.enabled === false ? '未启用' : '已启用'}</Tag>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Skill source" />
        )}
      </section>

      <section className={styles.section}>
        <Typography.Text strong>Memory Files</Typography.Text>
        {runtime.memory_files.length ? (
          <div className={styles.compactList}>
            {runtime.memory_files.map((path) => (
              <div key={path} className={styles.compactItem}>
                <Typography.Text code>{path}</Typography.Text>
                <Button
                  size="small"
                  disabled={!sessionId}
                  loading={loadingMemoryPath === path}
                  onClick={() => void openMemoryFile(path)}
                >
                  查看
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 memory 文件" />
        )}
        {loadingMemoryPath ? <Spin size="small" /> : null}
        {memoryError ? <Typography.Text type="danger">{memoryError}</Typography.Text> : null}
        {selectedMemoryFile ? (
          <div className={styles.memoryPreview}>
            <div className={styles.panelHeader}>
              <div>
                <Typography.Text strong>{selectedMemoryFile.path}</Typography.Text>
                <Typography.Text type="secondary">version {selectedMemoryFile.version}</Typography.Text>
              </div>
              <Tag color={selectedMemoryFile.writable ? 'processing' : 'default'}>{selectedMemoryFile.writable ? '可写' : '只读'}</Tag>
            </div>
            <pre>{selectedMemoryFile.content || '(empty)'}</pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}
