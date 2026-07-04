# Data Model

The existing assessment tables (`students`, `items`, `exams`, `exam_sessions`,
`answers`, `audit_log`) are **unchanged**. This milestone adds new, additive
tables for the competency domain. CEFR remains on `students.cefr_level` for
backward compatibility but is **no longer authoritative** (ADR-002).

## New entities (this milestone)

```mermaid
erDiagram
  COMPETENCY_DEFINITION ||--o{ COMPETENCY_PREREQUISITE : "has edges"
  COMPETENCY_DEFINITION ||--o{ EVIDENCE_OBSERVATION : "observed as"
  COMPETENCY_DEFINITION ||--o{ LEARNER_COMPETENCY : "projected as"
  STUDENT ||--o{ EVIDENCE_OBSERVATION : "produces"
  STUDENT ||--o{ LEARNER_COMPETENCY : "has"
  STUDENT ||--o{ CEFR_PROJECTION : "has"
  ANSWER ||--o{ EVIDENCE_OBSERVATION : "source_id (exam_answer)"
  EVALUATION_RUN ||--o{ EVIDENCE_OBSERVATION : "produced by"

  COMPETENCY_DEFINITION {
    int id PK
    string code UK "e.g. GR-B1-09"
    string name
    string domain "grammar/vocab/..."
    string subdomain
    string skill "production/reception/..."
    text description
    string cefr_level_hint
    json performance_descriptors
    json positive_patterns
    json negative_patterns
    json exceptions
    int evidence_required
    float accuracy_threshold
    int contexts_required
    bool active
    int version
    string created_by
  }
  COMPETENCY_PREREQUISITE {
    int id PK
    int competency_id FK
    int prerequisite_competency_id FK
    string relationship_type "requires/supports"
    float weight
  }
  EVIDENCE_OBSERVATION {
    int id PK
    int learner_id FK
    int competency_id FK
    string source_type "exam_answer/conversation_turn/..."
    int source_id
    string activity_type
    string context_key "diversity bucket"
    string modality "text/voice"
    text observed_text
    string outcome "correct/partially_correct/incorrect/not_demonstrated/uncertain"
    float correctness_score
    float evaluator_confidence
    float evidence_weight
    text detected_error
    text explanation
    string prompt_version
    string evaluator_version
    string model_name
    int evaluation_run_id FK
    string human_review_status "pending/accepted/rejected/overridden"
    json human_override
    datetime observed_at
  }
  LEARNER_COMPETENCY {
    int id PK
    int learner_id FK
    int competency_id FK
    string state "not_observed/emerging/developing/proficient/mastered/needs_review/regressing"
    int evidence_count
    int valid_evidence_count
    int distinct_context_count
    float accuracy
    float weighted_accuracy
    float confidence
    text reason "why this state"
    datetime first_observed_at
    datetime last_observed_at
    datetime mastered_at
    string algorithm_version
    datetime computed_at
  }
  EVALUATION_RUN {
    int id PK
    string evaluator_type
    string model_provider
    string model_name
    string prompt_version
    string input_hash
    text raw_input
    text raw_output
    json parsed_output
    int latency_ms
    bool success
    text error
  }
  CEFR_PROJECTION {
    int id PK
    int learner_id FK
    string grammar_level
    string vocabulary_level
    string speaking_level
    string listening_level
    string reading_level
    string writing_level
    string communication_level
    string overall_level
    float confidence
    text explanation
    string algorithm_version
    datetime computed_at
  }
```

## Constraints & indexes

- `competency_definitions.code` is **unique** (catalog integrity).
- `competency_prerequisites`: unique `(competency_id, prerequisite_competency_id)`;
  both FK → `competency_definitions.id`; self-reference forbidden in validation.
- `evidence_observations`: indexes on `(learner_id, competency_id)`,
  `source_type, source_id`; FK `learner_id → students.id`,
  `competency_id → competency_definitions.id`,
  `evaluation_run_id → evaluation_runs.id`.
- `learner_competencies`: **unique** `(learner_id, competency_id)` — it is a
  projection (one row per learner×competency), rebuildable from observations.
- All timestamps default to UTC; all JSON columns hold lists/objects only.

## Why `LearnerCompetency` and `CEFRProjection` are projections, not truth

They are **derived**: a pure function of (valid observations, competency
thresholds, algorithm version). They can be dropped and rebuilt with no data
loss. Raw truth lives in `evidence_observations` (+ human overrides). This is
what makes every learner state **traceable** and **reproducible** (ADR-005).

## Evidence weighting (summary; full algorithm in progress engine)

`evidence_weight` combines evaluator confidence, human-review status
(human-accepted > AI-only; rejected = excluded), recency, and modality. The
deterministic engine then requires, for mastery:

```
valid_evidence_count   >= competency.evidence_required
AND weighted_accuracy  >= competency.accuracy_threshold
AND distinct_context   >= competency.contexts_required
AND projection_confidence >= configured_minimum
```

One correct answer can never satisfy these (count and context gates). See
`core/progress/engine.py` and `docs/decisions/ADR-005`.

## Migration / rollback

- Baseline migration captures the existing 6 tables (already stamped on the live
  DB so current data is untouched).
- The milestone migration is **additive** (only `CREATE TABLE`/index). Its
  `downgrade()` drops only the new tables. SQLite-safe via `render_as_batch`;
  PostgreSQL-compatible types. See `docs/ROADMAP.md` §Migration commands.
