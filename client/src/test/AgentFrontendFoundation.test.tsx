import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import AgentWorkbenchRoute from '../agent/workbench/AgentWorkbenchRoute';
import type { AgentTransport } from '../agent/transport/agentTransport';
import baselineFixture from '../agent/testing/fixtures/agent-session-baseline.json';
import {
  AGENT_PROTOCOL_BASELINE_VERSION,
  REQUIRED_STREAM_ENVELOPE_FIELDS,
  type AgentProtocolBaselineFixture,
} from '../agent/protocol/foundation';

const agentRoot = path.resolve(process.cwd(), 'src/agent');
const forbiddenImports = [
  /pages\/ChatNew/,
  /pages\/chatNew/,
  /hooks\/chat/,
  /components\/chat/,
  /store\/chatStore/,
];

function isolatedTransport(): AgentTransport {
  return {
    listAgents: vi.fn().mockResolvedValue([]),
    listSessions: vi.fn().mockResolvedValue([]),
    createSession: vi.fn(),
    getSession: vi.fn(),
    updateSessionPreferences: vi.fn(),
    getWorkspace: vi.fn(),
    prompt: vi.fn(),
    interrupt: vi.fn(),
    decidePermission: vi.fn(),
    approvePermission: vi.fn(),
    rejectPermission: vi.fn(),
    recoverNode: vi.fn(),
    startAsyncTask: vi.fn(),
    cancelAsyncTask: vi.fn(),
    reportDiagnostics: vi.fn().mockResolvedValue({ accepted: 0 }),
    connectStream: vi.fn().mockReturnValue({ close: vi.fn() }),
  } as AgentTransport;
}

function sourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    return /\.(ts|tsx)$/.test(entry.name) ? [target] : [];
  });
}

describe('Agent frontend Phase 1 foundation', () => {
  it('renders the independent Workbench shell when enabled', async () => {
    const transport = isolatedTransport();
    render(
      <MemoryRouter
        initialEntries={['/agent']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AgentWorkbenchRoute
          transport={transport}
          persistence={{
            read: () => ({ version: 1, activeSessionId: null, sessions: [] }),
            write: vi.fn(),
          }}
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(transport.listAgents).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Agent 工作台')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新建任务' })).toBeInTheDocument();
    expect(screen.getByLabelText('任务目标')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '工作台面板' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '任务中心' })).toBeInTheDocument();
    const sessionResizeHandle = screen.getByRole('separator', { name: '调整会话栏宽度' });
    expect(sessionResizeHandle).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整工作区宽度' })).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整终端高度' })).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整工作区与任务中心比例' })).toBeInTheDocument();
    fireEvent.keyDown(sessionResizeHandle, { key: 'ArrowLeft' });
    expect(sessionResizeHandle).toHaveAttribute('aria-valuenow', '216');
    fireEvent.click(screen.getByRole('button', { name: '环境' }));
    expect(screen.getByText('环境信息')).toBeInTheDocument();
  });

  it('keeps the sanitized baseline fixture aligned with the stream envelope', () => {
    const fixture = baselineFixture as AgentProtocolBaselineFixture;
    expect(fixture.fixture_version).toBe(AGENT_PROTOCOL_BASELINE_VERSION);
    expect(fixture.source.sanitized).toBe(true);
    expect(fixture.events.length).toBeGreaterThanOrEqual(4);
    for (const event of [fixture.snapshot, ...fixture.events]) {
      for (const field of REQUIRED_STREAM_ENVELOPE_FIELDS) {
        expect(event).toHaveProperty(field);
      }
    }
    expect(fixture.events.some((event) => event.event_type === 'permission_asked')).toBe(true);
    expect(fixture.events.some((event) => event.event_type === 'loop_guard_triggered')).toBe(true);
  });

  it('prevents the rewrite foundation from importing legacy Agent orchestration', () => {
    const violations = sourceFiles(agentRoot).flatMap((file) => {
      const source = fs.readFileSync(file, 'utf8').replace(/\\/g, '/');
      return forbiddenImports
        .filter((pattern) => pattern.test(source))
        .map((pattern) => `${path.relative(agentRoot, file)} -> ${pattern}`);
    });

    expect(violations).toEqual([]);
  });
});
