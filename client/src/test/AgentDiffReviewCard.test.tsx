import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AgentDiffReviewCard from '../agent/components/AgentDiffReviewCard';
import { TimelineItem } from '../agent/components/AgentRunTimeline';
import {
  applyEventToSession,
  CODING_DIFF_CONTRACT_VERSION,
  selectCodingDiffReviewPayload,
} from '../agent/protocol/agentProtocol';
import { initialAgentRuntimeState } from '../agent/runtime/agentRuntime';
import {
  selectCodingDiffReviewGroups,
  selectTimeline,
} from '../agent/selectors/workbenchSelectors';
import type {
  AgentPart,
  AgentSession,
  AgentSessionEvent,
  AgentSessionUiTimelineItem,
} from '../services/api';

const sessionId = 'session-coding-diff';

function codingDiffPart(
  id: string,
  writeSequence: number,
  createdAt: string,
  overrides: Record<string, unknown> = {},
): AgentPart {
  return {
    id,
    session_id: sessionId,
    type: 'diff',
    status: 'completed',
    title: 'Diff review',
    content: '',
    created_at: createdAt,
    payload: {
      contract_version: CODING_DIFF_CONTRACT_VERSION,
      path: 'client/src/App.tsx',
      change_type: 'modified',
      additions: 2,
      deletions: 1,
      binary: false,
      truncated: false,
      write_sequence: writeSequence,
      review_status: 'ready',
      diff: '@@ -1,1 +1,2 @@\n-old\n+new\n+latest',
      ...overrides,
    },
  };
}

function session(parts: AgentPart[]): AgentSession {
  return {
    id: sessionId,
    agent_id: 'build',
    status: 'completed',
    title: 'Repair app',
    parts,
    preferences: { pinned: false, archived: false },
    created_at: '2026-07-11T10:00:00Z',
    updated_at: '2026-07-11T10:10:00Z',
  };
}

function reviewProjection(items: AgentSessionUiTimelineItem[]) {
  return selectCodingDiffReviewGroups(items).map((group) => ({
    path: group.path,
    entries: group.entries.map(({ item, payload }) => ({
      id: item.id,
      writeSequence: payload.writeSequence,
      changeKind: payload.changeKind,
      additions: payload.additions,
      deletions: payload.deletions,
      unifiedDiff: payload.unifiedDiff,
    })),
  }));
}

describe('Coding Agent persisted diff review', () => {
  it('accepts only a complete v1, workspace-relative review payload', () => {
    const valid = codingDiffPart('diff-1', 1, '2026-07-11T10:01:00Z');
    expect(selectCodingDiffReviewPayload(valid)).toMatchObject({
      path: 'client/src/App.tsx',
      changeKind: 'modified',
      writeSequence: 1,
    });
    expect(
      selectCodingDiffReviewPayload({
        ...valid,
        payload: { ...valid.payload, contract_version: 2 },
      }),
    ).toBeNull();
    expect(
      selectCodingDiffReviewPayload({
        ...valid,
        payload: { ...valid.payload, path: 'C:/Users/example/App.tsx' },
      }),
    ).toBeNull();
  });

  it('shows the latest write first and exposes earlier writes as read-only history', () => {
    const old = codingDiffPart('diff-1', 1, '2026-07-11T10:01:00Z', {
      change_type: 'added',
      additions: 1,
      deletions: 0,
      diff: '@@ -0,0 +1 @@\n+first',
    });
    const latest = codingDiffPart('diff-2', 2, '2026-07-11T10:02:00Z');
    const group = selectCodingDiffReviewGroups([old, latest])[0]!;

    render(<AgentDiffReviewCard group={group} />);

    expect(screen.getByLabelText('Diff 审阅：client/src/App.tsx')).toBeInTheDocument();
    expect(screen.getByText('修改 · 审阅材料已就绪')).toBeInTheDocument();
    expect(screen.getByText(/\+new/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看此前 1 次写入' })).toBeInTheDocument();
    expect(screen.queryByText('写入 #1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看此前 1 次写入' }));
    expect(screen.getByLabelText('client/src/App.tsx 的写入历史')).toBeInTheDocument();
    expect(screen.getByText('写入 #1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /commit|push|revert/i })).not.toBeInTheDocument();
  });

  it('keeps unknown versions on the generic artifact card and labels metadata-only records', () => {
    const unknown = codingDiffPart('legacy-diff', 1, '2026-07-11T10:01:00Z', {
      contract_version: 9,
      changed_files: ['client/src/App.tsx'],
      diff: '+legacy',
    });
    render(<TimelineItem item={unknown} />);
    expect(screen.getByRole('button', { name: '收起 1 个文件变更' })).toBeInTheDocument();
    expect(screen.getByText('+legacy')).toBeInTheDocument();

    const metadataOnly = codingDiffPart('binary-diff', 2, '2026-07-11T10:02:00Z', {
      binary: true,
      truncated: true,
      diff: undefined,
    });
    const group = selectCodingDiffReviewGroups([metadataOnly])[0]!;
    render(<AgentDiffReviewCard group={group} />);
    expect(screen.getByText('二进制文件：不提供内联 Diff。')).toBeInTheDocument();
    expect(screen.getByText('Diff 已按服务端上限截断，仅显示可审阅的片段。')).toBeInTheDocument();
  });

  it('projects REST recovery and SSE part updates into the same persisted review card data', () => {
    const parts = [
      codingDiffPart('diff-1', 1, '2026-07-11T10:01:00Z', {
        diff: '@@ -0,0 +1 @@\n+first',
      }),
      codingDiffPart('diff-2', 2, '2026-07-11T10:02:00Z'),
    ];
    const restTimeline = selectTimeline({ ...initialAgentRuntimeState, session: session(parts) });

    let sseSession: AgentSession | null = session([]);
    for (const part of parts) {
      const event: AgentSessionEvent = {
        id: `event-${part.id}`,
        session_id: sessionId,
        event_type: 'part_complete',
        chunk_type: 'part_complete',
        message: '',
        payload: {},
        created_at: part.created_at,
        part,
      };
      sseSession = applyEventToSession(sseSession, event);
    }
    const sseTimeline = selectTimeline({ ...initialAgentRuntimeState, session: sseSession });

    expect(reviewProjection(sseTimeline)).toEqual(reviewProjection(restTimeline));
  });
});
