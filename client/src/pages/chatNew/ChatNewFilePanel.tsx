import { Tag } from 'antd';
import type { KeyboardEvent, ReactNode } from 'react';

import type { WorkspaceTreeNode } from '../../services/api';
import { getFileIcon, isTextIcon } from '../../utils/fileIcons';
import styles from '../ChatNew.module.css';
import type { AgentFileSummary, AgentFileTreeNode } from './useAgentFileTree';

type FileTreeMode = 'agent' | 'workspace';

interface ChatNewFilePanelProps {
  mode: FileTreeMode;
  onModeChange: (mode: FileTreeMode) => void;
  agentFileSummaries: AgentFileSummary[];
  agentFileTree: AgentFileTreeNode;
  expandedAgentFolders: Set<string>;
  onToggleAgentFolder: (path: string) => void;
  onOpenAgentFile: (file: AgentFileSummary) => void;
  workspaceTreeNodes: WorkspaceTreeNode[];
  workspaceTreeLoading: boolean;
  expandedWorkspaceFolders: Set<string>;
  projectPath: string;
  onToggleWorkspaceFolder: (path: string) => void;
  onOpenWorkspaceFile: (node: WorkspaceTreeNode) => void | Promise<void>;
  onSelectWorkspaceFile: (path: string) => void;
  onRefreshWorkspaceTree: () => void;
}

const getStatusTone = (status: string) => {
  const statusLower = status.toLowerCase();
  if (/add|new|create|新增/.test(statusLower)) return 'success';
  if (/delete|remove|removed|删除/.test(statusLower)) return 'error';
  if (/modify|update|change|edit|fix|modified|修改/.test(statusLower)) return 'processing';
  return 'default';
};

