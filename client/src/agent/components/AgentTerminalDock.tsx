import { DownOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import { Suspense, lazy } from 'react';
import type { AgentSessionUiTimelineItem } from '../../services/api';
import { fadeVariants } from '../../theme/motion-tokens';
import { SmoothLoader } from '../../components/motion';
import { useMotionConfig } from '../../components/motion/useMotionConfig';
import type { PanelResizeHandlers } from '../workbench/usePanelResize';
import {
  MAX_TERMINAL_HEIGHT,
  MIN_TERMINAL_HEIGHT,
} from '../config/panelLayout';
import AgentResizeHandle from './AgentResizeHandle';
import styles from '../workbench/AgentWorkbench.module.css';

const AgentTerminalPanel = lazy(() => import('./AgentTerminalPanel'));

interface AgentTerminalDockProps {
  visible: boolean;
  mounted: boolean;
  isDesktop: boolean;
  terminalHeight: number;
  timeline: AgentSessionUiTimelineItem[];
  resize: PanelResizeHandlers;
  onClose: () => void;
}

/**
 * 终端停靠区：resize 分隔条 + 标题栏 + 懒加载 xterm 面板。
 *
 * 从 AgentWorkbenchPage 抽出，保持 mounted 与 visible 分离——面板可隐藏但 xterm
 * 实例不销毁，避免重复 WebSocket 重连。
 */
export default function AgentTerminalDock({
  visible,
  mounted,
  isDesktop,
  terminalHeight,
  timeline,
  resize,
  onClose,
}: AgentTerminalDockProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <section
      className={styles.terminalDock}
      data-visible={visible ? 'true' : 'false'}
      aria-label="终端面板"
      aria-hidden={!visible}
    >
      <AgentResizeHandle
        target="terminal"
        valueNow={terminalHeight}
        valueMin={MIN_TERMINAL_HEIGHT}
        valueMax={MAX_TERMINAL_HEIGHT}
        isDesktop={isDesktop}
        resize={resize}
        className={styles.terminalResizeHandle}
      />
      <header className={styles.terminalDockHeader}>
        <span>终端</span>
        <Tooltip title="隐藏终端">
          <button
            type="button"
            aria-label="隐藏终端"
            onClick={onClose}
          >
            <DownOutlined />
          </button>
        </Tooltip>
      </header>
      <div className={styles.terminalDockBody}>
        <AnimatePresence initial={false}>
          {mounted ? (
            <motion.div
              key="terminal-content"
              variants={getSafeVariants(fadeVariants)}
              initial="initial"
              animate="animate"
              exit="exit"
              style={{ width: '100%', height: '100%' }}
            >
              <Suspense fallback={<div className={styles.panelLoading}><SmoothLoader size="sm" /></div>}>
                <AgentTerminalPanel timeline={timeline} />
              </Suspense>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </section>
  );
}
