# Repository Audit — Lingua Nova

_Audit date: 2026-06-23. Based on reading the source, not the README claims._

## 1. What this repository is today

A local-first, privacy-first **CEFR English assessment MVP** ("Exam Machine").
A language expert authors items, manages students, assembles exams, runs
text-based exam sessions, scores answers with a local Ollama LLM, flags
low-confidence scores, and overrides them — with an append-only audit log that
doubles as future fine-tuning data.

It is a small, clean Python/Streamlit + SQLAlchemy 2 + SQLite monolith.

## 2. Source inventory (excluding `.venv/`, caches, `frontend/`)

| Path | Role | Keep / Refactor / Prototype |
|---|---|---|
| `app.py` | Dashboard home; boots DB + seeds; Ollama health; stats | Keep (UI) |
| `core/config.py` | Env-driven settings (`Settings` singleton) | Keep |
| `core/db.py` | Engine, `SessionLocal`, `init_db`, `session_scope` | Keep |
| `core/models.py` | ORM: Student, Item, Exam, ExamSession, Answer, AuditLog | Keep + extend |
| `core/llm.py` | `OllamaClient` (chat/generate, JSON, health) | Keep, wrap behind provider interface |
| `core/prompts.py` | Scorer + item-generation prompt templates | Keep, add versioning |
| `core/scoring.py` | Whole-answer scoring, confidence flagging, override, audit | Keep; add extraction hook |
| `core/exam_engine.py` | Exam assembly / item selection | Refactor (has a bug + dead code) |
| `core/seed.py` | Idempotent item seeder | Keep + extend (competency catalog) |
| `pages/1..6` | Streamlit pages (Students, Items, Exams, Sessions, Audit, Score Lab) | Keep (UI) |
| `data/seeds/sample_items.json` | 7 sample CEFR items | Keep |
| `scripts/test_ollama.py` | Ollama connectivity check | Keep |
| `frontend/` | Next.js scaffold, separate `.git`, tracked as gitlink | Prototype / not wired |
| `toutrial.txt` | Persian product notes (vision corroboration) | Keep as reference |

**Live database (`data/lingua.db`) at audit time:** 3 students, 7 items, 5 exams,
1 exam session, 1 answer, 6 audit rows. One real `Answer` exists — usable for the
first vertical slice.

## 3. Where business logic lives / coupling

- **Streamlit ↔ persistence coupling:** every page opens `session_scope()` and
  uses ORM models directly (e.g. `pages/1_📚_Students.py`). No service layer.
- **Ollama ↔ scoring coupling:** `core/scoring.py` imports `core/llm.get_client()`
  directly. The LLM is at least isolated in one class (`OllamaClient`) — a good
  seam — but there is no provider interface.
- **Pure/reusable:** `score_response_for_item(item, response)` is DB-free and
  easily testable; `exam_engine.items_for_exam` is reusable.

## 4. Confirmed technical debt & bugs (verified by reading code)

1. **`core/llm.chat` retry loop is broken** (lines ~90–104): on the first
   `LLMError` it returns the `/api/generate` fallback or `break`s; the
   `max_retries` loop never actually retries. The two statements after `break`
   are dead code.
2. **`core/exam_engine.generate_exam` does not persist an exam→item snapshot**
   (gap #7). It sets a non-persisted `_selected_items` attribute and contains
   dead `import` + comments; `items_for_exam` re-randomizes per call, so an exam
   has no stable item set.
3. **CEFR stored directly on `Student.cefr_level`** — fine for the MVP, but the
   target treats CEFR as derived (ADR-002).
4. **No migrations** (fixed in this milestone — Alembic added).
5. **No tests** (fixed — pytest scaffold added).
6. **No service/repository layer**; UI reaches into ORM.
7. **Prompt/model/evaluator versions not persisted**; no `EvaluationRun`.
8. **`datetime.utcnow()` deprecation** across models/scoring (low priority).
9. **README/sample data minor typos** (`"speeking"`, `format` JSON comment).

## 5. Security & hygiene findings (verified)

| Finding | Status before | Action taken (working tree only) |
|---|---|---|
| `.venv/` committed (10,492 files) | tracked | `git rm --cached` (kept on disk) + `.gitignore` |
| `.env` committed | tracked | untracked + `.env.example` added |
| `data/lingua.db` (live data) committed | tracked | untracked + ignored |
| `__pycache__/` committed | tracked | untracked + ignored |
| No `.gitignore` | absent | created |

`.env` keys present: `OLLAMA_HOST`, `OLLAMA_MODEL`, `DATABASE_URL`, `PHASE`. **No
secret credentials** were found in it at audit time, but a tracked `.env` is a
standing risk; values were never printed. See `docs/SECURITY_AND_PRIVACY.md`.

## 6. Missing tests (now seeded)

Added a pytest scaffold with in-memory DB fixtures and existing-workflow smoke
tests. Remaining coverage (extraction, progress, projection) is added with the
milestone. No test requires Ollama.

## 7. Gap between current product and target

The MVP is an **assessment machine**; the target is a **continuously-learning AI
teacher** built on a competency graph where CEFR is derived. See
`docs/PRODUCT_VISION.md`, `docs/TARGET_ARCHITECTURE.md`, and `docs/ROADMAP.md`.

## 8. Recommended first milestone

"Existing Exam Answer → Living Competency Projection" — a small correct vertical
slice (10–12 grammar competencies). See `docs/ROADMAP.md` §Milestone.
