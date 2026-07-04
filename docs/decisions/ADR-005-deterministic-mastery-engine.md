# ADR-005: Deterministic mastery engine

- Status: Accepted
- Date: 2026-06-23

## Context
Mastery decisions must be reliable, explainable, and reproducible. An LLM is
neither deterministic nor accountable for such decisions (ADR-006).

## Decision
A deterministic, versioned **progress engine** computes competency state and
mastery from valid evidence and the competency's configured thresholds. The
formula is in code, not in prompts:

```
mastery_eligible =
    valid_evidence_count   >= competency.evidence_required
AND weighted_accuracy      >= competency.accuracy_threshold
AND distinct_context_count >= competency.contexts_required
AND projection_confidence  >= configured_minimum
```

States: `not_observed, emerging, developing, proficient, mastered, needs_review,
regressing`. Each computed state stores a human-readable `reason`.

## Consequences
- One correct answer cannot create mastery (count + context gates).
- Negative/rejected evidence changes the outcome; projections are rebuildable.
- Thresholds are configurable per competency and the algorithm is versioned
  (`algorithm_version`) for reproducibility.
