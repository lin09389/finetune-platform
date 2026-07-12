import { describe, expect, it } from 'vitest';
import { ROUTE_CAPABILITY, isExperimentalRoute } from '../capability/tiers';
import { WORKBENCH_CAPABILITY_PARITY } from '../agent/testing/workbenchCapabilityParity';
import { getRouteTitle } from '../routes/meta';
import {
  PHASE75_CROSS_PAGE_ACCEPTANCE,
  phase75CrossPageScenario,
} from '../testing/phase75CrossPageScenarios';

describe('Phase 7.5 Wave 2 cross-page acceptance contract', () => {
  it('uses route metadata for the shared navigation names and preserves the two Workbench lines', () => {
    const namedRoutes = PHASE75_CROSS_PAGE_ACCEPTANCE.navigation;

    expect(namedRoutes.map((route) => route.id)).toEqual([
      'agent-daily-workbench',
      'training-specialist-workbench',
      'workspace-beta-entry',
      'gateway-experimental-entry',
    ]);
    expect(namedRoutes.map((route) => getRouteTitle(route.path))).toEqual(
      namedRoutes.map((route) => route.label),
    );
    expect(namedRoutes.map((route) => ROUTE_CAPABILITY[route.path]?.tier)).toEqual(
      namedRoutes.map((route) => route.tier),
    );

    const agent = phase75CrossPageScenario('agent-daily-workbench');
    const training = phase75CrossPageScenario('training-specialist-workbench');
    expect(agent.workbenchLine).toBe('daily-coding');
    expect(training.workbenchLine).toBe('specialist-training');
    expect(agent.sharedWorkbench).toBe(true);
    expect(training.sharedWorkbench).toBe(true);
  });

  it('keeps Build, Train, and Hybrid inside the GA Workbench rather than capability-tier navigation', () => {
    const workbenchModes = WORKBENCH_CAPABILITY_PARITY.filter((entry) =>
      ['build-mode', 'train-mode', 'hybrid-mode'].includes(entry.id),
    );

    expect(workbenchModes.map((entry) => entry.id)).toEqual([
      'build-mode',
      'train-mode',
      'hybrid-mode',
    ]);
    expect(workbenchModes.every((entry) => entry.defaultWorkflow && entry.availability === 'ga')).toBe(true);
    expect(PHASE75_CROSS_PAGE_ACCEPTANCE.navigation.filter((route) => route.tier === 'experimental')).toHaveLength(1);
    expect(isExperimentalRoute('/agent')).toBe(false);
    expect(isExperimentalRoute('/training')).toBe(false);
    expect(isExperimentalRoute('/gateway')).toBe(true);
  });

  it('freezes the desktop, mobile, keyboard, touch, and state matrix without claiming manual checks passed', () => {
    const { viewports, interactionChecks, stateMatrix, deferredManualChecks } =
      PHASE75_CROSS_PAGE_ACCEPTANCE;

    expect(viewports).toEqual([
      expect.objectContaining({ id: 'desktop-1280', width: 1280, height: 720, automated: false }),
      expect.objectContaining({ id: 'mobile-390', width: 390, height: 844, automated: false }),
    ]);
    expect(interactionChecks).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'keyboard-reachability', evidence: 'code-contract', automated: true }),
      expect.objectContaining({ id: 'touch-targets', minimumCssPixels: 44, automated: false }),
    ]));
    expect(stateMatrix.map((state) => state.id)).toEqual([
      'agent-loading',
      'agent-empty',
      'agent-error-retry',
      'training-loading',
      'training-empty',
      'training-error-retry',
      'ga-beta-disconnected',
    ]);
    expect(stateMatrix.every((state) => state.primaryActionExpectation.length > 0)).toBe(true);
    expect(deferredManualChecks.every((check) => check.status === 'deferred')).toBe(true);
    expect(deferredManualChecks.map((check) => check.id)).toEqual(expect.arrayContaining([
      'contrast-light-dark',
      'zoom-200-percent',
      'screen-reader-announcements',
      'drawer-focus-cycle',
      'mobile-touch-measurement',
    ]));
  });
});
