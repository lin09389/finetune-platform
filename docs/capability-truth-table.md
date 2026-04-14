# Finetune Platform Capability Truth Table

Last updated: `2026-04-14`

This document is the source of truth for feature maturity, delivery expectations, and verification depth across the platform. Product copy, navigation labels, release notes, and regression tests should align with this table.

## Maturity Tiers

| Tier | Meaning |
| --- | --- |
| `GA` | Core user-facing capability with closed frontend/backend loop and active regression coverage. |
| `Beta` | Usable capability with known limits, environmental dependencies, or incomplete UX hardening. |
| `Experimental` | Non-stable feature for controlled validation only. UI must show status and limitations explicitly. |

## Capability Matrix

| Capability | Tier | Frontend/backend closed loop | Local or external dependency | Failure mode | Regression coverage |
| --- | --- | --- | --- | --- | --- |
| Training | `GA` | Yes | Local GPU / PyTorch stack | Explicit API errors and status updates | Backend integration tests |
| Inference | `GA` | Yes | Local model runtime or Ollama | Explicit API errors, circuit-breaker behavior | Backend integration and contract tests |
| Models | `GA` | Yes | Local filesystem, HuggingFace / ModelScope | Explicit API errors | Backend integration tests |
| Datasets | `GA` | Yes | Local filesystem | Explicit validation errors | Backend integration tests |
| Chat Sessions | `GA` | Yes | Local storage | Explicit API errors | Backend integration tests |
| Knowledge Base | `GA` | Mostly | Embedder, vector store, local files | Explicit API errors; preload status exposed | Backend integration tests |
| Project Context | `Beta` | Mostly | Local repository scanning and indexing | Explicit API errors; quality depends on repo shape | Partial backend coverage |
| Memory | `Beta` | Mostly | Local storage, vector/search internals | Explicit API errors | Backend service coverage |
| Model Center | `Beta` | Mostly | External registries and network | Explicit API errors; network-sensitive | Partial backend coverage |
| Workspace | `Beta` | Mostly | Local filesystem | Explicit API errors | Backend integration tests |
| CUA | `Experimental` | Partial | OS automation, screen, keyboard/mouse access | Must show environment limits in UI; API returns explicit state | Partial backend coverage, frontend smoke |
| Action Recorder | `Experimental` | Partial | Local interaction hooks and filesystem | Must show environment limits in UI | Frontend smoke, backend save/load tests |
| OCR | `Experimental` | Partial | Tesseract and/or RapidOCR | Explicit `unavailable` / dependency-missing behavior; no silent placeholder success | Targeted backend coverage |
| MCP | `Experimental` | Partial | Configured MCP servers | Explicit API errors | Backend integration tests |
| Heartbeat | `Experimental` | Partial | Local scheduler and task handlers | Explicit API errors | Backend integration tests |
| Gateway Extensions | `Experimental` | Partial | Device pairing, auth, websocket runtime | Explicit API errors | Backend integration tests |

## Current Guardrails

- Experimental pages must display real runtime status instead of implying guaranteed support.
- API metadata must only advertise canonical routes that are currently implemented.
- Dependency-missing scenarios must fail explicitly rather than returning placeholder-success payloads.
- Frontend tests should assert the current UI contract, not older interaction patterns that have been removed.

## Near-Term Upgrade Priorities

1. Platform fidelity
   Align docs, metadata, API contracts, and UI state with actual capability maturity.
2. Core UX upgrades
   Add training preflight checks, inference observability, and unified chat runtime context.
3. Experimental governance
   Keep only the experimental features that support the “local AI workbench” story and clearly mark the rest.
