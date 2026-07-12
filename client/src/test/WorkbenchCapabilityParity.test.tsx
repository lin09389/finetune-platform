import { describe, expect, it } from 'vitest';
import {
  WORKBENCH_CAPABILITY_PARITY,
  type WorkbenchCapabilityParityEntry,
} from '../agent/testing/workbenchCapabilityParity';

describe('Workbench capability parity contract', () => {
  it('assigns every documented capability to one non-duplicated UI owner', () => {
    const owners = WORKBENCH_CAPABILITY_PARITY.map((capability) => capability.uiOwner);

    expect(new Set(owners).size).toBe(owners.length);
    expect(WORKBENCH_CAPABILITY_PARITY.map((capability) => capability.id)).toEqual([
      'workspace',
      'build-mode',
      'train-mode',
      'hybrid-mode',
      'approval',
      'permission',
      'terminal',
      'diff',
      'plan',
      'subagents',
      'training-activity',
      'recovery',
      'diagnostics',
      'capability-tier-gating',
    ]);
  });

  it('gives every capability a user-visible recovery source', () => {
    for (const capability of WORKBENCH_CAPABILITY_PARITY) {
      expect(capability.discover.trim(), `${capability.id} discover`).not.toBe('');
      expect(capability.action.trim(), `${capability.id} action`).not.toBe('');
      expect(capability.feedback.trim(), `${capability.id} feedback`).not.toBe('');
      expect(capability.responsive.trim(), `${capability.id} responsive`).not.toBe('');
      expect(capability.testOwner.trim(), `${capability.id} test owner`).not.toBe('');
      expect(capability.recovery.source.trim(), capability.id).not.toBe('');
      expect(capability.recovery.evidence.trim(), capability.id).not.toBe('');
    }
  });

  it('keeps experimental capability gating out of the default Workbench workflow', () => {
    const experimental = WORKBENCH_CAPABILITY_PARITY.filter(
      (capability) => capability.availability === 'experimental',
    );

    expect(experimental).toHaveLength(1);
    expect(experimental[0]).toMatchObject({
      id: 'capability-tier-gating',
      defaultWorkflow: false,
      action: 'Guard experimental routes only; do not advertise them as Workbench task modes.',
    } satisfies Partial<WorkbenchCapabilityParityEntry>);
  });

  it('separates Workbench convergence from application-shell and deferred acceptance work', () => {
    expect(WORKBENCH_CAPABILITY_PARITY.filter((capability) => capability.delivery === 'wave1')).toHaveLength(12);
    expect(WORKBENCH_CAPABILITY_PARITY.filter((capability) => capability.delivery === 'wave2')).toMatchObject([
      { id: 'capability-tier-gating' },
    ]);
    expect(WORKBENCH_CAPABILITY_PARITY.filter((capability) => capability.delivery === 'deferred')).toMatchObject([
      { id: 'diagnostics' },
    ]);
  });
});
