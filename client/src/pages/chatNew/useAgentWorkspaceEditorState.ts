import { useCallback, useRef, useState } from 'react';

import type { OpenedFile } from '../../components/chat/AgentWorkspaceEditor';

export function useAgentWorkspaceEditorState() {
  const [openedFiles, setOpenedFiles] = useState<OpenedFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const lastAutoOpenedPartIdRef = useRef<string | null>(null);

  const upsertOpenedFile = useCallback((fileEntry: OpenedFile) => {
    setOpenedFiles((prev) => {
      const existingIdx = prev.findIndex((file) => file.path === fileEntry.path);
      if (existingIdx >= 0) {
        const next = [...prev];
        const existing = next[existingIdx];
        if (existing) {
          next[existingIdx] = {
            ...existing,
            content: fileEntry.content,
            status: fileEntry.status,
            hunks: fileEntry.hunks ?? existing.hunks,
            actionId: fileEntry.actionId ?? existing.actionId,
            original: fileEntry.original ?? existing.original,
            fromDisk: fileEntry.fromDisk ?? existing.fromDisk,
          };
        }
        return next;
      }
      return [...prev, fileEntry];
    });
  }, []);

  const addOpenedFile = useCallback((fileEntry: OpenedFile) => {
    setOpenedFiles((prev) => {
      if (prev.some((file) => file.path === fileEntry.path)) return prev;
      return [...prev, fileEntry];
    });
  }, []);

  const updateOpenedFile = useCallback((filePath: string, updater: (file: OpenedFile) => OpenedFile) => {
    setOpenedFiles((prev) => prev.map((file) => (file.path === filePath ? updater(file) : file)));
  }, []);

  const setOpenedFileOriginal = useCallback((filePath: string, original: string) => {
    updateOpenedFile(filePath, (file) => ({ ...file, original }));
  }, [updateOpenedFile]);

  const focusAutoOpenedPart = useCallback((partId: string | undefined, filePath: string) => {
    if (!partId || lastAutoOpenedPartIdRef.current === partId) return;
    lastAutoOpenedPartIdRef.current = partId;
    setActiveFilePath(filePath);
  }, []);

  const handleAcceptHunk = useCallback((filePath: string, hunkId: string) => {
    updateOpenedFile(filePath, (file) => ({
      ...file,
      hunks: (file.hunks ?? []).map((hunk) => hunk.id === hunkId ? { ...hunk, status: 'accepted' as const } : hunk),
    }));
  }, [updateOpenedFile]);

  const handleRejectHunk = useCallback((filePath: string, hunkId: string) => {
    updateOpenedFile(filePath, (file) => ({
      ...file,
      hunks: (file.hunks ?? []).map((hunk) => hunk.id === hunkId ? { ...hunk, status: 'rejected' as const } : hunk),
    }));
  }, [updateOpenedFile]);

  const handleAcceptAll = useCallback((filePath: string) => {
    updateOpenedFile(filePath, (file) => ({
      ...file,
      hunks: (file.hunks ?? []).map((hunk) => hunk.status === 'pending' ? { ...hunk, status: 'accepted' as const } : hunk),
    }));
  }, [updateOpenedFile]);

  const handleRejectAll = useCallback((filePath: string) => {
    updateOpenedFile(filePath, (file) => ({
      ...file,
      hunks: (file.hunks ?? []).map((hunk) => hunk.status === 'pending' ? { ...hunk, status: 'rejected' as const } : hunk),
    }));
  }, [updateOpenedFile]);

  const handleCloseEditorTab = useCallback((closedPath: string) => {
    setOpenedFiles((prev) => {
      const closedIndex = prev.findIndex((file) => file.path === closedPath);
      const remaining = prev.filter((file) => file.path !== closedPath);
      setActiveFilePath((current) => {
        if (current !== closedPath) return current;
        if (remaining.length === 0) return null;
        return remaining[Math.min(Math.max(closedIndex, 0), remaining.length - 1)]?.path ?? null;
      });
      return remaining;
    });
  }, []);

  return {
    openedFiles,
    activeFilePath,
    setActiveFilePath,
    upsertOpenedFile,
    addOpenedFile,
    setOpenedFileOriginal,
    focusAutoOpenedPart,
    handleAcceptHunk,
    handleRejectHunk,
    handleAcceptAll,
    handleRejectAll,
    handleCloseEditorTab,
  };
}
