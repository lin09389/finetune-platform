import Editor, { DiffEditor } from "@monaco-editor/react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "../../theme";
import type { DiffHunk } from "../../utils/diffHunks";
import { getFileIcon, isTextIcon } from "../../utils/fileIcons";
import type { ActiveFileContext } from "../../services/api";
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
  /** Whether the file was loaded from disk (user-browsed) vs. an agent artifact */
  fromDisk?: boolean;
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
  /** Called when user saves a file (Ctrl+S or save button). Receives path and new content. */
  onSave?: (filePath: string, content: string) => void | Promise<void>;
  /** Active agent terminal_id, if any – shows terminal toggle hint in toolbar */
  activeTerminalId?: string | null;
  /** Called when user clicks the terminal toggle button */
  onToggleTerminal?: () => void;
  terminalOpen?: boolean;
  /** Workspace root absolute path */
  workspaceRoot?: string;
  /** Callback when a breadcrumb segment is clicked */
  onBreadcrumbClick?: (segment: string, fullPath: string) => void;
  onActiveContextChange?: (context: ActiveFileContext | null) => void;
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



const MONACO_READONLY_OPTIONS = {
  readOnly: true, fontSize: 13, minimap: { enabled: false },
  scrollBeyondLastLine: false, wordWrap: "on" as const,
  lineNumbers: "on" as const, glyphMargin: false, folding: true,
  renderLineHighlight: "none" as const, overviewRulerLanes: 0,
  fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", Consolas, monospace',
  fontLigatures: true,
};

const MONACO_EDITABLE_OPTIONS = {
  ...MONACO_READONLY_OPTIONS,
  readOnly: false,
  cursorBlinking: "smooth" as const,
  suggestOnTriggerCharacters: true,
  quickSuggestions: true,
  renderLineHighlight: "line" as const,
};

const MONACO_DIFF_OPTIONS = { ...MONACO_READONLY_OPTIONS, renderSideBySide: true, enableSplitViewResizing: true };

