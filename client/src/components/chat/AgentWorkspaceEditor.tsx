import Editor, { DiffEditor } from "@monaco-editor/react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "../../theme";
import type { DiffHunk } from "../../utils/diffHunks";
import styles from "./AgentWorkspaceEditor.module.css";

export type { DiffHunk };

export interface OpenedFile {
  path: string;
  name: string;
  content: string;
  original?: string;
  status: "added" | "deleted" | "modified" | "unknown";
  language?: string;
  hunks?: DiffHunk[];
  actionId?: string;
}

export interface AgentWorkspaceEditorProps {
  openedFiles: OpenedFile[];
  activeFilePath: string | null;
  onTabChange: (path: string) => void;
  onTabClose: (path: string) => void;
  onAcceptHunk?: (filePath: string, hunkId: string) => void | Promise<void>;
  onRejectHunk?: (filePath: string, hunkId: string) => void | Promise<void>;
  onAcceptAll?: (filePath: string) => void;
  onRejectAll?: (filePath: string) => void;
}

const EXT_LANGUAGE_MAP: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", css: "css", scss: "scss", less: "less", json: "json",
  md: "markdown", html: "html", htm: "html", yml: "yaml", yaml: "yaml",
  sh: "shell", bash: "shell", rs: "rust", go: "go", java: "java",
  cpp: "cpp", cc: "cpp", cxx: "cpp", c: "c", h: "c", hpp: "cpp",
  kt: "kotlin", rb: "ruby", php: "php", xml: "xml", toml: "toml",
  ini: "ini", txt: "plaintext",
};

const getLanguage = (path: string): string => {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EXT_LANGUAGE_MAP[ext] ?? "plaintext";
};

const STATUS_DOT_COLOR: Record<OpenedFile["status"], string> = {
  added: "#52c41a", deleted: "#ff4d4f", modified: "#1677ff", unknown: "#8c8c8c",
};

const MONACO_OPTIONS = {
  readOnly: true, fontSize: 12, minimap: { enabled: false },
  scrollBeyondLastLine: false, wordWrap: "on" as const,
  lineNumbers: "on" as const, glyphMargin: false, folding: true,
  renderLineHighlight: "none" as const, overviewRulerLanes: 0,
};

const MONACO_DIFF_OPTIONS = { ...MONACO_OPTIONS, renderSideBySide: true, enableSplitViewResizing: true };

