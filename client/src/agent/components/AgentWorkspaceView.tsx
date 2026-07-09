import {
  CheckCircleOutlined,
  CloseOutlined,
  CloseCircleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SaveOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, Modal, Progress, Spin, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  readWorkspaceFile,
  writeWorkspaceFile,
  type AgentExecutionPlanNode,
  type AgentWorkspace,
  type AgentWorkspaceNextAction,
} from '../../services/api';
import styles from '../workbench/AgentWorkbench.module.css';

export type AgentWorkspaceTab = 'activity' | 'files' | 'diff' | 'plan' | 'terminal' | 'subagents' | 'artifacts';

function formatNodeDuration(startedAt?: string | null, completedAt?: string | null): string | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

interface AgentWorkspaceViewProps {
  tab: Exclude<AgentWorkspaceTab, 'activity' | 'terminal'>;
  workspace: AgentWorkspace | null;
  busyKey?: string;
  requestedFilePath?: string | null;
  onRecover: (node: AgentExecutionPlanNode) => void;
  onCancelSubagent: (taskId: string) => void;
  onRunNextAction: (action: AgentWorkspaceNextAction) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export default function AgentWorkspaceView({
  tab,
  workspace,
  busyKey,
  requestedFilePath,
  onRecover,
  onCancelSubagent,
  onRunNextAction,
  onDirtyChange,
}: AgentWorkspaceViewProps) {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [openFiles, setOpenFiles] = useState<string[]>([]);
  const [fileContent, setFileContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);
  const projectPath = workspace?.session.project_path;
  const isDirty = Boolean(selectedFile && fileContent !== savedContent);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  const saveFile = useCallback(async () => {
    if (!selectedFile || !projectPath || !isDirty || fileSaving) return;
    setFileSaving(true);
    try {
      await writeWorkspaceFile({
        file_path: selectedFile,
        content: fileContent,
        project_path: projectPath,
      });
      setSavedContent(fileContent);
      message.success('文件已保存');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文件保存失败');
    } finally {
      setFileSaving(false);
    }
  }, [fileContent, fileSaving, isDirty, projectPath, selectedFile]);

  const selectFile = useCallback((path: string) => {
    setOpenFiles((current) => current.includes(path) ? current : [...current, path].slice(-8));
    if (!isDirty || path === selectedFile) {
      setSelectedFile(path);
      return;
    }
    Modal.confirm({
      title: '放弃未保存的修改？',
      content: `切换到 ${path} 会丢失当前编辑内容。`,
      okText: '放弃并切换',
      okButtonProps: { danger: true },
      cancelText: '继续编辑',
      onOk: () => setSelectedFile(path),
    });
  }, [isDirty, selectedFile]);

  const closeFile = useCallback((path: string) => {
    const doClose = () => {
      setOpenFiles((current) => {
        const index = current.indexOf(path);
        const next = current.filter((item) => item !== path);
        if (selectedFile === path) {
          setSelectedFile(next[Math.min(index, Math.max(0, next.length - 1))] || null);
        }
        return next;
      });
    };
    if (path === selectedFile && isDirty) {
      Modal.confirm({
        title: '关闭未保存的文件？',
        content: `${path} 的修改尚未保存。`,
        okText: '放弃并关闭',
        okButtonProps: { danger: true },
        cancelText: '继续编辑',
        onOk: doClose,
      });
      return;
    }
    doClose();
  }, [isDirty, selectedFile]);

  useEffect(() => {
    if (requestedFilePath) selectFile(requestedFilePath);
  }, [requestedFilePath, selectFile]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    const saveShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && isDirty) {
        event.preventDefault();
        void saveFile();
      }
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    window.addEventListener('keydown', saveShortcut);
    return () => {
      window.removeEventListener('beforeunload', warnBeforeUnload);
      window.removeEventListener('keydown', saveShortcut);
    };
  }, [isDirty, saveFile]);

  useEffect(() => {
    if (!selectedFile || !projectPath) {
      setFileContent('');
      setSavedContent('');
      return;
    }
    let active = true;
    setFileLoading(true);
    readWorkspaceFile({ file_path: selectedFile, project_path: projectPath })
      .then((result) => {
        if (!active) return;
        setFileContent(result.content);
        setSavedContent(result.content);
      })
      .catch((error) => {
        if (active) message.error(error instanceof Error ? error.message : '文件读取失败');
      })
      .finally(() => {
        if (active) setFileLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectPath, selectedFile]);

  if (!workspace) {
    return <div className={styles.panelEmpty}><Empty description="暂无工作区数据" /></div>;
  }

  if (tab === 'files') {
    return (
      <section className={styles.workspacePanel} aria-label="变更文件">
        <div className={styles.panelHeader}>变更文件 <span>{workspace.changed_files.length}</span></div>
        {workspace.changed_files.length === 0 ? <Empty description="尚未修改文件" /> : (
          <div className={styles.fileWorkspace}>
            <div className={styles.denseList}>
              {workspace.changed_files.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  className={`${styles.fileRow} ${selectedFile === file.path ? styles.fileRowActive : ''}`}
                  onClick={() => selectFile(file.path)}
                >
                  <FileTextOutlined />
                  <span><strong>{file.path}</strong><small>{file.summary || file.status}</small></span>
                  <Tag>{file.status}</Tag>
                </button>
              ))}
            </div>
            <div className={styles.fileEditor}>
              {!selectedFile ? <Empty description="选择文件以预览和编辑" /> : fileLoading ? <Spin /> : (
                <>
                  <div className={styles.fileTabs} role="tablist" aria-label="已打开文件">
                    {openFiles.map((path) => (
                      <div
                        key={path}
                        className={path === selectedFile ? styles.fileTabActive : styles.fileTab}
                      >
                        <button
                          type="button"
                          role="tab"
                          aria-selected={path === selectedFile}
                          onClick={() => selectFile(path)}
                        >
                          {path.split(/[\\/]/).pop()}
                          {path === selectedFile && isDirty ? ' *' : ''}
                        </button>
                        <button
                          type="button"
                          aria-label={`关闭 ${path}`}
                          onClick={() => closeFile(path)}
                        >
                          <CloseOutlined />
                        </button>
                      </div>
                    ))}
                  </div>
                  <header>
                    <strong>{selectedFile}{isDirty ? ' · 未保存' : ''}</strong>
                    <div className={styles.fileEditorActions}>
                      <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        aria-label="还原文件"
                        disabled={!isDirty || fileSaving}
                        onClick={() => setFileContent(savedContent)}
                      />
                      <Button
                        size="small"
                        type="primary"
                        icon={<SaveOutlined />}
                        aria-label="保存文件"
                        disabled={!isDirty || fileSaving}
                        loading={fileSaving}
                        onClick={() => void saveFile()}
                      >
                        保存
                      </Button>
                    </div>
                  </header>
                  <Input.TextArea
                    value={fileContent}
                    onChange={(event) => setFileContent(event.target.value)}
                    aria-label="文件内容"
                    spellCheck={false}
                  />
                </>
              )}
            </div>
          </div>
        )}
      </section>
    );
  }

  if (tab === 'diff') {
    const fileChanges = workspace.artifacts.filter((artifact) => artifact.artifact_type === 'file_change');
    return (
      <section className={styles.workspacePanel} aria-label="文件差异">
        <div className={styles.panelHeader}>文件差异 <span>{fileChanges.length}</span></div>
        {fileChanges.length === 0 ? <Empty description="尚无可显示的文件差异" /> : (
          <div className={styles.diffList}>
            {fileChanges.map((artifact) => (
              <article key={artifact.id} className={styles.diffItem}>
                <header><strong>{artifact.title}</strong><Tag>{artifact.status}</Tag></header>
                <pre>{String(artifact.payload.preview || artifact.summary || '文件已变更')}</pre>
              </article>
            ))}
          </div>
        )}
      </section>
    );
  }

  if (tab === 'plan') {
    const nodes = workspace.execution_plan?.nodes || [];
    const completed = nodes.filter((node) => node.status === 'completed').length;
    const blocked = nodes.filter((node) => node.status === 'blocked' || node.status === 'failed').length;
    const progress = nodes.length ? Math.round((completed / nodes.length) * 100) : 0;
    return (
      <section className={styles.workspacePanel} aria-label="执行计划">
        <div className={styles.panelHeader}>执行计划 <span>{workspace.execution_plan?.status || '未规划'}</span></div>
        {nodes.length === 0 ? <Empty description="暂无执行计划" /> : (
          <>
            <div className={styles.planSummary}>
              <Progress
                percent={progress}
                size="small"
                status={blocked ? 'exception' : progress === 100 ? 'success' : 'active'}
              />
              <span>{completed} 已完成 · {nodes.length - completed - blocked} 进行中 · {blocked} 阻塞</span>
            </div>
            <div className={styles.planList}>
              {nodes.map((node, index) => (
              <div key={node.id} className={styles.planNode}>
                <span className={styles.planIndex}>{index + 1}</span>
                <div className={styles.planNodeBody}>
                  <div><strong>{node.title}</strong><Tag>{node.status}</Tag></div>
                  {node.description ? <p>{node.description}</p> : null}
                  <div className={styles.planMeta}>
                    {node.agent_id ? <span>Agent: {node.agent_id}</span> : null}
                    {node.depends_on?.length ? <span>依赖: {node.depends_on.join(', ')}</span> : null}
                    {formatNodeDuration(node.started_at, node.completed_at) ? (
                      <span>耗时: {formatNodeDuration(node.started_at, node.completed_at)}</span>
                    ) : null}
                    {node.recovery_attempts ? <span>恢复: {node.recovery_attempts} 次</span> : null}
                  </div>
                  {node.error || node.blocked_reason ? (
                    <p className={styles.errorText}>{node.error || node.blocked_reason}</p>
                  ) : null}
                </div>
                {node.recoverable ? (
                  <Button
                    size="small"
                    aria-label={`恢复 ${node.title}`}
                    loading={busyKey?.endsWith(`:${node.id}`)}
                    onClick={() => onRecover(node)}
                  >
                    恢复
                  </Button>
                ) : null}
              </div>
              ))}
            </div>
          </>
        )}
      </section>
    );
  }

  if (tab === 'subagents') {
    const tasks = workspace.async_tasks.tasks;
    return (
      <section className={styles.workspacePanel} aria-label="子 Agent">
        <div className={styles.panelHeader}>子 Agent <span>{tasks.length}</span></div>
        {tasks.length === 0 ? <Empty description="暂无子 Agent 任务" /> : (
          <div className={styles.denseList}>
            {tasks.map((task) => (
              <div key={task.task_id} className={styles.denseRow}>
                {task.status === 'completed' ? <CheckCircleOutlined /> : task.status === 'failed' ? <CloseCircleOutlined /> : <TeamOutlined />}
                <div>
                  <strong>{task.agent_name}</strong>
                  <span>{String(task.input?.description || task.error || task.status)}</span>
                </div>
                {['pending', 'running'].includes(task.status) ? (
                  <Button
                    size="small"
                    danger
                    aria-label={`取消 ${task.agent_name}`}
                    loading={busyKey?.endsWith(`:${task.task_id}`)}
                    onClick={() => onCancelSubagent(task.task_id)}
                  >
                    取消
                  </Button>
                ) : <Tag>{task.status}</Tag>}
              </div>
            ))}
          </div>
        )}
      </section>
    );
  }

  return (
    <section className={styles.workspacePanel} aria-label="Agent 产物">
      <div className={styles.panelHeader}>产物与下一步 <span>{workspace.artifacts.length}</span></div>
      {workspace.next_actions.length > 0 ? (
        <div className={styles.nextActions}>
          {workspace.next_actions.map((action) => (
            <Button
              key={action.id}
              size="small"
              type={action.priority === 'high' ? 'primary' : 'default'}
              onClick={() => onRunNextAction(action)}
            >
              {action.title}
            </Button>
          ))}
        </div>
      ) : null}
      {workspace.artifacts.length === 0 ? <Empty description="暂无产物" /> : (
        <div className={styles.artifactGrid}>
          {workspace.artifacts.map((artifact) => (
            <article key={artifact.id} className={styles.artifactItem}>
              <div><FileTextOutlined /><Tag>{artifact.artifact_type}</Tag></div>
              <strong>{artifact.title}</strong>
              <p>{artifact.summary}</p>
              {artifact.producer_agent ? <span>由 {artifact.producer_agent} 生成</span> : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
