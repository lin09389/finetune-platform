import { useCallback, useEffect, useMemo, useState } from 'react';

import type { AgentArtifact } from '../../services/api';

export type AgentFileSummary = AgentArtifact & { depth: number };

export type AgentFileTreeNode = {
  name: string;
  path: string;
  kind: 'folder' | 'file';
  children: AgentFileTreeNode[];
  file?: AgentFileSummary;
};

export function useAgentFileTree(artifacts: AgentArtifact[] | undefined) {
  const agentFileSummaries = useMemo(() => {
    const depthOf = (path: string) => path.replace(/\\/g, '/').split('/').filter(Boolean).length;
    return (artifacts || [])
      .map((artifact) => ({ ...artifact, depth: depthOf(artifact.path) }))
      .slice(-12)
      .sort((a, b) => a.depth - b.depth || a.path.localeCompare(b.path));
  }, [artifacts]);

  const agentFileTree = useMemo(() => {
    const root: AgentFileTreeNode = { name: '', path: '', kind: 'folder', children: [] };

    const insert = (
      node: AgentFileTreeNode,
      segments: string[],
      file: AgentFileSummary,
      fullPath: string,
    ): void => {
      if (segments.length === 0) {
        node.children.push({ name: file.path.split('/').pop() || file.path, path: fullPath, kind: 'file', children: [], file });
        return;
      }
      const head = segments[0];
      if (!head) {
        node.children.push({ name: file.path.split('/').pop() || file.path, path: fullPath, kind: 'file', children: [], file });
        return;
      }
      const rest = segments.slice(1);
      const childPath = node.path ? `${node.path}/${head}` : head;
      let child = node.children.find((item) => item.kind === 'folder' && item.name === head) as AgentFileTreeNode | undefined;
      if (!child) {
        child = { name: head, path: childPath, kind: 'folder', children: [] };
        node.children.push(child);
      }
      insert(child, rest, file, fullPath);
    };

    for (const file of agentFileSummaries) {
      const normalized = file.path.replace(/\\/g, '/');
      const segments = normalized.split('/').filter(Boolean);
      const name = segments.pop() || normalized;
      insert(root, segments, file, normalized || name);
    }

    const sortTree = (node: AgentFileTreeNode): AgentFileTreeNode => {
      const children = node.children
        .map(sortTree)
        .sort((a, b) => {
          if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;
          return a.name.localeCompare(b.name, 'zh-CN');
        });
      return { ...node, children };
    };

    return sortTree(root);
  }, [agentFileSummaries]);

  const defaultExpandedFolders = useMemo(() => {
    const folders = new Set<string>();
    const walk = (node: AgentFileTreeNode) => {
      if (node.kind === 'folder' && node.path) folders.add(node.path);
      for (const child of node.children || []) walk(child);
    };
    walk(agentFileTree);
    return folders;
  }, [agentFileTree]);

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => defaultExpandedFolders);

  useEffect(() => {
    setExpandedFolders((prev) => {
      const next = new Set<string>();
      for (const path of prev) {
        if (defaultExpandedFolders.has(path)) next.add(path);
      }
      if (next.size === 0) {
        defaultExpandedFolders.forEach((path) => next.add(path));
      }
      return next;
    });
  }, [defaultExpandedFolders]);

  const toggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  return {
    agentFileSummaries,
    agentFileTree,
    expandedFolders,
    toggleFolder,
  };
}