const ChatNewFilePanel = ({
  mode,
  onModeChange,
  agentFileSummaries,
  agentFileTree,
  expandedAgentFolders,
  onToggleAgentFolder,
  onOpenAgentFile,
  workspaceTreeNodes,
  workspaceTreeLoading,
  expandedWorkspaceFolders,
  projectPath,
  onToggleWorkspaceFolder,
  onOpenWorkspaceFile,
  onSelectWorkspaceFile,
  onRefreshWorkspaceTree,
}: ChatNewFilePanelProps) => {
  const handleWorkspaceFileKeyDown = (event: KeyboardEvent<HTMLDivElement>, node: WorkspaceTreeNode) => {
    if (event.key === 'Enter') {
      onSelectWorkspaceFile(node.path);
      void onOpenWorkspaceFile(node);
    }
  };

  const renderAgentNode = (node: AgentFileTreeNode, depth = 0): ReactNode => {
    if (node.kind === 'file' && node.file) {
      const file = node.file;
      const statusTone = getStatusTone(file.status);
      const icon = getFileIcon(node.name);
      const isText = isTextIcon(icon.icon);
      return (
        <div
          key={node.path}
          className={`${styles.agentFileCard} ${styles.agentFileCardClickable}`}
          style={{ ['--file-depth' as any]: String(depth) }}
          onClick={() => onOpenAgentFile(file)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => event.key === 'Enter' && onOpenAgentFile(file)}
        >
          <div className={styles.agentFileTreeRow}>
            <div className={styles.agentFileTreeLine} aria-hidden="true">
              <span className={styles.agentFileTreeBranch} />
              <span className={styles.agentFileTreeDot} data-tone={statusTone} />
            </div>
            <div className={styles.agentFileCardBody}>
              <div className={styles.agentFileCardTop}>
                <div className={styles.agentFilePath} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span
                    className={isText ? styles.iconBadge : styles.iconEmoji}
                    style={{ ['--icon-color' as any]: icon.color }}
                  >
                    {icon.icon}
                  </span>
                  <span>{node.name}</span>
                </div>
                <Tag className={styles.agentFileStatus} color={statusTone}>{file.status || 'modified'}</Tag>
              </div>
              <div className={styles.agentFileSummary}>{file.summary}</div>
            </div>
          </div>
        </div>
      );
    }

    if (node.kind === 'folder') {
      const isExpanded = !node.path || expandedAgentFolders.has(node.path);
      const childrenCount = node.children.length;
      const fileCount = node.children.filter((child) => child.kind === 'file').length;
      return (
        <div key={node.path || 'root'} className={styles.agentFolderGroup} style={{ ['--folder-depth' as any]: String(depth) }}>
          {node.path ? (
            <button
              type="button"
              className={styles.agentFolderRow}
              onClick={() => onToggleAgentFolder(node.path)}
            >
              <span className={`${styles.agentFolderChevron} ${isExpanded ? styles.agentFolderChevronOpen : ''}`}>▸</span>
              <span className={styles.agentFolderEmoji} style={{ marginRight: '4px', fontSize: '14px' }}>
                {isExpanded ? '📂' : '📁'}
              </span>
              <span className={styles.agentFolderName}>{node.name}</span>
              <Tag className={styles.agentFolderTag}>{childrenCount}</Tag>
              <Tag className={styles.agentFolderSubTag}>{fileCount} files</Tag>
            </button>
          ) : null}
          {isExpanded && (
            <div className={styles.agentFolderChildren}>
              {node.children.map((child) => renderAgentNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  const renderWorkspaceNode = (node: WorkspaceTreeNode, depth = 0): ReactNode => {
    if (node.kind === 'file') {
      const icon = getFileIcon(node.name);
      const isText = isTextIcon(icon.icon);
      return (
        <div
          key={node.path}
          className={`${styles.agentFileCard} ${styles.agentFileCardClickable}`}
          style={{ ['--file-depth' as any]: String(depth), margin: '0 4px 3px' }}
          onClick={() => {
            onSelectWorkspaceFile(node.path);
            void onOpenWorkspaceFile(node);
          }}
          onFocus={() => onSelectWorkspaceFile(node.path)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => handleWorkspaceFileKeyDown(event, node)}
        >
          <div className={styles.agentFileCardBody} style={{ padding: '8px 8px 8px 0' }}>
            <div className={styles.agentFileCardTop}>
              <div className={styles.agentFilePath} style={{ paddingLeft: `${depth * 10}px`, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span
                  className={isText ? styles.iconBadge : styles.iconEmoji}
                  style={{ ['--icon-color' as any]: icon.color }}
                >
                  {icon.icon}
                </span>
                <span>{node.name}</span>
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (node.kind === 'folder') {
      const isExpanded = expandedWorkspaceFolders.has(node.path);
      return (
        <div key={node.path} className={styles.agentFolderGroup} style={{ ['--folder-depth' as any]: String(depth) }}>
          <button
            type="button"
            className={styles.agentFolderRow}
            onClick={() => onToggleWorkspaceFolder(node.path)}
          >
            <span className={`${styles.agentFolderChevron} ${isExpanded ? styles.agentFolderChevronOpen : ''}`}>▸</span>
            <span className={styles.agentFolderEmoji} style={{ marginRight: '4px', fontSize: '14px' }}>
              {isExpanded ? '📂' : '📁'}
            </span>
            <span className={styles.agentFolderName}>{node.name}</span>
          </button>
          {isExpanded && node.children && (
            <div className={styles.agentFolderChildren}>
              {node.children.map((child) => renderWorkspaceNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  return (
    <div className={styles.slimFilePanel}>
      <div className={styles.slimFilePanelHeader}>
        <div className={styles.fileTreeToggle}>
          <button
            type="button"
            className={`${styles.fileTreeToggleBtn} ${mode === 'agent' ? styles.fileTreeToggleBtnActive : ''}`}
            onClick={() => onModeChange('agent')}
          >变更</button>
          <button
            type="button"
            className={`${styles.fileTreeToggleBtn} ${mode === 'workspace' ? styles.fileTreeToggleBtnActive : ''}`}
            onClick={() => onModeChange('workspace')}
          >工作区</button>
        </div>
        {mode === 'agent' && agentFileSummaries.length > 0 && (
          <span className={styles.slimFileCount}>{agentFileSummaries.length}</span>
        )}
        {mode === 'workspace' && (
          <button
            type="button"
            className={styles.fileTreeRefreshBtn}
            onClick={onRefreshWorkspaceTree}
            disabled={workspaceTreeLoading}
            title="刷新文件树"
          >↺</button>
        )}
      </div>
      {mode === 'agent' ? (
        agentFileSummaries.length > 0 ? (
          <div className={styles.slimFileList}>
            {renderAgentNode(agentFileTree)}
          </div>
        ) : (
          <div className={styles.agentFileEmpty}>暂无变更文件</div>
        )
      ) : (
        workspaceTreeLoading ? (
          <div className={styles.agentFileEmpty}>正在加载文件树…</div>
        ) : workspaceTreeNodes.length > 0 ? (
          <div className={styles.slimFileList}>
            {workspaceTreeNodes.map((node) => renderWorkspaceNode(node))}
          </div>
        ) : (
          <div className={styles.agentFileEmpty}>
            {projectPath ? '文件树为空或无法访问' : '请先选择工作区目录'}
          </div>
        )
      )}
    </div>
  );
};

export default ChatNewFilePanel;
