# ADR-007: Human-reviewable, versioned evidence

- Status: Accepted
- Date: 2026-06-23

## Context
Experts must retain authority over AI conclusions, and historical results must
remain reproducible.

## Decision
Every `EvidenceObservation` carries provenance (`source_type`, `source_id`,
`prompt_version`, `evaluator_version`, `model_name`, `evaluation_run_id`) and a
`human_review_status` (`pending/accepted/rejected/overridden`) plus an optional
`human_override`. The progress engine **excludes rejected** evidence and weights
human-accepted evidence higher. Raw evidence is never destroyed by a review;
only its status/override changes, and projections are rebuilt from it.

## Consequences
- Experts can reject/override observations and the learner state updates on
  rebuild — fully traceable (prompt §3 Rules 5 & 6).
- We can answer "why did this score change?" from stored provenance.
