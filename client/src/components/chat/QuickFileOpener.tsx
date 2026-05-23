import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getFileIcon, isTextIcon } from '../../utils/fileIcons';
import type { WorkspaceTreeNode } from '../../services/api';
import styles from './QuickFileOpener.module.css';

export interface QuickFileOpenerProps {
  open: boolean;
  onClose: () => void;
  /** Flat list of workspace tree nodes (files only) */
  nodes: WorkspaceTreeNode[];
  /** Root path of the workspace */
  rootPath?: string;
  /** Called when user selects a file */
  onSelectFile: (node: WorkspaceTreeNode) => void;
  /** Recently opened file paths for default display */
  recentPaths?: string[];
}

/** Flatten a tree of nodes into a list of file nodes only */
export function flattenFileNodes(nodes: WorkspaceTreeNode[]): WorkspaceTreeNode[] {
  const result: WorkspaceTreeNode[] = [];
  const walk = (list: WorkspaceTreeNode[]) => {
    for (const node of list) {
      if (node.kind === 'file') result.push(node);
      if (node.children) walk(node.children);
    }
  };
  walk(nodes);
  return result;
}

/** Score and highlight a string against a query (simple fuzzy) */
function fuzzyMatch(
  text: string,
  query: string,
): { score: number; highlights: boolean[] } | null {
  if (!query) return { score: 0, highlights: Array(text.length).fill(false) };
  const lText = text.toLowerCase();
  const lQuery = query.toLowerCase();
  const highlights = Array(text.length).fill(false);
  let qi = 0;
  let score = 0;
  let consecutive = 0;
  for (let i = 0; i < lText.length && qi < lQuery.length; i++) {
    if (lText[i] === lQuery[qi]) {
      highlights[i] = true;
      score += 1 + consecutive * 2;
      consecutive++;
      qi++;
    } else {
      consecutive = 0;
    }
  }
  if (qi < lQuery.length) return null; // didn't match all chars
  return { score, highlights };
}

