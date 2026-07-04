# ADR-002: CEFR as a derived projection

- Status: Accepted
- Date: 2026-06-23

## Context
CEFR (A1–C2) is useful for communication with learners and institutions, but it
is too coarse to be the learner's internal state (ADR-001).

## Decision
CEFR is **computed** from competency states by a deterministic, versioned
projection algorithm and stored as a `CEFRProjection` snapshot (per skill +
overall, with confidence and an explanation). It is never written directly as
learner truth.

## Consequences
- `Student.cefr_level` is non-authoritative; the source of truth is the graph.
- A CEFR level can be recomputed and explained from evidence at any time.
- CEFR cannot exceed what competency rules and evidence support (tested).
