import { Empty, Tag, Typography } from 'antd';
import type { AgentWorkspaceRuntimeContext } from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

interface AgentRuntimePanelProps {
  runtime?: AgentWorkspaceRuntimeContext | null;
}

export default function AgentRuntimePanel({ runtime }: AgentRuntimePanelProps) {
  if (!runtime) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行时上下文" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Runtime Context</Typography.Text>
          <Typography.Text type="secondary">{runtime.workspace_root || '未绑定工作区'}</Typography.Text>
        </div>
      </div>

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
                <Tag color={source.available ? 'success' : 'default'}>{source.available ? '可用' : '未挂载'}</Tag>
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
              <Typography.Text key={path} code>{path}</Typography.Text>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 memory 文件" />
        )}
      </section>
    </div>
  );
}
