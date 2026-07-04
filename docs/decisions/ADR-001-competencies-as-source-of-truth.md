# ADR-001: Competencies as the source of truth

- Status: Accepted
- Date: 2026-06-23

## Context
The MVP models a learner as a single `cefr_level` string. The product needs an
uneven, multi-ability profile (strong conditionals, weak articles, B2 reading /
B1 speaking, …) that drives teaching.

## Decision
The authoritative model of a learner is a graph of **competencies** plus the
**evidence** observed about them. All higher-level views (including CEFR) are
derived from this.

## Consequences
- New entities: `CompetencyDefinition`, `EvidenceObservation`, `LearnerCompetency`.
- `Student.cefr_level` remains only for backward compatibility (ADR-002).
- Teaching, placement, and reporting consume the competency graph, not a band.
