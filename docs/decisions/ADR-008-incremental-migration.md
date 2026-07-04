# ADR-008: Incremental migration from the current Streamlit MVP

- Status: Accepted
- Date: 2026-06-23

## Context
The MVP works and holds real data. A big-bang rewrite or folder relocation would
risk breaking it and lose trust.

## Decision
Evolve incrementally and **additively**. Keep the existing assessment tables and
Streamlit pages untouched; add new competency packages and tables alongside.
Introduce Alembic by **baselining** the existing schema (stamped on the live DB)
before any additive migration. Preserve working imports; defer the `src/`
relocation until later, with an interim mapping documented in
`docs/TARGET_ARCHITECTURE.md`.

## Consequences
- Existing student/item/exam/session/scoring/audit workflows keep working.
- New functionality is opt-in and reversible (`alembic downgrade`).
- The first slice integrates with existing `Answer` rows as a source of evidence
  rather than replacing the scoring path.