const AgentWorkspaceEditor: React.FC<AgentWorkspaceEditorProps> = ({
  openedFiles, activeFilePath, onTabChange, onTabClose,
  onAcceptHunk, onRejectHunk, onAcceptAll, onRejectAll,
}) => {
  const { theme } = useTheme();
  const monacoTheme = theme === "dark" ? "vs-dark" : "light";
  const diffEditorRef = useRef<any>(null);

  const activeFile = useMemo(
    () => openedFiles.find((f) => f.path === activeFilePath) ?? openedFiles[0] ?? null,
    [openedFiles, activeFilePath],
  );
  const showDiff = activeFile?.status === "modified" && typeof activeFile?.original === "string";

  const hunks: DiffHunk[] = activeFile?.hunks ?? [];
  const [currentHunkIdx, setCurrentHunkIdx] = useState(0);
  useEffect(() => { setCurrentHunkIdx(0); }, [activeFile?.path]);

  const currentHunk = hunks[currentHunkIdx] ?? null;
  const pendingCount = useMemo(() => hunks.filter((h) => h.status === "pending").length, [hunks]);
  const acceptedCount = useMemo(() => hunks.filter((h) => h.status === "accepted").length, [hunks]);
  const rejectedCount = useMemo(() => hunks.filter((h) => h.status === "rejected").length, [hunks]);

  /* ── Stable refs for keyboard handler ──────────────────── */
  const onAcceptHunkRef = useRef(onAcceptHunk);
  const onRejectHunkRef = useRef(onRejectHunk);
  const onAcceptAllRef  = useRef(onAcceptAll);
  const onRejectAllRef  = useRef(onRejectAll);
  const currentHunkRef  = useRef(currentHunk);
  const activeFileRef   = useRef(activeFile);
  const hunksLenRef     = useRef(hunks.length);
  useEffect(() => { onAcceptHunkRef.current  = onAcceptHunk; });
  useEffect(() => { onRejectHunkRef.current  = onRejectHunk; });
  useEffect(() => { onAcceptAllRef.current   = onAcceptAll;  });
  useEffect(() => { onRejectAllRef.current   = onRejectAll;  });
  useEffect(() => { currentHunkRef.current   = currentHunk;  });
  useEffect(() => { activeFileRef.current    = activeFile;   });
  useEffect(() => { hunksLenRef.current      = hunks.length; });

  /* ── Global keyboard shortcuts ──────────────────────────── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (document.activeElement as HTMLElement)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      const hk = currentHunkRef.current;
      const af = activeFileRef.current;
      const len = hunksLenRef.current;
      if (e.key === "]") { e.preventDefault(); if (len > 0) setCurrentHunkIdx((i) => Math.min(i + 1, len - 1)); }
      else if (e.key === "[") { e.preventDefault(); if (len > 0) setCurrentHunkIdx((i) => Math.max(i - 1, 0)); }
      else if (e.key === "a" && hk?.status === "pending" && af) { onAcceptHunkRef.current?.(af.path, hk.id); }
      else if (e.key === "r" && hk?.status === "pending" && af) { onRejectHunkRef.current?.(af.path, hk.id); }
      else if (e.key === "A" && af && len > 0) { onAcceptAllRef.current?.(af.path); }
      else if (e.key === "R" && af && len > 0) { onRejectAllRef.current?.(af.path); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  /* ── Scroll DiffEditor to current hunk line ─────────────── */
  useEffect(() => {
    if (!diffEditorRef.current || !currentHunk) return;
    try { diffEditorRef.current.getModifiedEditor?.()?.revealLineInCenter(currentHunk.newStart); }
    catch { /* not yet ready */ }
  }, [currentHunk]);

  const handleDiffEditorMount = useCallback((editor: any) => { diffEditorRef.current = editor; }, []);

  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string) => { if (e.key === "Enter" || e.key === " ") onTabChange(path); },
    [onTabChange],
  );
  const handleCloseKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string) => {
      if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); onTabClose(path); }
    },
    [onTabClose],
  );

  return (
    <div className={styles.editorWrap}>
      {/* ── Tab bar ────────────────────────────────────────── */}
      <div className={styles.tabBar} role="tablist" aria-label="已打开的文件">
        {openedFiles.map((file) => {
          const isActive = file.path === activeFile?.path;
          const hasPending = file.hunks?.some((h) => h.status === "pending") ?? false;
          return (
            <div key={file.path} role="tab" aria-selected={isActive} tabIndex={isActive ? 0 : -1}
              className={`${styles.tab} ${isActive ? styles.tabActive : ""}`}
              onClick={() => onTabChange(file.path)}
              onKeyDown={(e) => handleTabKeyDown(e, file.path)}
            >
              <span className={styles.tabDot} style={{ background: STATUS_DOT_COLOR[file.status] }} aria-hidden="true" />
              <span className={styles.tabName} title={file.path}>{file.name}</span>
              {hasPending && <span className={styles.tabPendingDot} title="有待确认的 hunk" aria-hidden="true" />}
              <span className={styles.tabClose} role="button" aria-label={`关闭 ${file.name}`} tabIndex={-1}
                onClick={(e) => { e.stopPropagation(); onTabClose(file.path); }}
                onKeyDown={(e) => handleCloseKeyDown(e, file.path)}
              >×</span>
            </div>
          );
        })}
      </div>

      {/* ── Review toolbar ─────────────────────────────────── */}
      <div className={styles.reviewToolbar}>
        <div className={styles.reviewMeta}>
          <span className={styles.reviewKicker}>AI Code Review</span>
          <span className={styles.reviewTitle}>{activeFile ? activeFile.path : "等待选择变更文件"}</span>
        </div>
        <div className={styles.reviewRight}>
          {hunks.length > 0 && (
            <div className={styles.reviewStats}>
              {pendingCount > 0 && <span className={styles.statPending}>{pendingCount} pending</span>}
              {acceptedCount > 0 && <span className={styles.statAccepted}>✓ {acceptedCount}</span>}
              {rejectedCount > 0 && <span className={styles.statRejected}>✗ {rejectedCount}</span>}
            </div>
          )}
          {pendingCount > 0 && activeFile && (
            <div className={styles.reviewBulkActions}>
              <button type="button" className={`${styles.bulkBtn} ${styles.bulkAcceptBtn}`}
                onClick={() => onAcceptAll?.(activeFile.path)} aria-label="接受全部 hunk" title="Accept All (Shift+A)">
                ✓ All
              </button>
              <button type="button" className={`${styles.bulkBtn} ${styles.bulkRejectBtn}`}
                onClick={() => onRejectAll?.(activeFile.path)} aria-label="拒绝全部 hunk" title="Reject All (Shift+R)">
                ✗ All
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Hunk navigator ─────────────────────────────────── */}
      {hunks.length > 0 && (
        <div className={styles.hunkNav} role="toolbar" aria-label="Hunk 导航">
          <div className={styles.hunkNavLeft}>
            <span className={styles.hunkNavCounter}>Hunk {currentHunkIdx + 1} / {hunks.length}</span>
            {currentHunk && (
              <span className={styles.hunkNavStatus} data-status={currentHunk.status}>{currentHunk.status}</span>
            )}
            <span className={styles.hunkNavHints}>[/] navigate · a/r accept/reject · A/R all</span>
          </div>
          <div className={styles.hunkNavActions}>
            <button type="button" className={styles.hunkNavBtn}
              disabled={currentHunkIdx === 0} onClick={() => setCurrentHunkIdx((i) => i - 1)} aria-label="上一个 hunk"
            >‹ Prev <kbd className={styles.kbdHint}>[</kbd></button>
            <button type="button" className={styles.hunkNavBtn}
              disabled={currentHunkIdx >= hunks.length - 1} onClick={() => setCurrentHunkIdx((i) => i + 1)} aria-label="下一个 hunk"
            >Next › <kbd className={styles.kbdHint}>]</kbd></button>
            <span className={styles.hunkNavSep} />
            <button type="button" className={`${styles.hunkNavBtn} ${styles.hunkAcceptBtn}`}
              disabled={!currentHunk || currentHunk.status !== "pending"}
              onClick={() => currentHunk && onAcceptHunk?.(activeFile!.path, currentHunk.id)} aria-label="接受当前 hunk"
            >✓ Accept <kbd className={styles.kbdHint}>a</kbd></button>
            <button type="button" className={`${styles.hunkNavBtn} ${styles.hunkRejectBtn}`}
              disabled={!currentHunk || currentHunk.status !== "pending"}
              onClick={() => currentHunk && onRejectHunk?.(activeFile!.path, currentHunk.id)} aria-label="拒绝当前 hunk"
            >✗ Reject <kbd className={styles.kbdHint}>r</kbd></button>
          </div>
        </div>
      )}

      {/* ── Editor area ────────────────────────────────────── */}
      {!activeFile ? (
        <div className={styles.emptyState} aria-label="编辑器空状态">
          <svg className={styles.emptyIcon} viewBox="0 0 48 48" fill="none" aria-hidden="true">
            <rect x="6" y="6" width="36" height="36" rx="4" stroke="currentColor" strokeWidth="2" strokeOpacity=".35" />
            <path d="M16 18l8 6-8 6M27 30h6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" strokeOpacity=".55" />
          </svg>
          <span className={styles.emptyTitle}>暂无打开的文件</span>
          <span className={styles.emptyHint}>点击左侧文件树中的变更文件即可在此查看代码</span>
        </div>
      ) : showDiff ? (
        <div className={styles.monacoWrap}>
          <DiffEditor height="100%" original={activeFile.original} modified={activeFile.content}
            language={activeFile.language ?? getLanguage(activeFile.path)}
            theme={monacoTheme} options={MONACO_DIFF_OPTIONS} onMount={handleDiffEditorMount} />
        </div>
      ) : (
        <div className={styles.monacoWrap}>
          <Editor height="100%" value={activeFile.content ?? ""}
            language={activeFile.language ?? getLanguage(activeFile.path)}
            theme={monacoTheme} options={MONACO_OPTIONS} />
        </div>
      )}
    </div>
  );
};

export default AgentWorkspaceEditor;