const QuickFileOpener: React.FC<QuickFileOpenerProps> = ({
  open,
  onClose,
  nodes,
  rootPath = '',
  onSelectFile,
  recentPaths = [],
}) => {
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Flatten all file nodes once
  const allFiles = useMemo(() => flattenFileNodes(nodes), [nodes]);

  // Filter and score
  const results = useMemo(() => {
    if (!query.trim()) {
      // Show recent files when no query
      if (recentPaths.length > 0) {
        const recentSet = new Set(recentPaths);
        const recents = allFiles.filter((n) => recentSet.has(n.path));
        const rest = allFiles.filter((n) => !recentSet.has(n.path)).slice(0, 20 - recents.length);
        return [...recents, ...rest].slice(0, 20).map((n) => ({
          node: n,
          highlights: Array(n.name.length).fill(false),
          score: recentPaths.indexOf(n.path) >= 0 ? 1000 : 0,
          isRecent: recentSet.has(n.path),
        }));
      }
      return allFiles.slice(0, 20).map((n) => ({
        node: n,
        highlights: Array(n.name.length).fill(false),
        score: 0,
        isRecent: false,
      }));
    }

    const q = query.trim();
    const matched: { node: WorkspaceTreeNode; highlights: boolean[]; score: number; isRecent: boolean }[] = [];

    for (const node of allFiles) {
      // Match against full path for better results
      const nameMatch = fuzzyMatch(node.name, q);
      const pathMatch = fuzzyMatch(node.path, q);
      if (!nameMatch && !pathMatch) continue;

      const best = nameMatch && pathMatch
        ? (nameMatch.score >= pathMatch.score ? nameMatch : { ...pathMatch, highlights: Array(node.name.length).fill(false) })
        : (nameMatch ?? { ...pathMatch!, highlights: Array(node.name.length).fill(false) });

      matched.push({
        node,
        highlights: nameMatch?.highlights ?? Array(node.name.length).fill(false),
        score: best.score,
        isRecent: recentPaths.includes(node.path),
      });
    }

    return matched.sort((a, b) => b.score - a.score).slice(0, 50);
  }, [query, allFiles, recentPaths]);

  // Reset selection when results change
  useEffect(() => setActiveIdx(0), [results]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Scroll active item into view
  useEffect(() => {
    const item = listRef.current?.querySelector(`[data-idx="${activeIdx}"]`);
    item?.scrollIntoView({ block: 'nearest' });
  }, [activeIdx]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = results[activeIdx];
      if (item) { onSelectFile(item.node); onClose(); }
    } else if (e.key === 'Escape') {
      onClose();
    }
  }, [results, activeIdx, onSelectFile, onClose]);

  const renderHighlighted = (text: string, highlights: boolean[]) => {
    const parts: React.ReactNode[] = [];
    let i = 0;
    while (i < text.length) {
      if (highlights[i]) {
        let j = i;
        while (j < text.length && highlights[j]) j++;
        parts.push(<mark key={i} className={styles.highlight}>{text.slice(i, j)}</mark>);
        i = j;
      } else {
        let j = i;
        while (j < text.length && !highlights[j]) j++;
        parts.push(<span key={i}>{text.slice(i, j)}</span>);
        i = j;
      }
    }
    return parts;
  };

  if (!open) return null;

  const relPath = (node: WorkspaceTreeNode) => {
    const p = node.path.replace(/\\/g, '/');
    const root = rootPath.replace(/\\/g, '/');
    return root && p.startsWith(root) ? p.slice(root.length).replace(/^\//, '') : p;
  };

  return (
    <div className={styles.overlay} onClick={onClose} role="dialog" aria-modal="true" aria-label="快速文件搜索">
      <div className={styles.panel} onClick={(e) => e.stopPropagation()}>
        {/* Search input */}
        <div className={styles.inputRow}>
          <span className={styles.searchIcon} aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            placeholder="搜索文件… (Ctrl+P)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            autoComplete="off"
            spellCheck={false}
            aria-autocomplete="list"
            aria-controls="qfo-list"
            aria-activedescendant={`qfo-item-${activeIdx}`}
          />
          <kbd className={styles.escHint}>Esc</kbd>
        </div>

        {/* Results */}
        <div ref={listRef} id="qfo-list" className={styles.list} role="listbox">
          {results.length === 0 ? (
            <div className={styles.empty}>
              {allFiles.length === 0
                ? '请先在工作区面板加载文件树'
                : `未找到匹配 "${query}" 的文件`}
            </div>
          ) : (
            results.map((item, idx) => {
              const icon = getFileIcon(item.node.name);
              const isText = isTextIcon(icon.icon);
              const path = relPath(item.node);
              const pathDir = path.includes('/')
                ? path.split('/').slice(0, -1).join(' › ')
                : '';

              return (
                <div
                  key={item.node.path}
                  id={`qfo-item-${idx}`}
                  data-idx={idx}
                  role="option"
                  aria-selected={idx === activeIdx}
                  className={`${styles.item} ${idx === activeIdx ? styles.itemActive : ''}`}
                  onMouseEnter={() => setActiveIdx(idx)}
                  onClick={() => { onSelectFile(item.node); onClose(); }}
                >
                  {/* File icon */}
                  <span
                    className={isText ? styles.iconBadge : styles.iconEmoji}
                    style={{ ['--icon-color' as any]: icon.color }}
                    aria-hidden="true"
                  >
                    {icon.icon}
                  </span>

                  {/* File name with highlights */}
                  <span className={styles.fileName}>
                    {renderHighlighted(item.node.name, item.highlights)}
                  </span>

                  {/* Path dir */}
                  {pathDir && (
                    <span className={styles.filePath}>{pathDir}</span>
                  )}

                  {/* Recent badge */}
                  {item.isRecent && (
                    <span className={styles.recentBadge}>最近</span>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer hint */}
        <div className={styles.footer}>
          <span><kbd className={styles.kbd}>↑↓</kbd> 导航</span>
          <span><kbd className={styles.kbd}>↵</kbd> 打开</span>
          <span><kbd className={styles.kbd}>Esc</kbd> 关闭</span>
          <span className={styles.footerRight}>{results.length} 个结果</span>
        </div>
      </div>
    </div>
  );
};

export default QuickFileOpener;
