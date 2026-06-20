# Commands

`agentCommands.ts` owns typed command definitions, idempotency keys, multi-request transaction ordering, partial-session recovery, and structured refresh/stream directives. Runtime code consumes command results; it must not reproduce endpoint ordering.
