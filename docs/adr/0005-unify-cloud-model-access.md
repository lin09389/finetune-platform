# ADR-0005: Unify Cloud Model Access Behind a Domain Service

## Status

Accepted

## Context

Cloud provider configuration, credential persistence, provider resolution and
request execution are concentrated in `server/api/cloud_chat.py`. Agent
sessions, inference fallback and intent classification also independently read
`SecureStorage`, creating inconsistent provider discovery and validation.

The public `/cloud/*` API and its SSE payloads are already consumed by the
React client, so a breaking route replacement is not acceptable.

## Decision

Introduce a `cloud_models` domain package with a credential repository,
provider catalog/resolver, and execution service. Keep `api.cloud_chat` as a
thin compatibility adapter while consumers migrate to the service. Credentials
remain in `SecureStorage`; the domain layer returns redacted metadata only.

## Consequences

### Positive

- One validation and resolution path for chat, Agent and fallback execution.
- Provider-specific behavior is isolated from HTTP routes.
- Existing REST/SSE contracts remain stable during migration.

### Negative

- Temporary compatibility wrappers exist until all consumers migrate.
- Additional domain tests are required for persistence and resolution rules.

## Alternatives Considered

**Rewrite `/cloud` endpoints in place**

Rejected because it would mix an API migration with a domain migration and
raise SSE compatibility risk.

**Keep per-consumer SecureStorage reads**

Rejected because model readiness and custom-provider behavior would continue
to drift.

## References

- `server/api/cloud_chat.py`
- `server/ai/providers.py`
- `server/agent_session/model_adapter.py`
