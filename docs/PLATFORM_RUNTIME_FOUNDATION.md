# Platform Runtime Foundation

Last updated: `2026-04-16`

This document defines the frontend foundation that now sits under the core platform workflow:

- shared runtime context
- shared notification adapter
- runtime-focused smoke and contract-style tests

The goal is to keep `Training / Inference / Knowledge / Chat` evolving as one platform surface instead of four independent pages.

## Why This Exists

The platform previously had three structural problems:

1. The same runtime truth was loaded and explained separately on multiple pages.
2. User choices did not propagate reliably across core workflows.
3. UI notifications and smoke tests were tied to page-level implementation details instead of platform contracts.

The new foundation solves those problems by centralizing runtime state, defining a shared notification boundary, and giving the core pages a stable acceptance-test layer.

## Backend Bootstrap Contract

Source: [server/api/runtime.py](/C:/Users/JHJ/Desktop/finetune-platform/server/api/runtime.py)

Endpoint: `GET /runtime/bootstrap`

The backend now exposes a runtime bootstrap contract for the frontend shell. It returns:

- `schema_version`
- `observed.backend_status`
- `observed.inference.backends`
- `observed.inference.current_backend`
- `observed.inference.huggingface_models`
- `observed.inference.ollama`
- `observed.knowledge.collections`
- `observed.knowledge.embedder_status`
- `observed.training`
- `derived.runtime_status`
- `derived.warnings`
- `derived.available_model_count`

The endpoint is intentionally tolerant. If one subsystem probe fails, bootstrap returns fallback data plus a warning instead of failing the entire request. This keeps the workbench load path observable and recoverable.

Frontend access is typed through [client/src/services/api.ts](/C:/Users/JHJ/Desktop/finetune-platform/client/src/services/api.ts) as `getRuntimeBootstrap()`.

As of `2026-04-16`, [client/src/runtime/RuntimeContext.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/runtime/RuntimeContext.tsx) uses this endpoint as the primary initialization path. If bootstrap fails, it falls back to the previous multi-request refresh path for inference and knowledge state.

The frontend runtime summary now preserves server-derived `derived.warnings` from bootstrap payloads so backend aggregation warnings are not lost in UI.
When backend connectivity transitions away from `connected`, stale bootstrap warnings are cleared to avoid showing historical warnings as current runtime truth.

## Runtime Context

Source: [client/src/runtime/RuntimeContext.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/runtime/RuntimeContext.tsx)

`RuntimeContextProvider` is the shared frontend runtime source for the GA workflow. It aggregates:

- backend connectivity
- inference backends and active model options
- Ollama availability and model list
- knowledge collections and embedder readiness
- chat runtime settings that should remain part of the shared operating state
- training selections that need to influence the wider platform summary

The provider exposes four explicit layers:

1. Observed state  
   `runtime.observed` is backend-derived truth such as connectivity, available inference backends, model lists, knowledge collections, and embedder readiness.

2. Selected state  
   `runtime.selected` is page or user intent, such as the model currently selected on a page or the active knowledge collection override.

3. Derived state  
   `runtime.derived` is the platform summary computed from observed state, chat settings, and selected overrides. It includes active backend, active model, active knowledge collection, runtime status, model count, and warnings.

4. Actions  
   `runtime.actions` contains refresh, local selection, and cross-page sync functions.

The previous convenience fields remain available for compatibility:

- `runtime.inference`, `runtime.knowledge`, `runtime.chat`, `runtime.training`
- `runtime.summary`
- top-level `set*Selection()` and `sync*()` functions

Use the local selection APIs when a page only needs to contribute temporary local intent. Use the sync APIs when the change should become part of the platform-wide operating state and be visible to other pages.

## Runtime Integration Rules

When wiring a page into the shared runtime layer, follow these rules:

1. Read shared runtime state before creating page-local fallbacks.  
   Pages should not invent their own default backend, model, or knowledge collection if runtime already has one.

3. Prefer the explicit layers for new code.  
   Use `runtime.observed` for backend truth, `runtime.selected` for local intent, `runtime.derived` for user-facing summaries, and `runtime.actions` for mutations.

4. Use `set*Selection()` for page-local tracking.  
   Example: training form selections that should influence the runtime summary but not immediately overwrite chat settings.

5. Use `sync*()` when the user is intentionally changing platform operating state.  
   Example: choosing the active inference model or knowledge collection that other pages should inherit.