const AgentWorkspaceEditor: React.FC<AgentWorkspaceEditorProps> = ({
  openedFiles, activeFilePath, onTabChange, onTabClose,
  onAcceptHunk, onRejectHunk, onAcceptAll, onRejectAll,
  onSave, onToggleTerminal, terminalOpen, activeTerminalId,
  workspaceRoot, onBreadcrumbClick, onActiveContextChange,
}) => {
  const { theme } = useTheme();
  const monacoTheme = theme === "dark" ? "vs-dark" : "light";
  const diffEditorRef = useRef<any>(null);
  const editorRef = useRef<any>(null);
  const [cursorPos, setCursorPos] = useState({ line: 1, col: 1 });

  const activeFile = useMemo(
    () => openedFiles.find((f) => f.path === activeFilePath) ?? openedFiles[0] ?? null,
    [openedFiles, activeFilePath],
  );
  const showDiff = activeFile?.status === "modified" && typeof activeFile?.original === "string";

  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string } | null>(null);
  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);


  // In diff-review mode the editor is always read-only; for normal files allow editing
  const isEditableMode = Boolean(activeFile && !showDiff);

  const handleEditorMount = useCallback((editor: any) => {
    editorRef.current = editor;
    const emitContext = () => {
      const file = activeFileRef.current;
      if (!file) {
        onActiveContextChange?.(null);
        return;
      }
      const position = editor.getPosition?.();
      const selection = editor.getSelection?.();
      const model = editor.getModel?.();
      const selectedText = selection && model ? model.getValueInRange(selection) : "";
      const content = model?.getValue?.() ?? file.content ?? "";
      onActiveContextChange?.({
        file_path: file.path,
        language: file.language ?? getLanguage(file.path),
        cursor: {
          line: position?.lineNumber || 1,
          column: position?.column || 1,
        },
        selection: selection && selectedText
          ? {
              start_line: selection.startLineNumber,
              start_column: selection.startColumn,
              end_line: selection.endLineNumber,
              end_column: selection.endColumn,
              text: selectedText.slice(0, 4000),
            }
          : null,
        content_preview: content.slice(0, 4000),
        updated_at: new Date().toISOString(),
      });
    };
    editor.onDidChangeCursorPosition((e: any) => {
      setCursorPos({ line: e.position.lineNumber, col: e.position.column });
      emitContext();
    });
    editor.onDidChangeCursorSelection(emitContext);
    emitContext();
  }, [onActiveContextChange]);

  const breadcrumbs = useMemo(() => {
    if (!activeFile) return [];
    let path = activeFile.path.replace(/\\/g, '/');
    if (workspaceRoot) {
      const root = workspaceRoot.replace(/\\/g, '/');
      if (path.startsWith(root)) {
        path = path.slice(root.length).replace(/^\//, '');
      }
    }
    return path.split('/').filter(Boolean);
  }, [activeFile, workspaceRoot]);

  const handleBreadcrumbClick = useCallback((index: number) => {
    if (!activeFile || !onBreadcrumbClick) return;
    let path = activeFile.path.replace(/\\/g, '/');
    let isRelative = false;
    if (workspaceRoot) {
      const root = workspaceRoot.replace(/\\/g, '/');
      if (path.startsWith(root)) {
        path = path.slice(root.length).replace(/^\//, '');
        isRelative = true;
      }
    }
    const parts = path.split('/').filter(Boolean);
    const subParts = parts.slice(0, index + 1);
    const cumulativePath = isRelative && workspaceRoot
      ? `${workspaceRoot}/${subParts.join('/')}`.replace(/\\/g, '/')
      : subParts.join('/');

    onBreadcrumbClick(parts[index]!, cumulativePath);
  }, [activeFile, workspaceRoot, onBreadcrumbClick]);

  useEffect(() => {
    setCursorPos({ line: 1, col: 1 });
    if (!activeFile) {
      onActiveContextChange?.(null);
      return;
    }
    onActiveContextChange?.({
      file_path: activeFile.path,
      language: activeFile.language ?? getLanguage(activeFile.path),
      cursor: { line: 1, column: 1 },
      selection: null,
      content_preview: (activeFile.content ?? "").slice(0, 4000),
      updated_at: new Date().toISOString(),
    });
  }, [activeFile, activeFilePath, onActiveContextChange]);

  // Track dirty (unsaved) content for the active file
  const [dirtyContent, setDirtyContent] = useState<Record<string, string>>({});
  const [savingPath, setSavingPath] = useState<string | null>(null);
  const savingPathRef = useRef<string | null>(null);

  // Reset dirty state when active file changes
  useEffect(() => {
    // no-op: dirty content persists per path until saved or tab closed
  }, [activeFile?.path]);

  const currentContent = activeFile
    ? (dirtyContent[activeFile.path] ?? activeFile.content ?? "")
    : "";

  const isDirty = activeFile ? (activeFile.path in dirtyContent) : false;

  const handleEditorChange = useCallback((value: string | undefined) => {
    if (!activeFile) return;
    setDirtyContent((prev) => ({ ...prev, [activeFile.path]: value ?? "" }));
  }, [activeFile]);

  const handleSave = useCallback(async () => {
    if (!activeFile || !onSave) return;
    if (savingPathRef.current === activeFile.path) return;
    const content = dirtyContent[activeFile.path] ?? activeFile.content ?? "";
    setSavingPath(activeFile.path);
    savingPathRef.current = activeFile.path;
    try {
      await onSave(activeFile.path, content);
      // Clear dirty state after successful save
      setDirtyContent((prev) => {
        const next = { ...prev };
        delete next[activeFile.path];
        return next;
      });
    } finally {
      setSavingPath(null);
      savingPathRef.current = null;
    }
  }, [activeFile, dirtyContent, onSave]);

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
  const onSaveRef       = useRef(onSave);
  const currentHunkRef  = useRef(currentHunk);
  const activeFileRef   = useRef(activeFile);
  const hunksLenRef     = useRef(hunks.length);
  const isEditableModeRef = useRef(isEditableMode);
  useEffect(() => { onAcceptHunkRef.current  = onAcceptHunk; });
  useEffect(() => { onRejectHunkRef.current  = onRejectHunk; });
  useEffect(() => { onAcceptAllRef.current   = onAcceptAll;  });
  useEffect(() => { onRejectAllRef.current   = onRejectAll;  });
  useEffect(() => { onSaveRef.current        = onSave;       });
  useEffect(() => { currentHunkRef.current   = currentHunk;  });
  useEffect(() => { activeFileRef.current    = activeFile;   });
  useEffect(() => { hunksLenRef.current      = hunks.length; });
  useEffect(() => { isEditableModeRef.current = isEditableMode; });

  /* ── Global keyboard shortcuts ──────────────────────────── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+S / Cmd+S → save
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        const af = activeFileRef.current;
        if (af && onSaveRef.current && isEditableModeRef.current) {
          void handleSave();
        }
        return;
      }
      const tag = (document.activeElement as HTMLElement)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;

      const hk = currentHunkRef.current;
      const af = activeFileRef.current;
      const len = hunksLenRef.current;
      const key = e.key.toLowerCase();

      // Use Alt key for IDE shortcuts to prevent clashes
      if (e.altKey) {
        if (e.key === "ArrowDown") { e.preventDefault(); if (len > 0) setCurrentHunkIdx((i) => Math.min(i + 1, len - 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); if (len > 0) setCurrentHunkIdx((i) => Math.max(i - 1, 0)); }
        else if (key === "a" && hk?.status === "pending" && af) {
          e.preventDefault();
          if (e.shiftKey) { onAcceptAllRef.current?.(af.path); }
          else { onAcceptHunkRef.current?.(af.path, hk.id); }
        }
        else if (key === "r" && hk?.status === "pending" && af) {
          e.preventDefault();
          if (e.shiftKey) { onRejectAllRef.current?.(af.path); }
          else { onRejectHunkRef.current?.(af.path, hk.id); }
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handleSave]);

  /* ── Scroll DiffEditor to current hunk line ─────────────── */
  useEffect(() => {
    if (!diffEditorRef.current || !currentHunk) return;
    try { diffEditorRef.current.getModifiedEditor?.()?.revealLineInCenter(currentHunk.newStart); }
    catch { /* not yet ready */ }
  }, [currentHunk]);

  const handleDiffEditorMount = useCallback((editor: any) => { diffEditorRef.current = editor; }, []);

  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string, index: number) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onTabChange(path);
      } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        const nextTab = document.getElementById(`agent-tab-${index + 1}`);
        if (nextTab) nextTab.focus();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        const prevTab = document.getElementById(`agent-tab-${index - 1}`);
        if (prevTab) prevTab.focus();
      }
    },
    [onTabChange],
  );
  const handleCloseKeyDown = useCallback(
    (e: React.KeyboardEvent, path: string) => {
      if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); onTabClose(path); }
    },
    [onTabClose],
  );

  const language = activeFile ? (activeFile.language ?? getLanguage(activeFile.path)) : "plaintext";

  const hunksProgress = useMemo(() => {
    if (hunks.length === 0) return null;
    return `✓${acceptedCount} ✗${rejectedCount} pending${pendingCount}`;
  }, [hunks.length, acceptedCount, rejectedCount, pendingCount]);

  return (
    <div className={styles.editorWrap}>
      {/* ── Tab bar ────────────────────────────────────────── */}
      <div className={styles.tabBar} role="tablist" aria-label="已打开的文件">
        {openedFiles.map((file, index) => {
          const isActive = file.path === activeFile?.path;
          const hasPending = file.hunks?.some((h) => h.status === "pending") ?? false;
          const fileIsDirty = file.path in dirtyContent;
          const icon = getFileIcon(file.name);
          const isText = isTextIcon(icon.icon);
          return (
            <div key={file.path} id={`agent-tab-${index}`} role="tab" aria-selected={isActive} tabIndex={isActive ? 0 : -1}
              className={`${styles.tab} ${isActive ? styles.tabActive : ""}`}
              onClick={() => onTabChange(file.path)}
              onKeyDown={(e) => handleTabKeyDown(e, file.path, index)}
              onContextMenu={(e) => {
                e.preventDefault();
                setContextMenu({ x: e.clientX, y: e.clientY, path: file.path });
              }}
            >
              <span
                className={isText ? styles.iconBadge : styles.iconEmoji}
                style={{ ['--icon-color' as any]: icon.color }}
                aria-hidden="true"
              >
                {icon.icon}
              </span>
              <span className={styles.tabName} title={file.path}>{file.name}</span>
              {hasPending && <span className={styles.tabPendingDot} title="有待确认时的 hunk" aria-hidden="true" />}
              {fileIsDirty && <span className={styles.tabDirtyDot} title="未保存修改" aria-hidden="true" />}
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
          <span className={styles.reviewKicker}>
            {showDiff ? "AI Code Review" : isEditableMode ? "Editor" : "Preview"}
          </span>
          <span className={styles.reviewTitle}>{activeFile ? activeFile.path : "等待选择变更文件"}</span>
        </div>
        <div className={styles.reviewRight}>
          {/* Editable mode indicator */}
          {isEditableMode && (
            <span className={`${styles.modeIndicator} ${isDirty ? styles.modeIndicatorDirty : styles.modeIndicatorClean}`}>
              {isDirty ? "● 未保存" : "✓ 已保存"}
            </span>
          )}
          {showDiff && (
            <span className={styles.modeIndicatorReview}>REVIEW MODE</span>
          )}
          {/* Review stats */}
          {hunks.length > 0 && (
            <div className={styles.reviewStats}>
              {pendingCount > 0 && <span className={styles.statPending}>{pendingCount} pending</span>}
              {acceptedCount > 0 && <span className={styles.statAccepted}>✓ {acceptedCount}</span>}
              {rejectedCount > 0 && <span className={styles.statRejected}>✗ {rejectedCount}</span>}
            </div>
          )}
          {/* Save button */}
          {isEditableMode && onSave && isDirty && (
            <button
              type="button"
              className={`${styles.bulkBtn} ${styles.saveBtn}`}
              onClick={() => void handleSave()}
              disabled={savingPath === activeFile?.path}
              title="保存文件 (Ctrl+S)"
              aria-label="保存文件"
            >
              {savingPath === activeFile?.path ? "保存中..." : "↓ 保存"}
            </button>
          )}
          {pendingCount > 0 && activeFile && (
            <div className={styles.reviewBulkActions}>
              <button type="button" className={`${styles.bulkBtn} ${styles.bulkAcceptBtn}`}
                onClick={() => onAcceptAll?.(activeFile.path)} aria-label="接受全部 hunk" title="Accept All (Alt+Shift+A)">
                ✓ All
              </button>
              <button type="button" className={`${styles.bulkBtn} ${styles.bulkRejectBtn}`}
                onClick={() => onRejectAll?.(activeFile.path)} aria-label="拒绝全部 hunk" title="Reject All (Alt+Shift+R)">
                ✗ All
              </button>
            </div>
          )}
          {/* Terminal toggle */}
          {(activeTerminalId || onToggleTerminal) && (
            <button
              type="button"
              className={`${styles.bulkBtn} ${terminalOpen ? styles.terminalBtnActive : styles.terminalBtn}`}
              onClick={onToggleTerminal}
              title={terminalOpen ? "隐藏终端" : "显示终端"}
              aria-label={terminalOpen ? "隐藏终端" : "显示终端"}
            >
              {terminalOpen ? "▽ 终端" : "▷ 终端"}
            </button>
          )}
        </div>
      </div>

      {/* ── Breadcrumb path ────────────────────────────────── */}
      {activeFile && (
        <div className={styles.breadcrumb} role="navigation" aria-label="文件路径面包屑">
          <span className={styles.breadcrumbRootIcon}>📁</span>
          {breadcrumbs.map((segment, index) => {
            const isLast = index === breadcrumbs.length - 1;
            return (
              <React.Fragment key={index}>
                {index > 0 && <span className={styles.breadcrumbSep}>/</span>}
                <button
                  type="button"
                  className={`${styles.breadcrumbSeg} ${isLast ? styles.breadcrumbSegLast : ""}`}
                  disabled={isLast || !onBreadcrumbClick}
                  onClick={() => handleBreadcrumbClick(index)}
                >
                  {segment}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      )}

      {/* ── Hunk navigator ─────────────────────────────────── */}
      {hunks.length > 0 && (
        <div className={styles.hunkNav} role="toolbar" aria-label="Hunk 导航">
          <div className={styles.hunkNavLeft}>
            <span className={styles.hunkNavCounter}>Hunk {currentHunkIdx + 1} / {hunks.length}</span>
            {currentHunk && (
              <span className={styles.hunkNavStatus} data-status={currentHunk.status}>{currentHunk.status}</span>
            )}
            <span className={styles.hunkNavHints}>Alt+↑/↓ navigate · Alt+A/R accept/reject · Alt+Shift+A/R all</span>
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
            >✓ Accept <kbd className={styles.kbdHint}>Alt+A</kbd></button>
            <button type="button" className={`${styles.hunkNavBtn} ${styles.hunkRejectBtn}`}
              disabled={!currentHunk || currentHunk.status !== "pending"}
              onClick={() => currentHunk && onRejectHunk?.(activeFile!.path, currentHunk.id)} aria-label="拒绝当前 hunk"
            >✗ Reject <kbd className={styles.kbdHint}>Alt+R</kbd></button>
          </div>
        </div>
      )}

      {/* ── Context Menu ───────────────────────────────────── */}
      {contextMenu && (
        <ul
          className={styles.contextMenu}
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <li onClick={() => { onTabClose(contextMenu.path); setContextMenu(null); }}>关闭当前</li>
          <li onClick={() => {
            openedFiles.forEach(f => {
              if (f.path !== contextMenu.path) onTabClose(f.path);
            });
            setContextMenu(null);
          }}>关闭其他</li>
          <li onClick={() => {
            openedFiles.forEach(f => onTabClose(f.path));
            setContextMenu(null);
          }}>关闭所有</li>
        </ul>
      )}

      {/* ── Editor area ────────────────────────────────────── */}
      {!activeFile ? (
        <div className={styles.emptyState} aria-label="编辑器空状态">
          <div className={styles.emptyStateContainer}>
            <div className={styles.emptyIllustration} aria-hidden="true">
              <div className={styles.emptyIllustrationHeader}>
                <div className={styles.emptyIllustrationDot} />
                <div className={styles.emptyIllustrationDot} />
                <div className={styles.emptyIllustrationDot} />
              </div>
              <div className={styles.emptyIllustrationLines}>
                <div className={styles.emptyIllustrationLine} />
                <div className={styles.emptyIllustrationLine} />
                <div className={styles.emptyIllustrationLine} />
                <div className={styles.emptyIllustrationLine} />
                <div className={styles.emptyIllustrationLine} />
              </div>
              <div className={styles.emptyIllustrationCursor} />
            </div>
            <h3 className={styles.emptyTitle}>暂无打开的文件</h3>
            <p className={styles.emptyHint}>
              点击左侧文件树中的文件，或等 AI Agent 自动生成补丁文件以在此查看与编辑代码。
            </p>
          </div>
        </div>
      ) : showDiff ? (
        <div className={styles.monacoWrap}>
          <DiffEditor height="100%" original={activeFile.original} modified={activeFile.content}
            language={activeFile.language ?? getLanguage(activeFile.path)}
            theme={monacoTheme} options={MONACO_DIFF_OPTIONS} onMount={handleDiffEditorMount} />
        </div>
      ) : (
        <div className={styles.monacoWrap}>
          <Editor
            height="100%"
            value={currentContent}
            language={activeFile.language ?? getLanguage(activeFile.path)}
            theme={monacoTheme}
            options={isEditableMode ? MONACO_EDITABLE_OPTIONS : MONACO_READONLY_OPTIONS}
            onChange={handleEditorChange}
            onMount={handleEditorMount}
          />
        </div>
      )}

      {/* ── Status Bar ──────────────────────────────────────── */}
      {activeFile && (
        <div className={styles.statusBar}>
          <div className={styles.statusBarLeft}>
            <span className={styles.statusBarItem} title="光标位置">
              Ln {cursorPos.line}, Col {cursorPos.col}
            </span>
            <span className={styles.statusBarSep} />
            <span className={styles.statusBarItem} title="文件编码">
              UTF-8
            </span>
            <span className={styles.statusBarSep} />
            <span className={styles.statusBarItem} title="行尾符">
              LF
            </span>
            <span className={styles.statusBarSep} />
            <span className={styles.statusBarItem} style={{ textTransform: "uppercase" }} title="语言">
              {language}
            </span>
          </div>
          <div className={styles.statusBarRight}>
            {hunksProgress && (
              <span className={styles.statusBarItem} title="Review Hunk 进度">
                Hunks: {hunksProgress}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentWorkspaceEditor;
