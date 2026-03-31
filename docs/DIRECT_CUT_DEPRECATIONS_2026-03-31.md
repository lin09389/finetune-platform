# Direct-Cut Deprecations (2026-03-31)

## Scope
This document records deprecated interfaces after the direct-cut migration of:
- intent detection / save-intent
- execution module
- gateway module
- chat + persistence chain

## Deprecated API Surface
1. `/agent/audit/*`
- Status: removed from public direct-cut contract.
- Current frontend behavior: compatibility wrappers map to `/agent-executor/*`.
- Wrapper location: `client/src/services/api.ts`

2. Legacy multi-shape intent responses
- Status: deprecated.
- Replacement: unified response shape from:
  - `POST /agent/detect-intent`
  - `POST /agent/detect-intent-multi`
  - `POST /agent/chat-execute`
  - `POST /smart-agent/smart-execute`

3. Legacy gateway route fields that had no backend implementation
- Status: removed from route contract.
- Replacement: only methods implemented by:
  - `BindingManager`
  - `DeviceAuthManager`
  - `AgentIsolationManager`
  - `CrossAgentCommunicator`
  - `GatewayServer`

## Replacement Mapping
1. Intent detection
- old: multiple intent result structures
- new: `detected / intent_type / action / params / confidence / need_confirm / execution`

2. Save-intent flow
- old: ad-hoc detect + execute coupling
- new: first-class intent types:
  - `content_generation`
  - `save_content`
  - `composite_content_save`
  with preconditions in params:
  - `has_content`
  - `path_writable`

3. Gateway status and device/binding actions
- old: route calls with method drift risk
- new: signatures guarded by `server/tests/test_gateway_api_signature_contract.py`

## Runtime Notes
1. Old executor modules may still exist in repository for compatibility review, but active API execution path is unified through `agent.core`.
2. High-risk actions must be explicitly confirmed (`high-risk strong confirm` policy).

## Removal Boundary (Current Version)
1. No old behavior branch is kept in public API contract.
2. Frontend keeps minimal wrappers only where required to avoid immediate breakage.
3. Full physical deletion of legacy internals should be done in a dedicated follow-up with full regression run.
