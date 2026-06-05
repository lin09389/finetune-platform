import { Button, Input, Typography } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AgentHitlDecision, AgentSessionUiPendingPermission } from '../../services/api';
import styles from '../../pages/ChatNew.module.css';

type HitlDecisionType = AgentHitlDecision['type'];

interface HitlDecisionDraft {
  type: HitlDecisionType;
  message: string;
  editedArgs: string;
  error?: string;
}

interface HitlApprovalPanelProps {
  pendingPermission?: AgentSessionUiPendingPermission | null;
  prefersReducedMotion?: boolean;
  presentation?: 'popover' | 'panel';
  onSubmit: (permissionId: string, decisions: AgentHitlDecision[]) => void | Promise<void>;
}

const DECISION_TYPES: HitlDecisionType[] = ['approve', 'edit', 'reject', 'respond'];

const DECISION_LABELS: Record<HitlDecisionType, string> = {
  approve: '批准',
  reject: '拒绝',
  edit: '修改参数',
  respond: '回复',
};

export default function HitlApprovalPanel({
  pendingPermission,
  prefersReducedMotion = false,
  presentation = 'popover',
  onSubmit,
}: HitlApprovalPanelProps) {
  const [drafts, setDrafts] = useState<Record<number, HitlDecisionDraft>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const actions = useMemo(() => pendingPermission?.actions || [], [pendingPermission?.actions]);

  useEffect(() => {
    if (!pendingPermission?.part_id) {
      setDrafts({});
      setSubmitting(false);
      setSubmissionError(null);
      return;
    }
    setSubmissionError(null);
    setDrafts((current) => {
      const next: Record<number, HitlDecisionDraft> = {};
      actions.forEach((action) => {
        const existing = current[action.index];
        const defaultType = (action.allowed_decisions.includes('approve')
          ? 'approve'
          : action.allowed_decisions[0] || 'approve') as HitlDecisionType;
        next[action.index] = existing || {
          type: defaultType,
          message: '',
          editedArgs: JSON.stringify(action.args || {}, null, 2),
        };
      });
      return next;
    });
  }, [actions, pendingPermission?.part_id]);

  const updateDraft = useCallback((index: number, updates: Partial<HitlDecisionDraft>) => {
    setDrafts((current) => ({
      ...current,
      [index]: { ...(current[index] || { type: 'approve', message: '', editedArgs: '{}' }), error: undefined, ...updates },
    }));
  }, []);

  const buildDecisions = useCallback((): AgentHitlDecision[] | null => {
    const decisions: AgentHitlDecision[] = [];
    for (const action of actions) {
      const draft = drafts[action.index];
      if (!draft) return null;
      if (draft.type === 'approve') {
        decisions.push({ type: 'approve' });
      } else if (draft.type === 'reject') {
        decisions.push({ type: 'reject', ...(draft.message.trim() ? { message: draft.message.trim() } : {}) });
      } else if (draft.type === 'respond') {
        if (!draft.message.trim()) {
          updateDraft(action.index, { error: '回复需要填写内容。' });
          return null;
        }
        decisions.push({ type: 'respond', message: draft.message.trim() });
      } else if (draft.type === 'edit') {
        try {
          const args = JSON.parse(draft.editedArgs || '{}');
          if (!args || typeof args !== 'object' || Array.isArray(args)) {
            throw new Error('修改参数必须是 JSON 对象。');
          }
          decisions.push({ type: 'edit', edited_action: { name: action.name, args } });
        } catch (error) {
          updateDraft(action.index, {
            error: error instanceof Error ? error.message : '修改参数必须是有效 JSON。',
          });
          return null;
        }
      }
    }
    return decisions;
  }, [actions, drafts, updateDraft]);

  const submit = useCallback(async () => {
    if (!pendingPermission?.part_id || submitting) return;
    const decisions = buildDecisions();
    if (!decisions) return;
    setSubmitting(true);
    setSubmissionError(null);
    try {
      await onSubmit(pendingPermission.part_id, decisions);
    } catch (error) {
      setSubmissionError(error instanceof Error ? error.message : '提交决策失败。');
    } finally {
      setSubmitting(false);
    }
  }, [buildDecisions, onSubmit, pendingPermission?.part_id, submitting]);

  const rejectAll = useCallback(async () => {
    if (!pendingPermission?.part_id || !actions.length || submitting) return;
    setSubmitting(true);
    setSubmissionError(null);
    try {
      await onSubmit(pendingPermission.part_id, actions.map(() => ({ type: 'reject' })));
    } catch (error) {
      setSubmissionError(error instanceof Error ? error.message : '全部拒绝失败。');
    } finally {
      setSubmitting(false);
    }
  }, [actions, onSubmit, pendingPermission?.part_id, submitting]);

  return (
    <AnimatePresence>
      {pendingPermission?.part_id && (
        <motion.div
          key={pendingPermission.part_id}
          className={presentation === 'panel' ? `${styles.approvalPopover} ${styles.approvalPanel}` : styles.approvalPopover}
          initial={prefersReducedMotion ? false : { opacity: 0, y: 14, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.985 }}
          transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className={styles.approvalPopoverHeader}>
            <span className={styles.approvalTerminalIcon}>›_</span>
            <Typography.Text strong>
              确认 {actions.length || 1} 个 Agent 动作
            </Typography.Text>
          </div>
          <div className={styles.approvalBatchList}>
            {actions.map((action) => {
              const draft = drafts[action.index] || {
                type: 'approve' as HitlDecisionType,
                message: '',
                editedArgs: JSON.stringify(action.args || {}, null, 2),
              };
              return (
                <div className={styles.approvalActionCard} key={`${pendingPermission.part_id}-${action.index}`}>
                  <div className={styles.approvalActionHeader}>
                    <span className={styles.approvalKeycap}>{action.index + 1}</span>
                    <Typography.Text code>{action.name}</Typography.Text>
                  </div>
                  <pre className={styles.approvalArgs}>{JSON.stringify(action.args || {}, null, 2)}</pre>
                  <div className={styles.approvalChoices}>
                    {DECISION_TYPES
                      .filter((type) => action.allowed_decisions.includes(type))
                      .map((type) => (
                        <button
                          type="button"
                          key={type}
                          className={draft.type === type ? styles.approvalChoicePrimary : styles.approvalChoice}
                          disabled={submitting}
                          onClick={() => updateDraft(action.index, { type })}
                        >
                          {DECISION_LABELS[type]}
                        </button>
                      ))}
                  </div>
                  {draft.type === 'edit' && (
                    <Input.TextArea
                      className={styles.approvalTextarea}
                      value={draft.editedArgs}
                      autoSize={{ minRows: 3, maxRows: 8 }}
                      disabled={submitting}
                      onChange={(event) => updateDraft(action.index, { editedArgs: event.target.value })}
                    />
                  )}
                  {(draft.type === 'reject' || draft.type === 'respond') && (
                    <Input.TextArea
                      className={styles.approvalTextarea}
                      value={draft.message}
                      placeholder={draft.type === 'respond' ? '作为工具结果返回给 Agent 的回复' : '可选：给 Agent 的反馈'}
                      autoSize={{ minRows: 2, maxRows: 5 }}
                      disabled={submitting}
                      onChange={(event) => updateDraft(action.index, { message: event.target.value })}
                    />
                  )}
                  {draft.error && <Typography.Text type="danger">{draft.error}</Typography.Text>}
                </div>
              );
            })}
          </div>
          {submissionError && <Typography.Text type="danger">{submissionError}</Typography.Text>}
          <div className={styles.approvalFooter}>
            <Button
              size="small"
              type="text"
              disabled={submitting || !actions.every((action) => action.allowed_decisions.includes('reject'))}
              loading={submitting}
              onClick={() => void rejectAll()}
            >
              全部拒绝
            </Button>
            <Button size="small" type="primary" loading={submitting} onClick={() => void submit()}>
              提交决策
            </Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
