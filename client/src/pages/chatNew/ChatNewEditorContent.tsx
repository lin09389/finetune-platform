import type { PointerEvent } from 'react';

import AgentTerminal from '../../components/chat/AgentTerminal';
import AgentWorkspaceEditor from '../../components/chat/AgentWorkspaceEditor';
import type { OpenedFile } from '../../components/chat/AgentWorkspaceEditor';
import type { ActiveFileContext } from '../../services/api';
import styles from '../ChatNew.module.css';

interface ChatNewEditorContentProps {
  openedFiles: OpenedFile[];
  activeFilePath: string | null;
  onTabChange: (path: string) => void;
  onTabClose: (path: string) => void;
  onActiveContextChange: (context: ActiveFileContext | null) => void;
  onAcceptHunk: (filePath: string, hunkId: string) => void | Promise<void>;
  onRejectHunk: (filePath: string, hunkId: string) => void | Promise<void>;
  onAcceptAll: (filePath: string) => void;
  onRejectAll: (filePath: string) => void;
  onSave: (filePath: string, content: string) => void | Promise<void>;
  activeTerminalId: string | null;
  terminalOpen: boolean;
  onToggleTerminal: () => void;
  onCloseTerminal: () => void;
  terminalHeight: number;
  resizingTerminal: boolean;
  onTerminalResizePointerDown: (event: PointerEvent<HTMLDivElement>) => void;
  terminalRunning: boolean;
  workspaceRoot: string;
  onBreadcrumbClick: (segment: string, fullPath: string) => void;
}

const ChatNewEditorContent = ({
  openedFiles,
  activeFilePath,
  onTabChange,
  onTabClose,
  onActiveContextChange,
  onAcceptHunk,
  onRejectHunk,
  onAcceptAll,
  onRejectAll,
  onSave,
  activeTerminalId,
  terminalOpen,
  onToggleTerminal,
  onCloseTerminal,
  terminalHeight,
  resizingTerminal,
  onTerminalResizePointerDown,
  terminalRunning,
  workspaceRoot,
  onBreadcrumbClick,
}: ChatNewEditorContentProps) => (
  <div className={styles.editorWithTerminal}>
    <div className={styles.editorPaneMain}>
      <AgentWorkspaceEditor
        openedFiles={openedFiles}
        activeFilePath={activeFilePath}
        onTabChange={onTabChange}
        onTabClose={onTabClose}
        onActiveContextChange={onActiveContextChange}
        onAcceptHunk={onAcceptHunk}
        onRejectHunk={onRejectHunk}
        onAcceptAll={onAcceptAll}
        onRejectAll={onRejectAll}
        onSave={onSave}
        activeTerminalId={activeTerminalId}
        onToggleTerminal={onToggleTerminal}
        terminalOpen={terminalOpen}
        workspaceRoot={workspaceRoot}
        onBreadcrumbClick={onBreadcrumbClick}
      />
    </div>
    {terminalOpen && activeTerminalId && (
      <div
        className={styles.terminalDock}
        style={{ height: terminalHeight, minHeight: 120, maxHeight: '60%' }}
      >
        <div
          className={`${styles.terminalDockResizer} ${resizingTerminal ? styles.terminalDockResizerActive : ''}`}
          onPointerDown={onTerminalResizePointerDown}
        />
        <div className={styles.terminalDockBar}>
          <span className={styles.terminalDockTitle}>Terminal</span>
          <button
            type="button"
            className={styles.terminalDockClose}
            onClick={onCloseTerminal}
            aria-label="关闭终端"
          >
            &times;
          </button>
        </div>
        <AgentTerminal
          terminalId={activeTerminalId}
          running={terminalRunning}
        />
      </div>
    )}
  </div>
);

export default ChatNewEditorContent;
