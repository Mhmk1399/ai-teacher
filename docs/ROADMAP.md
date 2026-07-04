# Roadmap

Each phase must produce working, testable software. We do not build everything
at once. CEFR is always a derived projection; the LLM never decides mastery.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repository audit & stabilization | **done (this session)** |
| 1 | Competency domain foundation (schema, migrations, repos) | **in progress (milestone)** |
| 2 | Expert-managed competency catalog | partial (seed slice) |
| 3 | Evidence extraction engine | partial (milestone slice) |
| 4 | Deterministic progress & mastery engine | partial (milestone slice) |
| 5 | Discovery conversation & adaptive placement | not started |
| 6 | Adaptive learning-path engine | not started |
| 7 | AI teacher orchestration (strategies) | not started |
| 8 | Voice learning loop | not started |
| 9 | Expert & learner dashboards | not started |
| 10 | Scientific validation & production readiness | not started |

## Phase 0 — done

`.gitignore` + `.env.example`; untracked `.venv`/`.env`/`*.db`/`__pycache__`;
Alembic added and existing schema baselined + stamped; pytest scaffold with
in-memory DB and existing-workflow smoke tests; the 7 docs + 8 ADRs.

**DoD met:** app still imports; existing workflows intact; no secrets/venv
tracked; a test command exists (`pytest`).

## The immediate milestone — "Existing Exam Answer → Living Competency Projection"

A correct **small** vertical slice (10–12 grammar competencies — not a faked
A1–C2 catalog):

1. Expert seeds competency definitions.
2. Student submits an answer (existing exam flow, unchanged).
3. Whole-answer scorer keeps working.
4. A separate competency **extractor** analyzes the answer (AI behind a provider
   interface; strict Pydantic output; fake provider in tests).
5. Observations are validated and stored, linked to the source answer and the
   `EvaluationRun`.
6. The deterministic **progress engine** recomputes learner competencies.
7. A **CEFR projection** is computed from competency data.
8. Expert inspects source answer, detected competencies, evidence, confidence,
   state, and the **reason**; can **reject/override**; rebuild respects it.

### Acceptance criteria (mirrors prompt §14)

- Existing student/item/exam/session/scoring/audit still function.
- Migrations exist; competency/observation/projection tables exist.
- ≥1 existing answer can generate evidence; AI output is schema-validated.
- Mastery is deterministic; **one observation cannot produce mastery**.
- Every projection links back to evidence; expert can reject an observation;
  rebuilding respects reviews.
- CEFR is exposed as a derived projection. Tests cover the critical rules.
- No secrets exposed; no venv as source; app still runnable.

## Setup & commands

```bash
# Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # adjust as needed

# Database migrations
alembic upgrade head        # apply all migrations (fresh DB builds from scratch)
alembic downgrade -1        # roll back the last migration
alembic current             # show current revision
alembic history             # list migrations

# Run the admin app
./run.sh                    # or: streamlit run app.py

# Tests (never require Ollama)
pytest                      # full suite
pytest -m "not ollama"      # default; ollama-marked tests are opt-in
```

### Migration & rollback notes

- The **baseline** was stamped onto the existing populated DB, so current data
  was preserved (not recreated).
- The **milestone** migration is additive; `downgrade -1` drops only the new
  competency tables and leaves assessment data intact.
- A brand-new clone runs `alembic upgrade head` to build the full schema.

## Later phases (summary)

- **2** Full catalog CRUD + versions; C2 via performance descriptors, not longer
  grammar lists.
- **3** Provider-independent extraction, idempotent, replayable; failures never
  silently dropped.
- **4** Configurable thresholds; regression detection; human overrides without
  destroying raw evidence; CEFR per skill + overall.
- **5–8** Adaptive placement, learning-path engine, teacher strategies behind one
  orchestrator, voice via the same evidence pipeline.
- **9–10** Dashboards; benchmark datasets, agreement/false-mastery metrics,
  PostgreSQL, auth/RBAC, Docker, backups, retention.
