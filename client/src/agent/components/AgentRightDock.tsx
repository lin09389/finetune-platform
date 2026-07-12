import { CloseOutlined, DoubleRightOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import { type ReactNode } from 'react';
import { useMotionConfig } from '../../components/motion/useMotionConfig';
import { fadeVariants } from '../../theme/motion-tokens';
import type {
  AgentPanelLayout,
  AgentTaskCenterTab,
  AgentWorkspacePanelTab,
} from '../config/panelLayout';
import {
  MAX_DOCK_WIDTH,
  MAX_WORKSPACE_SPLIT,
  MIN_DOCK_WIDTH,
  MIN_WORKSPACE_SPLIT,
} from '../config/panelLayout';
import styles from '../workbench/AgentWorkbench.module.css';
import type { PanelResizeHandlers } from '../workbench/usePanelResize';
import AgentResizeHandle from './AgentResizeHandle';
import polish from './AgentRightDock.module.css';

interface WorkspaceTabDef {
  key: AgentWorkspacePanelTab;
  label: string;
}

interface TaskCenterTabDef {
  key: AgentTaskCenterTab;
  label: string;
}

interface AgentRightDockProps {
  panelLayout: AgentPanelLayout;
  rightDockRef: React.Ref<HTMLElement>;
  isDesktop: boolean;
  rightDockVisible: boolean;
  workspaceTabs: WorkspaceTabDef[];
  taskCenterTabs: TaskCenterTabDef[];
  workspacePanel: ReactNode;
  taskCenterPanel: ReactNode;
  subagentAttentionCount: number;
  resize: PanelResizeHandlers;
  onOpenWorkspaceTab: (tab: AgentWorkspacePanelTab) => void;
  onOpenTaskCenterTab: (tab: AgentTaskCenterTab) => void;
  onCollapseWorkspace: () => void;
  onCollapseTaskCenter: () => void;
  onMobileDockClose: () => void;
}

/**
 * 工作台右侧停靠栏：工作区 + 任务中心双面板，中间可拖拽 split。
 *
 * 从 AgentWorkbenchPage 抽出。面板内容以 ReactNode 注入，tab 配置与切换回调
 * 由 Page 提供，保持 dock 组件无状态、不耦合 runtime。
 */
export default function AgentRightDock({
  panelLayout,
  rightDockRef,
  isDesktop,
  rightDockVisible,
  workspaceTabs,
  taskCenterTabs,
  workspacePanel,
  taskCenterPanel,
  subagentAttentionCount,
  resize,
  onOpenWorkspaceTab,
  onOpenTaskCenterTab,
  onCollapseWorkspace,
  onCollapseTaskCenter,
  onMobileDockClose,
}: AgentRightDockProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <aside
      ref={rightDockRef}
      className={`${styles.rightDock} ${polish.dock}`}
      data-visible={rightDockVisible ? 'true' : 'false'}
      data-workspace-open={panelLayout.workspaceOpen ? 'true' : 'false'}
      data-tasks-open={panelLayout.taskCenterOpen ? 'true' : 'false'}
      aria-label="工作台侧栏"
      aria-hidden={!rightDockVisible}
    >
      <AgentResizeHandle
        target="dock"
        valueNow={panelLayout.dockWidth}
        valueMin={MIN_DOCK_WIDTH}
        valueMax={MAX_DOCK_WIDTH}
        isDesktop={isDesktop}
        resize={resize}
        className={styles.dockResizeHandle}
      />
      <button
        type="button"
        className={`${styles.mobileDockClose} ${polish.mobileClose}`}
        aria-label="关闭工作台侧栏"
        data-auxiliary-control="true"
        onClick={onMobileDockClose}
      >
        <CloseOutlined />
      </button>
      <section
        className={`${styles.workspaceDockPanel} ${polish.workspacePanel}`}
        hidden={!panelLayout.workspaceOpen}
        aria-label="工作区"
      >
        <header className={`${styles.dockPanelHeader} ${polish.panelHeader}`}>
          <div role="tablist" aria-label="工作区视图">
            {workspaceTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={panelLayout.workspaceTab === tab.key}
                className={`${panelLayout.workspaceTab === tab.key ? styles.dockPanelTabActive : styles.dockPanelTab} ${polish.tab}`}
                onClick={() => onOpenWorkspaceTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <Tooltip title="隐藏工作区">
            <button
              type="button"
              aria-label="隐藏工作区"
              className={polish.dismissButton}
              data-auxiliary-control="true"
              onClick={onCollapseWorkspace}
            >
              <DoubleRightOutlined />
            </button>
          </Tooltip>
        </header>
        <div className={styles.dockPanelBody}>
          <AnimatePresence initial={false}>
            <motion.div
              key="workspace-content"
              variants={getSafeVariants(fadeVariants)}
              initial="initial"
              animate="animate"
              exit="exit"
              style={{ width: '100%', height: '100%' }}
            >
              {workspacePanel}
            </motion.div>
          </AnimatePresence>
        </div>
      </section>
      <AgentResizeHandle
        target="workspace-split"
        valueNow={panelLayout.workspaceSplit}
        valueMin={MIN_WORKSPACE_SPLIT}
        valueMax={MAX_WORKSPACE_SPLIT}
        isDesktop={isDesktop}
        visible={panelLayout.workspaceOpen && panelLayout.taskCenterOpen}
        resize={resize}
        className={styles.workspaceSplitResizeHandle}
      />
      <section
        className={`${styles.taskCenterDockPanel} ${polish.taskCenterPanel}`}
        hidden={!panelLayout.taskCenterOpen}
        aria-label="任务中心"
      >
        <header className={`${styles.dockPanelHeader} ${polish.panelHeader}`}>
          <div className={styles.taskCenterTitle}>任务中心</div>
          <Tooltip title="隐藏任务中心">
            <button
              type="button"
              aria-label="隐藏任务中心"
              className={polish.dismissButton}
              data-auxiliary-control="true"
              onClick={onCollapseTaskCenter}
            >
              <DoubleRightOutlined />
            </button>
          </Tooltip>
        </header>
        <nav
          className={`${styles.taskCenterTabs} ${polish.taskCenterTabs}`}
          aria-label="任务中心视图"
        >
          {taskCenterTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              aria-current={panelLayout.taskCenterTab === tab.key ? 'page' : undefined}
              className={`${panelLayout.taskCenterTab === tab.key ? styles.dockPanelTabActive : styles.dockPanelTab} ${polish.tab}`}
              onClick={() => onOpenTaskCenterTab(tab.key)}
            >
              {tab.label}
              {tab.key === 'subagents' && subagentAttentionCount ? (
                <span className={styles.tabCount}>{subagentAttentionCount}</span>
              ) : null}
            </button>
          ))}
        </nav>
        <div className={styles.dockPanelBody}>
          <AnimatePresence initial={false}>
            <motion.div
              key={`task-center-${panelLayout.taskCenterTab}`}
              variants={getSafeVariants(fadeVariants)}
              initial="initial"
              animate="animate"
              exit="exit"
              style={{ width: '100%', height: '100%' }}
            >
              {taskCenterPanel}
            </motion.div>
          </AnimatePresence>
        </div>
      </section>
    </aside>
  );
}
