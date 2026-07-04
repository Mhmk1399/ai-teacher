# Security & Privacy

Lingua Nova is **local-first and privacy-first**: by default all inference runs
on a local Ollama model, and learner data stays in a local database. This
document records the security posture, the issues found during the audit, and
the controls applied.

## Findings from the Phase 0 audit (and actions)

| Finding | Severity | Action (working tree only — not committed) |
|---|---|---|
| `.env` tracked in git | High | Untracked via `git rm --cached`; added to `.gitignore`; `.env.example` provided. Values were **never printed**. |
| `.venv/` tracked (10,492 files) | Medium (hygiene) | Untracked; ignored. |
| `data/lingua.db` (live learner data) tracked | High (privacy) | Untracked; ignored. |
| `__pycache__/` tracked | Low | Untracked; ignored. |
| No `.gitignore` | Medium | Added. |

**Note:** untracking removes files from future commits but they remain in git
**history**. If the repository was ever pushed, rotate anything that was in
`.env` and consider history rewriting (`git filter-repo`) before publishing.
This was **not** performed automatically and no secret values were inspected.

## Secret handling

- Secrets come only from `.env` (loaded by `core/config.py`). `.env` is git-ignored.
- `.env.example` documents required keys with placeholder values only.
- Do not log secrets. The logging guidance (below) forbids it.

## Data & PII

- Learner PII (names, external IDs, free-text responses) lives in the database.
- **Logging rule:** structured logs record IDs, versions, outcomes, and counts —
  **not** raw student text or personal data unless explicitly required for an
  audited review action.
- `EvidenceObservation.observed_text` stores short source excerpts needed for
  traceability/expert review; treat the table as sensitive.

## AI provider boundary

- All model calls go through a `LanguageModelProvider` interface. The default
  adapter is local Ollama. Adding a hosted provider (OpenAI, etc.) is a
  deliberate change that moves data off-device and must be documented and
  consented to before enabling.

## Auditability

- The append-only `audit_log`, plus `evaluation_runs` and human-review status on
  observations, mean every competency conclusion is traceable to its source and
  to the model/prompt version that produced it (prompt §3 Rule 5, ADR-007).

## Deferred (Phase 10)

Authentication & role-based access, data-retention controls, backup/restore,
PostgreSQL hardening, and formal privacy documentation are production concerns
tracked in `docs/ROADMAP.md`.
