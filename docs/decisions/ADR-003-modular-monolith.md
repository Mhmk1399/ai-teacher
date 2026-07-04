# ADR-003: Modular monolith architecture

- Status: Accepted
- Date: 2026-06-23

## Context
The product is ambitious, but the team and codebase are small and the domain is
still being discovered.

## Decision
Build a **modular monolith** with clear layers (presentation, application,
domain, AI, infrastructure). No microservices, message brokers, or separate
services at this stage. Application services are UI-independent so a future API
or Next.js client can reuse them.

## Consequences
- New code lives in additive `core/*` packages mirroring the target layers
  (`competency/`, `evidence/`, `progress/`, `ai/`) for a later mechanical move.
- We explicitly avoid Kafka, microservices, and premature distribution.
