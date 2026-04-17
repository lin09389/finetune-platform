import { API_BASE_URL } from './api';
import { updateChatSessionMetadata } from './chatSessionApi';

export interface ConversationTreeNode {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  parent_id: string | null;
  children_ids: string[];
  branch_name?: string;
}

export interface ConversationBranchSummary {
  id: string;
  session_id: string;
  name: string;
  created_at: string;
  root_message_id: string | null;
  last_message_id?: string | null;
  message_count: number;
}

export interface ConversationTreePayload {
  nodes: Record<string, ConversationTreeNode>;
  root_id: string | null;
  current_branch_id: string | null;
}

export interface ConversationTreeState {
  tree: ConversationTreePayload;
  branches: ConversationBranchSummary[];
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      (errorData as { detail?: string }).detail ||
        `Conversation tree request failed: ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export async function fetchConversationTree(sessionId: string): Promise<ConversationTreePayload> {
  return requestJson<ConversationTreePayload>(`${API_BASE_URL}/chat/${sessionId}/tree`);
}

export async function fetchConversationBranches(sessionId: string): Promise<{
  branches: ConversationBranchSummary[];
}> {
  return requestJson<{ branches: ConversationBranchSummary[] }>(
    `${API_BASE_URL}/chat/${sessionId}/branches`,
  );
}

export async function fetchConversationTreeState(
  sessionId: string,
): Promise<ConversationTreeState> {
  const [tree, branchPayload] = await Promise.all([
    fetchConversationTree(sessionId),
    fetchConversationBranches(sessionId),
  ]);

  return {
    tree,
    branches: branchPayload.branches || [],
  };
}

export async function switchConversationBranch(sessionId: string, branchId: string) {
  return requestJson<{ success: boolean; message: string }>(
    `${API_BASE_URL}/chat/${sessionId}/switch-branch/${branchId}`,
    { method: 'POST' },
  );
}

export async function switchConversationToMainTimeline(sessionId: string) {
  return updateChatSessionMetadata(sessionId, {
    current_branch_id: null,
  });
}

export async function createConversationBranch(
  sessionId: string,
  fromMessageId: string,
  branchName?: string,
) {
  return requestJson<{ success: boolean; branch?: { id?: string } }>(
    `${API_BASE_URL}/chat/branch`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        from_message_id: fromMessageId,
        branch_name: branchName,
      }),
    },
  );
}

export async function saveConversationMessage(
  sessionId: string,
  role: 'user' | 'assistant',
  content: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<{ id: string; session_id: string; role: string; content: string }>(
    `${API_BASE_URL}/chat/sessions/${sessionId}/messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        role,
        content,
        metadata,
      }),
    },
  );
}

export async function deleteConversationBranch(sessionId: string, branchId: string) {
  return requestJson<{ success: boolean; message: string }>(
    `${API_BASE_URL}/chat/${sessionId}/branch/${branchId}`,
    {
      method: 'DELETE',
    },
  );
}

export async function mergeConversationBranch(sessionId: string, branchId: string) {
  return requestJson<{
    success: boolean;
    message: string;
    merged_count?: number;
    target_branch_id?: string | null;
  }>(`${API_BASE_URL}/chat/${sessionId}/merge-branch/${branchId}`, {
    method: 'POST',
  });
}
