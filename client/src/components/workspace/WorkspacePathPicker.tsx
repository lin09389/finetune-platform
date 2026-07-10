import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Input, Tooltip, message } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  CopyOutlined,
  ExclamationCircleFilled,
  FolderOpenOutlined,
  LoadingOutlined,
  LockOutlined,
  PlusOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import {
  browseWorkspaceFolder,
  createWorkspace,
  getAllowedWorkspaceRoots,
  listWorkspaces,
  validateWorkspacePath,
  type WorkspacePathValidation,
  type WorkspaceSummary,
} from '../../services/api';
import styles from './WorkspacePathPicker.module.css';

const RECENT_PATHS_KEY = 'finetune.workspace.recent-paths.v1';
const MAX_RECENT = 8;

export type WorkspacePathPickerProps = {
  value: string;
  disabled?: boolean;
  onChange: (path: string) => void;
  onValidated?: (result: WorkspacePathValidation | null) => void;
};

type QuickPick = {
  path: string;
  label: string;
  kind: 'default' | 'recent' | 'workspace';
};

function readRecentPaths(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_PATHS_KEY);
    const parsed = JSON.parse(raw || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function pushRecentPath(path: string): string[] {
  const normalized = path.trim();
  if (!normalized) return readRecentPaths();
  const next = [normalized, ...readRecentPaths().filter((item) => item !== normalized)].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(RECENT_PATHS_KEY, JSON.stringify(next));
  } catch {
    // ignore quota / private mode
  }
  return next;
}

function basename(path: string): string {
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return segments[segments.length - 1] || path;
}

function shortenPath(path: string, max = 56): string {
  const normalized = path.replace(/\\/g, '/');
  if (normalized.length <= max) return path;
  const head = Math.max(12, Math.floor(max * 0.35));
  const tail = max - head - 1;
  return `${path.slice(0, head)}…${path.slice(-tail)}`;
}

/**
 * Shared project-path picker for Agent workbench.
 * Browse-first UX, quick picks, compact status, register loop.
 */
