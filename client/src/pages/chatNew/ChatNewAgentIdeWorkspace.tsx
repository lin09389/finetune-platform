import type { ReactNode } from 'react';
import { Button, Input, Tag, Tooltip } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';

import styles from '../ChatNew.module.css';

interface ChatNewAgentIdeWorkspaceProps {
  projectPath: string;
  workspaceProjectPath: string;
  openedFileCount: number;
  showPathEdit: boolean;
  treePanel: ReactNode;
  editorPanel: ReactNode;
  onPathClick: () => void;
  onPickFolder: () => void | Promise<void>;
  onProjectPathChange: (value: string) => void;
  onConfirmPath: () => void;
}

const hasElectronApi = () => typeof window !== 'undefined' && Boolean((window as any).electronAPI);

const ChatNewAgentIdeWorkspace = ({
  projectPath,
  workspaceProjectPath,
  openedFileCount,
  showPathEdit,
  treePanel,
  editorPanel,
  onPathClick,
  onPickFolder,
  onProjectPathChange,
  onConfirmPath,
}: ChatNewAgentIdeWorkspaceProps) => (
  <section className={styles.agentIdeWorkspace} style={{ flex: '1 1 0', minWidth: 0 }} aria-label="AI 编程工作区">
    <div className={styles.agentIdeHeader}>
      <div style={{ minWidth: 0 }}>
        <div className={styles.agentIdeKicker}>Agent IDE</div>
        <div className={styles.agentIdeTitle}>代码审阅与补丁确认</div>
        {projectPath ? (
          <div
            className={styles.agentIdePath}
            title={hasElectronApi() ? '点击打开本地文件夹' : '点击编辑项目路径'}
            onClick={onPathClick}
          >
            <FolderOpenOutlined style={{ fontSize: 10, opacity: 0.7 }} />
            <span className={styles.agentIdePathText}>{projectPath}</span>
          </div>
        ) : (
          <div className={styles.agentIdePathEmpty}>未绑定工作区目录</div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flex: '0 0 auto' }}>
        <Tooltip title={hasElectronApi() ? '选择本地项目文件夹' : '手动输入项目路径'}>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => void onPickFolder()}>
            {projectPath ? '更换' : '选择文件夹'}
          </Button>
        </Tooltip>
        <Tag color={openedFileCount ? 'processing' : 'default'} className={styles.agentIdeTag}>
          {openedFileCount ? `${openedFileCount} opened` : 'No file opened'}
        </Tag>
      </div>
    </div>
    {showPathEdit && (
      <div className={styles.agentIdePathEdit}>
        <Input
          size="small"
          prefix={<FolderOpenOutlined style={{ opacity: 0.5 }} />}
          placeholder="例如：C:\\Projects\\my-app"
          value={workspaceProjectPath}
          onChange={(event) => onProjectPathChange(event.target.value)}
          onPressEnter={onConfirmPath}
          autoFocus
          suffix={
            <Button type="link" size="small" style={{ height: 20, padding: 0 }} onClick={onConfirmPath}>确认</Button>
          }
        />
      </div>
    )}
    <div className={styles.agentIdeBody}>
      <aside className={styles.agentIdeTreePane}>{treePanel}</aside>
      <main className={styles.agentIdeEditorPane}>{editorPanel}</main>
    </div>
  </section>
);

export default ChatNewAgentIdeWorkspace;
