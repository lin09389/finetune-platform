/**
 * Coding-agent HITL review card.
 * Styled with workbench tokens (same density as training/command cards).
 */
import {
  CheckOutlined,
  CloseOutlined,
  CodeOutlined,
  EditOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Button, Input, Space, Tooltip } from 'antd';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import type {
  AgentHitlDecision,
  AgentSessionUiPendingPermission,
  AgentSessionUiPendingPermissionAction,
} from '../../services/api';
import { transitions } from '../../theme/motion-tokens';
import {
  allowsDecision,
  contentSnippet,
  extractPrimaryTarget,
  formatArgsPreview,
  permissionReviewTitle,
  sessionTrustHint,
  singleActionTitle,
  toolLabel,
} from '../permission/permissionReview';
import styles from '../workbench/AgentWorkbench.module.css';

export interface PermissionReviewCardProps {
  permission: AgentSessionUiPendingPermission;
  onDecide: (partId: string, decisions: AgentHitlDecision[]) => void | Promise<unknown>;
  busy?: boolean;
  compact?: boolean;
  autoFocus?: boolean;
  hideTitle?: boolean;
  surface?: 'default' | 'modal';
  onOpenFile?: (filePath: string) => void;
  className?: string;
}

type LocalDecision = 'approve' | 'reject' | 'edit' | null;