6. Keep runtime summaries honest.  
   Do not mark derived or future state as active if the backend has not actually produced or loaded it.

The current implementation already follows this pattern:

- `Training` contributes model and dataset selections, can reuse the current active model, and can promote the selected base model into the active inference context.
- `Inference` uses runtime-backed backends and model lists.
- `Knowledge` uses runtime-backed collection and embedder state, and syncs collection changes.
- `Chat` consumes and updates shared model and knowledge choices.

As of `2026-04-16`, these four GA pages use the explicit `observed / selected / derived / actions` runtime layers as their primary integration path. The older convenience fields remain available only as compatibility shims while the rest of the frontend catches up.

## Notification Boundary

Source: [client/src/utils/notify.ts](/C:/Users/JHJ/Desktop/finetune-platform/client/src/utils/notify.ts)

Core platform pages should not depend directly on Ant Design's global `message` API when that dependency hurts testability or couples business logic to UI infrastructure.

`notify` is the thin adapter boundary for that purpose.

Current rule:

- `Training`
- `Inference`
- `Knowledge`
- `Chat`

should use `notify` for success, warning, error, and info messages related to the core runtime workflow.

This gives us two benefits:

1. Tests can mock the notification layer without mounting Ant Design's real global message infrastructure.
2. Future UX changes such as inline toasts, grouped notifications, or environment-specific behavior can be introduced centrally.

The adapter is intentionally small. It is not a full event bus and should stay that way unless product requirements clearly demand more.

## Test Strategy

The runtime foundation is protected by two complementary test layers.

### 1. Runtime Contract Tests

Source: [client/src/test/RuntimeContext.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/RuntimeContext.test.tsx)

These tests validate the runtime provider itself:

- aggregation of backend, model, and knowledge state
- precedence between shared state and page overrides
- propagation from chat settings into runtime summary
- fallback behavior when overrides are cleared
- sync APIs writing back into shared chat settings

Use this layer when changing provider semantics, precedence rules, or cross-page propagation behavior.

### 2. Runtime Workflow Tests

Source: [client/src/test/RuntimeWorkflows.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/RuntimeWorkflows.test.tsx)

These tests validate cross-page platform behavior:

- `Training -> Inference`: a training-selected base model can become the active inference context.
- `Knowledge -> Chat`: a selected knowledge collection writes into shared chat runtime settings.
- `Chat -> Runtime summary`: chat-selected backend, model, and collection are reflected in the platform summary.

Use this layer when changing sync semantics across GA pages. It should stay focused on behavior propagation, not page rendering details.

### 3. Smoke Acceptance Tests

Sources:

- [client/src/test/gaSmokePages.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/gaSmokePages.test.tsx)
- [client/src/test/betaTierPages.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/betaTierPages.test.tsx)
- [client/src/test/experimentalStatusPages.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/experimentalStatusPages.test.tsx)
- [client/src/test/Sidebar.test.tsx](/C:/Users/JHJ/Desktop/finetune-platform/client/src/test/Sidebar.test.tsx)

These tests validate platform-level UI contracts:

- tier labeling
- experimental status visibility
- GA page disconnected or degraded states
- runtime bridge actions on critical pages

Use this layer when changing what the user should be able to understand from the page, not when changing internal implementation details.

## How To Extend This Foundation

When adding a new platform-level capability, prefer this order:

1. Decide whether the state is local, shared, or synchronized.
2. Extend `RuntimeContext` only if another page should read the same truth.
3. Route user feedback through `notify` if the workflow belongs to the core platform chain.
4. Add or update:
   - one runtime contract test if provider behavior changes
   - one smoke test if page-level user understanding changes

Do not extend runtime context just because a page has state. Extend it only when the state represents platform operating context that should persist or propagate.

## What Not To Do

- Do not duplicate backend/model/collection loading on multiple GA pages if runtime already owns that truth.
- Do not silently override chat or runtime selections with hardcoded defaults.
- Do not present training artifacts as active runtime models before the backend exposes them as real loadable assets.
- Do not add page-level smoke assertions that depend on incidental markup or transient UI internals.
- Do not bypass `notify` on core platform pages unless there is a strong reason tied to a component-scoped interaction pattern.

## Current Scope

This foundation is intentionally focused on the core workbench path:

- `Training`
- `Inference`
- `Knowledge`
- `Chat`

`Beta` and `Experimental` pages may adopt the same patterns, but they should only be pulled in when the shared runtime truth is real and worth maintaining.
