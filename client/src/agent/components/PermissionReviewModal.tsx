/**
 * Modal HITL review — outside the conversation timeline.
 * Visual language matches Agent Workbench cards / SubagentModal (tokens, quiet chrome).
 */
import { SafetyCertificateOutlined } from '@ant-design/icons';
import { Modal } from 'antd';
import { motion, useReducedMotion } from 'framer-motion';
import { useEffect, useState } from 'react';
import type {
  AgentHitlDecision,
  AgentSessionUiPendingPermission,
} from '../../services/api';
import { transitions } from '../../theme/motion-tokens';
import { permissionReviewTitle } from '../permission/permissionReview';
import PermissionReviewCard from './PermissionReviewCard';
import styles from '../workbench/AgentWorkbench.module.css';

export interface PermissionReviewModalProps {
  permission: AgentSessionUiPendingPermission | null;
  busy?: boolean;
  onDecide: (partId: string, decisions: AgentHitlDecision[]) => void | Promise<unknown>;
  onOpenFile?: (filePath: string) => void;
}

export default function PermissionReviewModal({
  permission,
  busy = false,
  onDecide,
  onOpenFile,
}: PermissionReviewModalProps) {
  const partId = permission?.part_id || null;
  const [open, setOpen] = useState(false);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    setOpen(Boolean(permission?.part_id));
  }, [permission?.part_id]);

  if (!permission || !partId) {
    return null;
  }

  const titleText = permissionReviewTitle(permission).replace(/`/g, '');
  const actionCount = permission.actions?.length || 0;

  return (
    <Modal
      open={open}
      title={
        <div className={styles.permissionReviewModalTitleRow}>
          <SafetyCertificateOutlined className={styles.permissionReviewModalTitleIcon} />
          <span>需要确认</span>
          {actionCount > 1 ? (
            <span className={styles.permissionReviewModalCount}>{actionCount} 项</span>
          ) : null}
        </div>
      }
      footer={null}
      centered
      destroyOnHidden
      maskClosable={false}
      keyboard={false}
      width={480}
      className={styles.permissionReviewModal}
      closable={false}
      data-testid="permission-review-modal"
    >
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={transitions.base}
      >
        <h2 className={styles.permissionReviewModalTitle}>{titleText}</h2>
        <p className={styles.permissionReviewModalHint}>
          Agent 已暂停，不会继续改文件或执行命令，直到你决定。
        </p>
        <PermissionReviewCard
          permission={permission}
          busy={busy}
          autoFocus
          hideTitle
          surface="modal"
          onOpenFile={onOpenFile}
          onDecide={async (id, decisions) => {
            await Promise.resolve(onDecide(id, decisions));
          }}
        />
      </motion.div>
    </Modal>
  );
}
