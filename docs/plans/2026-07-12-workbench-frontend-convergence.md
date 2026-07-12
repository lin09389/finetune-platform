# Workbench Frontend Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align Phase 0–7 capabilities into a polished, responsive, visually consistent Codex-style Workbench without changing the established design language.

**Architecture:** Preserve the existing Agent runtime and component hierarchy. Improve information priority at the Workbench composition boundary, move track-specific visual rules into scoped modules where practical, and freeze capability/visual acceptance in additive tests and documentation. The shared design tokens remain the only palette, typography, spacing, radius, motion, and focus source.

**Tech Stack:** React 18, TypeScript, Ant Design, CSS Modules, Framer Motion, Vitest, Testing Library, Vite.

---

## Global guardrails

- No backend production changes and no new Agent capability.
- No palette, font, radius, global theme, icon-library, or route redesign.
- Do not modify or stage `server/tests/test_agent_training_integration_path.py`.
- No component may introduce raw theme-dependent white/black alpha colors.
- Preserve Build/Train/Hybrid, approvals, training cards, Diff, terminal, recovery, resize, keyboard and refresh behavior.
- Every track must compare against the accepted screenshots under `%TEMP%/finetune-phase75-audit/` and report visible trade-offs.

## Track A — Capability parity and experience contract

**Owned files**

- Create `docs/frontend-capability-parity-2026-07-12.md`
- Create `client/src/agent/testing/workbenchCapabilityParity.ts`
- Create `client/src/test/WorkbenchCapabilityParity.test.tsx`
- Update `client/src/agent/README.md`

### Task A1: Freeze the Phase 0–7 parity matrix

1. Enumerate Workspace, task modes, approvals, terminal, Diff, plan, subagents, training activity, recovery, diagnostics and capability gating.
2. Record discoverability, action, feedback, recovery, responsive and test status with source evidence.
3. Classify only P0/P1 gaps for Phase 7.5; defer unrelated route redesign.
4. Add a typed fixture that maps each capability to its existing UI surface and recovery source.
5. Write a failing test for missing/duplicate capability ownership, then make the fixture complete.
6. Run `npm exec vitest run src/test/WorkbenchCapabilityParity.test.tsx`.
7. Commit only owned files.

## Track B — Primary task surface and responsive hierarchy

**Owned files**

- Modify `client/src/agent/workbench/AgentWorkbenchPage.tsx`
- Modify `client/src/agent/workbench/AgentWorkbenchShell.tsx`
- Modify `client/src/agent/workbench/AgentWorkbench.module.css`
- Modify `client/src/agent/components/AgentTaskComposer.tsx`
- Modify `client/src/agent/components/AgentTaskContextBar.tsx`
- Create or update focused tests in `client/src/test/AgentProductPolish.test.tsx` and `client/src/test/AgentPanelLayout.test.tsx`

### Task B1: Make the task the visual center

1. Add failing tests for desktop priority, mobile new-task return, and preserved panel controls.
2. Refine the shell hierarchy so the main timeline/composer retains usable width before auxiliary regions.
3. Keep all persisted panel sizes and resize behavior backward compatible.
4. Use existing tokens only; do not restyle the global app.
5. Verify at 1440×900, 1280×720 and 390×844.

### Task B2: Clarify the next action in the composer

1. Add failing tests for unconfirmed Workspace, running, waiting intervention and terminal states.
2. Make the current prerequisite explicit without adding a modal or duplicate state machine.
3. Reduce secondary selector prominence while preserving labels and keyboard behavior.
4. Ensure reduced-motion and focus-visible behavior remain intact.
5. Run focused Vitest, `npm run typecheck`, `npm run build`, and commit.

## Track C — Session and auxiliary-surface polish

**Owned files**

- Modify `client/src/agent/components/AgentSessionRail.tsx`
- Modify `client/src/agent/components/AgentRightDock.tsx`
- Modify `client/src/agent/components/AgentTerminalDock.tsx`
- Modify `client/src/agent/components/AgentWorkspaceView.tsx`
- Create scoped modules beside owned components when new styling is required
- Create `client/src/test/AgentAuxiliarySurfacePolish.test.tsx`

### Task C1: Reduce secondary visual noise

1. Add failing tests for compact empty states, session metadata hierarchy and accessible panel controls.
2. Keep titles and current status primary; move timestamps/actions/secondary counts down one level.
3. Use compact empty states inside Diff, terminal and task-center subpanels; do not replace real icons with text symbols.
4. Preserve virtualization, resize handles, mounted terminal state and Diff Review cards.
5. Validate light/dark theme class behavior and 44px mobile targets.
6. Run focused Vitest, typecheck and build; commit only owned files.

## Main-thread integration and visual gate

1. Review Track A as the experience contract, then integrate B and C.
2. Reject changes that invent a new visual language or hide existing capability.
3. Resolve shared CSS only in the main thread; do not let Track C edit `AgentWorkbench.module.css`.
4. Run Workbench, runtime, training, Diff and capability test suites.
5. Run typecheck, production build and bundle budget.
6. Start the integrated app and capture the same four baseline states at the same viewports.
7. Inspect each saved screenshot and compare hierarchy, padding, typography, borders, radii, empty states and focus/interaction visibility.
8. Fix visible regressions before declaring Phase 7.5 complete.

## Wave 2 — Application shell and primary-page convergence

Wave 2 starts only after Tracks A–C are integrated and visually accepted. The main thread will create a second non-overlapping batch from the capability matrix.

### Track D: Navigation and naming consistency

**Expected ownership:** `Sidebar.tsx`, `HeaderBar.tsx`, mobile navigation, route-title facts and focused navigation tests.

- Remove duplicate route-title dictionaries and inconsistent labels.
- Preserve capability-tier runtime authority and experimental guards.
- Align desktop/mobile active, disconnected and compact states without changing routes.

### Track E: Shared loading, empty, error and status adoption

**Expected ownership:** shared state components plus a bounded set of GA/Beta pages selected from the parity matrix.

- Consolidate repeated loading/empty/error markup onto existing shared components.
- Keep page-specific content and operations; do not flatten professional workflows into generic cards.
- Replace theme-dependent hardcoded colors only inside owned pages.

### Track F: Cross-page visual and accessibility acceptance

**Expected ownership:** additive scenarios/tests/audit docs and screenshot evidence; no production implementation.

- Freeze light/dark, desktop/mobile, disconnected and empty-state acceptance.
- Verify page headings, primary actions, focus visibility, touch targets and reduced motion.
- Report remaining P2/P3 debt instead of expanding scope silently.

## Definition of done

- The default Workbench clearly prioritizes task execution and continuation.
- Existing Phase 0–7 capabilities have a documented, tested UI owner.
- Desktop and mobile auxiliary panels no longer obscure the main next action by default.
- Application navigation, route titles and major GA/Beta page states use one consistent language.
- Visual changes look native to the current paper/editorial system.
- No backend or user-owned unrelated file is included.
- Automated tests and screenshot-based visual review both pass.