export default function WorkspacePathPicker({
  value,
  disabled = false,
  onChange,
  onValidated,
}: WorkspacePathPickerProps) {
  const [recentPaths, setRecentPaths] = useState<string[]>(() => readRecentPaths());
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [defaultPath, setDefaultPath] = useState<string>('');
  const [validation, setValidation] = useState<WorkspacePathValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [browseError, setBrowseError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [roots, listed] = await Promise.all([
          getAllowedWorkspaceRoots().catch(() => null),
          listWorkspaces().catch(() => [] as WorkspaceSummary[]),
        ]);
        if (cancelled) return;
        if (roots?.default_project_path) setDefaultPath(roots.default_project_path);
        setWorkspaces(Array.isArray(listed) ? listed : []);
      } catch {
        // non-fatal
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const runValidate = useCallback(
    async (path: string, options?: { remember?: boolean }) => {
      setValidating(true);
      setBrowseError(null);
      try {
        const result = await validateWorkspacePath(path.trim() ? path : null);
        setValidation(result);
        onValidated?.(result);
        if (options?.remember && result.ok && result.resolved_path && path.trim()) {
          setRecentPaths(pushRecentPath(result.resolved_path));
        }
        return result;
      } catch (error) {
        const failed: WorkspacePathValidation = {
          ok: false,
          resolved_path: path || null,
          allowed: false,
          exists: false,
          is_dir: false,
          needs_register: false,
          message: error instanceof Error ? error.message : '路径校验失败',
          error_code: 'path_missing',
        };
        setValidation(failed);
        onValidated?.(failed);
        return failed;
      } finally {
        setValidating(false);
      }
    },
    [onValidated],
  );

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void runValidate(value, { remember: Boolean(value.trim()) });
    }, 320);
    return () => window.clearTimeout(handle);
  }, [value, runValidate]);

  const quickPicks = useMemo(() => {
    const items: QuickPick[] = [];
    const seen = new Set<string>();
    const add = (path: string, label: string, kind: QuickPick['kind']) => {
      const key = path.trim();
      if (!key || seen.has(key.toLowerCase())) return;
      seen.add(key.toLowerCase());
      items.push({ path: key, label, kind });
    };
    if (defaultPath) add(defaultPath, '默认项目', 'default');
    for (const path of recentPaths.slice(0, 5)) {
      add(path, basename(path), 'recent');
    }
    for (const workspace of workspaces.slice(0, 6)) {
      if (workspace.local_path) {
        add(workspace.local_path, workspace.name || basename(workspace.local_path), 'workspace');
      }
    }
    return items;
  }, [defaultPath, recentPaths, workspaces]);

  const displayPath = validation?.resolved_path || value.trim() || defaultPath || '';
  const folderName = displayPath ? basename(displayPath) : '未选择工作区';
  const isUsingDefault = !value.trim() && Boolean(defaultPath);

  const tone: 'ok' | 'warn' | 'error' | 'idle' = validating
    ? 'idle'
    : validation?.ok
      ? 'ok'
      : validation?.needs_register
        ? 'warn'
        : validation
          ? 'error'
          : 'idle';

  const statusMessage = validating
    ? '正在校验路径…'
    : validation?.ok
      ? isUsingDefault
        ? `可用 · 默认工作区 ${shortenPath(displayPath)}`
        : `可用 · ${shortenPath(displayPath)}`
      : validation?.message || '留空将使用后端默认工作区；也可浏览选择本地文件夹。';

  const applyPath = (path: string, toast?: string) => {
    onChange(path);
    if (toast) message.success(toast);
  };

  const handleBrowse = async () => {
    if (disabled) return;
    setBrowsing(true);
    setBrowseError(null);
    try {
      const selected = await browseWorkspaceFolder(value || defaultPath || undefined);
      if (selected) {
        applyPath(selected, '已选择文件夹');
        const result = await runValidate(selected, { remember: true });
        if (result.ok && result.resolved_path) {
          setRecentPaths(pushRecentPath(result.resolved_path));
        }
      }
    } catch (error) {
      setBrowseError(error instanceof Error ? error.message : '无法打开文件夹选择，请手动输入路径');
    } finally {
      setBrowsing(false);
    }
  };

  const handleRegister = async () => {
    if (disabled || !value.trim()) return;
    setRegistering(true);
    setBrowseError(null);
    try {
      const name = basename(value.trim()) || 'Workspace';
      const created = await createWorkspace({
        name,
        description: '从 Agent 工作台登记',
        local_path: value.trim(),
      });
      const nextPath = created.local_path || value.trim();
      applyPath(nextPath, '已登记为工作区');
      setWorkspaces((prev) => {
        if (prev.some((item) => item.id === created.id)) return prev;
        return [created, ...prev];
      });
      const result = await runValidate(nextPath, { remember: true });
      if (result.ok && result.resolved_path) {
        setRecentPaths(pushRecentPath(result.resolved_path));
      }
    } catch (error) {
      setBrowseError(error instanceof Error ? error.message : '登记工作区失败');
    } finally {
      setRegistering(false);
    }
  };

  const handleCopy = async () => {
    if (!displayPath) return;
    try {
      await navigator.clipboard.writeText(displayPath);
      message.success('路径已复制');
    } catch {
      message.warning('复制失败，请手动选择路径');
    }
  };

  const previewClass = [
    styles.preview,
    tone === 'ok' ? styles.previewOk : '',
    tone === 'warn' ? styles.previewWarn : '',
    tone === 'error' ? styles.previewError : '',
  ]
    .filter(Boolean)
    .join(' ');

  const iconClass = [
    styles.previewIcon,
    tone === 'ok' ? styles.previewIconOk : '',
    tone === 'warn' ? styles.previewIconWarn : '',
    tone === 'error' ? styles.previewIconError : '',
  ]
    .filter(Boolean)
    .join(' ');

  const badgeClass = [
    styles.badge,
    tone === 'ok' ? styles.badgeOk : '',
    tone === 'warn' ? styles.badgeWarn : '',
    tone === 'error' ? styles.badgeError : '',
  ]
    .filter(Boolean)
    .join(' ');

  const statusClass = [
    styles.status,
    tone === 'ok' ? styles.statusOk : '',
    tone === 'warn' ? styles.statusWarn : '',
    tone === 'error' ? styles.statusError : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={styles.picker} data-testid="workspace-path-picker">
      <div className={previewClass}>
        <div className={iconClass} aria-hidden>
          {validating ? <LoadingOutlined /> : <FolderOpenOutlined />}
        </div>
        <div className={styles.previewBody}>
          <div className={styles.previewTitle}>
            <strong title={folderName}>{folderName}</strong>
            <span className={badgeClass}>
              {validating
                ? '校验中'
                : tone === 'ok'
                  ? isUsingDefault
                    ? '默认'
                    : '可用'
                  : tone === 'warn'
                    ? '需登记'
                    : tone === 'error'
                      ? '不可用'
                      : '待选择'}
            </span>
          </div>
          <div className={styles.previewPath} title={displayPath || undefined}>
            {displayPath ? shortenPath(displayPath, 64) : '选择或输入本地项目目录'}
          </div>
        </div>
        <div className={styles.previewActions}>
          <Tooltip title={displayPath ? '复制完整路径' : '暂无路径'}>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              disabled={!displayPath}
              onClick={() => void handleCopy()}
              aria-label="复制路径"
            />
          </Tooltip>
          <Tooltip title="清空为默认">
            <Button
              type="text"
              size="small"
              icon={<ClearOutlined />}
              disabled={disabled || !value}
              onClick={() => applyPath('')}
              aria-label="清空路径"
            />
          </Tooltip>
        </div>
      </div>

      <div className={styles.actions}>
        <Button
          type="primary"
          className={styles.browseBtn}
          icon={<FolderOpenOutlined />}
          disabled={disabled}
          loading={browsing}
          onClick={() => void handleBrowse()}
          data-testid="workspace-path-browse"
          block
        >
          选择文件夹
        </Button>
        <Tooltip title="手动编辑完整路径">
          <Button
            disabled={disabled}
            onClick={() => {
              const input = document.querySelector<HTMLInputElement>('[data-testid="workspace-path-input"]');
              input?.focus();
              input?.select();
            }}
          >
            手填
          </Button>
        </Tooltip>
      </div>

      {quickPicks.length > 0 ? (
        <div>
          <p className={styles.sectionTitle}>快速选择</p>
          <div className={styles.chips} role="list" aria-label="快速选择工作区">
            {quickPicks.map((item) => {
              const active =
                (value && value === item.path) ||
                (!value && item.kind === 'default') ||
                (validation?.resolved_path === item.path && !value);
              return (
                <button
                  key={`${item.kind}:${item.path}`}
                  type="button"
                  className={`${styles.chip} ${active ? styles.chipActive : ''}`}
                  disabled={disabled}
                  title={item.path}
                  onClick={() => applyPath(item.kind === 'default' ? '' : item.path)}
                >
                  <span className={styles.chipLabel}>
                    {item.kind === 'default' ? '默认' : item.kind === 'recent' ? '最近' : '工作区'} · {item.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className={styles.pathField}>
        <label className={styles.pathLabel} htmlFor="workspace-path-input">
          完整路径
        </label>
        <div className={styles.pathInputRow}>
          <Input
            id="workspace-path-input"
            value={value}
            disabled={disabled}
            placeholder={defaultPath ? `留空 = ${shortenPath(defaultPath, 40)}` : '例如 C:\\projects\\my-app'}
            onChange={(event) => onChange(event.target.value)}
            aria-label="项目路径"
            data-testid="workspace-path-input"
            allowClear={!disabled}
          />
        </div>
      </div>

      <div className={statusClass} data-testid="workspace-path-status">
        <span className={styles.statusIcon} aria-hidden>
          {validating ? (
            <LoadingOutlined />
          ) : tone === 'ok' ? (
            <CheckCircleFilled />
          ) : tone === 'warn' ? (
            <ExclamationCircleFilled />
          ) : tone === 'error' ? (
            <CloseCircleFilled />
          ) : (
            <FolderOpenOutlined />
          )}
        </span>
        <div className={styles.statusBody}>
          <div className={styles.statusText}>{statusMessage}</div>
          {validation?.needs_register && !disabled ? (
            <Button
              type="primary"
              size="small"
              className={styles.registerBtn}
              icon={<PlusOutlined />}
              loading={registering}
              onClick={() => void handleRegister()}
              data-testid="workspace-path-register"
            >
              登记为工作区并使用
            </Button>
          ) : null}
        </div>
      </div>

      {browseError ? (
        <div className={styles.errorText} data-testid="workspace-path-browse-error">
          {browseError}
        </div>
      ) : null}

      {disabled ? (
        <div className={styles.locked} data-testid="workspace-path-locked-hint">
          <LockOutlined />
          <span>
            当前会话已绑定此工作区。路径不会在运行中热切换；若要换目录，请先结束或新建会话后再改。
          </span>
        </div>
      ) : (
        <div className={styles.hint}>
          优先用「选择文件夹」。目录不在允许范围内时，点「登记为工作区」即可加入白名单。
        </div>
      )}
    </div>
  );
}