export default function PermissionReviewCard({
  permission,
  onDecide,
  busy = false,
  compact = false,
  autoFocus = true,
  hideTitle = false,
  surface = 'default',
  onOpenFile,
  className,
}: PermissionReviewCardProps) {
  const actions = permission.actions?.length
    ? permission.actions
    : [{ index: 0, name: 'tool', args: {}, allowed_decisions: ['approve', 'reject'] }];
  const partId = permission.part_id;
  const rootRef = useRef<HTMLDivElement>(null);
  const [submitted, setSubmitted] = useState<'approve' | 'reject' | 'mixed' | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectMessage, setRejectMessage] = useState('');
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editJson, setEditJson] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [perAction, setPerAction] = useState<Record<number, LocalDecision>>(() =>
    Object.fromEntries(actions.map((a, i) => [a.index ?? i, null])),
  );
  const reduceMotion = useReducedMotion();

  const title = useMemo(() => permissionReviewTitle(permission), [permission]);
  const trustHint = useMemo(() => sessionTrustHint(actions), [actions]);
  const multi = actions.length > 1;

  useEffect(() => {
    if (!autoFocus || submitted) return;
    const node = rootRef.current;
    if (!node) return;
    const id = window.requestAnimationFrame(() => {
      node.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [autoFocus, partId, submitted]);

  const submitDecisions = useCallback(
    async (decisions: AgentHitlDecision[], kind: 'approve' | 'reject' | 'mixed') => {
      if (busy || submitted || !partId) return;
      setSubmitted(kind);
      try {
        await Promise.resolve(onDecide(partId, decisions));
      } catch {
        setSubmitted(null);
      }
    },
    [busy, onDecide, partId, submitted],
  );

  const approveAll = useCallback(() => {
    void submitDecisions(
      actions.map(() => ({ type: 'approve' as const })),
      'approve',
    );
  }, [actions, submitDecisions]);

  const rejectAll = useCallback(
    (message?: string) => {
      const msg = (message ?? rejectMessage).trim() || '已在工作台拒绝';
      void submitDecisions(
        actions.map(() => ({ type: 'reject' as const, message: msg })),
        'reject',
      );
    },
    [actions, rejectMessage, submitDecisions],
  );

  const submitPerAction = useCallback(() => {
    const decisions: AgentHitlDecision[] = actions.map((action, i) => {
      const idx = action.index ?? i;
      const choice = perAction[idx] || 'approve';
      if (choice === 'reject') {
        return { type: 'reject' as const, message: rejectMessage.trim() || '已在工作台拒绝' };
      }
      return { type: 'approve' as const };
    });
    const kinds = new Set(decisions.map((d) => d.type));
    const kind = kinds.size === 1 ? (kinds.has('reject') ? 'reject' : 'approve') : 'mixed';
    void submitDecisions(decisions, kind);
  }, [actions, perAction, rejectMessage, submitDecisions]);

  const submitEdit = useCallback(
    (action: AgentSessionUiPendingPermissionAction, index: number) => {
      setEditError(null);
      let args: Record<string, unknown>;
      try {
        const parsed = JSON.parse(editJson) as unknown;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          setEditError('参数必须是 JSON 对象');
          return;
        }
        args = parsed as Record<string, unknown>;
      } catch {
        setEditError('JSON 无法解析');
        return;
      }
      const decisions: AgentHitlDecision[] = actions.map((a, i) => {
        if (i === index) {
          return {
            type: 'edit' as const,
            edited_action: { name: String(a.name || action.name), args },
          };
        }
        return { type: 'approve' as const };
      });
      void submitDecisions(decisions, 'approve');
    },
    [actions, editJson, submitDecisions],
  );

  const onKeyDown = (event: KeyboardEvent) => {
    if (busy || submitted) return;
    const target = event.target as HTMLElement | null;
    if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT' || target.isContentEditable)) {
      return;
    }
    if (event.key === 'y' || event.key === 'Y') {
      event.preventDefault();
      if (multi && Object.values(perAction).some(Boolean)) submitPerAction();
      else approveAll();
    }
    if (event.key === 'n' || event.key === 'N') {
      event.preventDefault();
      if (!rejectOpen) {
        setRejectOpen(true);
        return;
      }
      rejectAll();
    }
    if (event.key === 'Escape' && rejectOpen) {
      event.preventDefault();
      setRejectOpen(false);
    }
  };

  const rootClass = [
    styles.permissionReview,
    surface === 'modal' ? styles.permissionReviewSurfaceModal : styles.permissionReviewSurfaceDefault,
    compact ? styles.permissionReviewCompact : '',
    submitted ? styles.permissionReviewDone : '',
    className || '',
  ]
    .filter(Boolean)
    .join(' ');

  if (submitted) {
    return (
      <div className={rootClass} data-permission-review="done">
        <div className={styles.permissionReviewHeader}>
          <SafetyCertificateOutlined />
          <strong>
            {submitted === 'approve' ? '已批准' : submitted === 'reject' ? '已拒绝' : '已提交决定'}
          </strong>
        </div>
        <p className={styles.permissionReviewHint}>
          {submitted === 'approve'
            ? 'Agent 正在继续执行…'
            : submitted === 'reject'
              ? 'Agent 将根据拒绝结果调整后续步骤。'
              : '决定已提交，Agent 正在继续…'}
        </p>
        {submitted === 'approve' && trustHint ? (
          <p className={styles.permissionReviewTrust}>{trustHint}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className={rootClass}
      data-permission-review="pending"
      data-part-id={partId}
      tabIndex={0}
      role="region"
      aria-label={title.replace(/`/g, '')}
      onKeyDown={onKeyDown}
    >
      {!hideTitle ? (
        <div className={styles.permissionReviewHeader}>
          <SafetyCertificateOutlined />
          <strong className={styles.permissionReviewTitle}>{renderTitleWithCode(title)}</strong>
        </div>
      ) : null}

      {permission.content && !compact ? (
        <p className={styles.permissionReviewSub}>{permission.content}</p>
      ) : null}

      <div className={styles.permissionReviewActions}>
        {actions.map((action, index) => {
          const idx = action.index ?? index;
          const target = extractPrimaryTarget(action);
          const snippet = contentSnippet(action.args || {});
          const argsPreview = formatArgsPreview(action.args || {}, {
            omitKeys: snippet ? ['content', 'new_string', 'old_string'] : [],
            maxChars: compact ? 160 : 320,
          });
          const canEdit = allowsDecision(action, 'edit');
          const choice = perAction[idx];
          const TargetIcon = target.kind === 'command' ? CodeOutlined : FileTextOutlined;

          return (
            <div
              key={`${idx}-${action.name}`}
              className={`${styles.permissionActionBlock} ${choice ? styles[`permissionChoice_${choice}`] || '' : ''}`}
            >
              <div className={styles.permissionActionHead}>
                <span className={styles.permissionToolChip}>
                  <TargetIcon />
                  <code className={styles.permissionToolName}>{toolLabel(action.name)}</code>
                </span>
                {multi ? <span className={styles.permissionActionIndex}>#{index + 1}</span> : null}
                {multi ? (
                  <span className={styles.permissionPerActionToggles}>
                    <Button
                      size="small"
                      type={choice === 'approve' || !choice ? 'primary' : 'default'}
                      ghost={choice === 'reject'}
                      onClick={() => setPerAction((c) => ({ ...c, [idx]: 'approve' }))}
                    >
                      允
                    </Button>
                    <Button
                      size="small"
                      danger={choice === 'reject'}
                      type={choice === 'reject' ? 'primary' : 'default'}
                      onClick={() => setPerAction((c) => ({ ...c, [idx]: 'reject' }))}
                    >
                      拒
                    </Button>
                  </span>
                ) : null}
              </div>
              {multi ? (
                <div className={styles.permissionActionTitle}>
                  {renderTitleWithCode(singleActionTitle(action))}
                </div>
              ) : null}
              {target.kind === 'file' && target.detail ? (
                <div className={styles.permissionTargetRow}>
                  <FileTextOutlined />
                  {onOpenFile ? (
                    <button
                      type="button"
                      className={styles.permissionPathButton}
                      onClick={() =>
                        onOpenFile(
                          target.detail!.startsWith('/')
                            ? target.detail!
                            : `/workspace/${target.detail}`,
                        )
                      }
                    >
                      {target.detail}
                    </button>
                  ) : (
                    <code>{target.detail}</code>
                  )}
                </div>
              ) : null}
              {target.kind === 'command' && target.detail ? (
                <pre className={styles.permissionCommand}>{target.detail}</pre>
              ) : null}
              {snippet ? (
                <div className={styles.permissionSnippet}>
                  <span>{snippet.label}</span>
                  <pre>{snippet.text}</pre>
                </div>
              ) : null}
              {argsPreview && !snippet ? (
                <pre className={styles.permissionArgs}>{argsPreview}</pre>
              ) : null}
              {action.description ? (
                <p className={styles.permissionActionDesc}>{action.description}</p>
              ) : null}

              <AnimatePresence initial={false}>
                {canEdit && editIndex === index ? (
                  <motion.div
                    key="edit"
                    className={styles.permissionEditBox}
                    initial={reduceMotion ? false : { opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={transitions.base}
                  >
                    <label htmlFor={`perm-edit-${partId}-${idx}`}>编辑参数 (JSON)</label>
                    <Input.TextArea
                      id={`perm-edit-${partId}-${idx}`}
                      rows={compact ? 4 : 6}
                      value={editJson}
                      onChange={(e) => setEditJson(e.target.value)}
                      status={editError ? 'error' : undefined}
                    />
                    {editError ? (
                      <span className={styles.permissionEditError}>{editError}</span>
                    ) : null}
                    <Space size="small">
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => submitEdit(action, index)}
                        loading={busy}
                      >
                        用修改后的参数批准
                      </Button>
                      <Button
                        size="small"
                        onClick={() => {
                          setEditIndex(null);
                          setEditError(null);
                        }}
                      >
                        取消
                      </Button>
                    </Space>
                  </motion.div>
                ) : null}
              </AnimatePresence>

              {canEdit && editIndex !== index ? (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  className={styles.permissionEditLink}
                  onClick={() => {
                    setEditIndex(index);
                    setEditJson(JSON.stringify(action.args || {}, null, 2));
                    setEditError(null);
                  }}
                >
                  编辑参数后批准
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>

      <AnimatePresence initial={false}>
        {rejectOpen ? (
          <motion.div
            key="reject"
            className={styles.permissionRejectBox}
            initial={reduceMotion ? false : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={transitions.base}
          >
            <label htmlFor={`perm-reject-${partId}`}>拒绝原因（可选）</label>
            <Input.TextArea
              id={`perm-reject-${partId}`}
              rows={2}
              value={rejectMessage}
              placeholder="例如：路径不对 / 先别跑测试"
              onChange={(e) => setRejectMessage(e.target.value)}
              autoFocus
            />
          </motion.div>
        ) : null}
      </AnimatePresence>

      {trustHint ? <p className={styles.permissionReviewTrust}>{trustHint}</p> : null}

      <div className={styles.permissionReviewButtons}>
        {multi ? (
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            loading={busy}
            disabled={busy}
            onClick={() => {
              const anyChoice = Object.values(perAction).some((v) => v != null);
              if (anyChoice) submitPerAction();
              else approveAll();
            }}
          >
            确认决定
          </Button>
        ) : (
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            loading={busy}
            disabled={busy}
            onClick={approveAll}
          >
            批准
          </Button>
        )}
        {!rejectOpen ? (
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            disabled={busy}
            onClick={() => setRejectOpen(true)}
          >
            拒绝
          </Button>
        ) : (
          <Button
            size="small"
            danger
            type="primary"
            icon={<CloseOutlined />}
            loading={busy}
            disabled={busy}
            onClick={() => rejectAll()}
          >
            确认拒绝
          </Button>
        )}
        <Tooltip title="焦点在卡片上时：Y 批准 · N 拒绝">
          <span className={styles.permissionHotkeys}>Y / N</span>
        </Tooltip>
      </div>
    </div>
  );
}

function renderTitleWithCode(title: string) {
  const parts = title.split(/(`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={i}>{part.slice(1, -1)}</code>;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
