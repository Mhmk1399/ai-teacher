# Current Architecture (MVP)

## Component view

```mermaid
flowchart TD
  subgraph UI["Streamlit (presentation + application logic mixed)"]
    APP[app.py]
    P1[1 Students] & P2[2 Items] & P3[3 Exams] & P4[4 Sessions] & P5[5 Audit] & P6[6 Score Lab]
  end

  subgraph CORE["core/"]
    CFG[config.py settings] --> DB[db.py engine/session]
    M[models.py ORM]
    SC[scoring.py]
    EE[exam_engine.py]
    PR[prompts.py]
    LLM[llm.py OllamaClient]
    SEED[seed.py]
  end

  P1 & P2 & P3 & P5 -->|session_scope + ORM| DB
  P4 --> SC
  P6 --> SC
  SC --> PR
  SC --> LLM
  SC --> M
  EE --> M
  DB --- M
  LLM -->|HTTP /api/chat,/api/generate| OLL[(Ollama local)]
  DB --- SQL[(SQLite data/lingua.db)]
```

## Existing data model

```mermaid
erDiagram
  STUDENT ||--o{ EXAM_SESSION : has
  EXAM ||--o{ EXAM_SESSION : runs
  EXAM_SESSION ||--o{ ANSWER : contains
  ITEM ||--o{ ANSWER : answered_by
  STUDENT {
    int id PK
    string external_id
    string full_name
    string l1
    string cefr_level "stored directly (MVP)"
    string goal
  }
  ITEM {
    int id PK
    string code
    string skill
    string cefr_level
    string topic
    text prompt
    json expected_patterns
    json rubric
    bool active
  }
  EXAM {
    int id PK
    string name
    string cefr_level
    json skills
    int item_count
  }
  EXAM_SESSION {
    int id PK
    int exam_id FK
    int student_id FK
    string status
    string final_band
  }
  ANSWER {
    int id PK
    int session_id FK
    int item_id FK
    text response_text
    json raw_llm_output
    string band
    json scores
    float confidence
    bool flagged_for_review
    string reviewer_override_band
  }
  AUDIT_LOG {
    int id PK
    string actor
    string action
    string entity_type
    int entity_id
    json payload
  }
```

## Existing scoring flow

```mermaid
sequenceDiagram
  participant U as Expert (Sessions/Score Lab)
  participant SC as core.scoring
  participant PR as core.prompts
  participant LLM as OllamaClient
  participant DB as SQLite

  U->>SC: score_answer(db, answer_id)
  SC->>DB: load Answer + Item
  SC->>PR: build_scoring_user(item, response)
  SC->>LLM: score(SCORER_SYSTEM, user)  [JSON mode]
  alt LLM error
    LLM-->>SC: LLMError
    SC->>DB: record error, confidence=0, flag for review, AuditLog(score_error)
  else success
    LLM-->>SC: strict JSON {band, scores, confidence, feedback...}
    SC->>DB: persist band/scores/confidence; flag if confidence < 0.6 or band missing
    SC->>DB: AuditLog(auto_score)
  end
  U->>SC: apply_override(...) (when AI is wrong)
  SC->>DB: store reviewer override + AuditLog(override_score)
```

## Key behaviors & constraints

- `expire_on_commit=False` is intentional for Streamlit's re-run model.
- SQLite uses `check_same_thread=False`.
- Confidence threshold for review is `0.6` (`core/scoring.CONFIDENCE_THRESHOLD`).
- `_norm_band` defensively normalizes the model's band string to A1–C2.

## Known issues (see REPOSITORY_AUDIT.md §4)

- `core/llm.chat` retry loop never retries (dead code after `break`).
- `core/exam_engine.generate_exam` doesn't persist an exam→item snapshot.
- No migrations/tests before this milestone; UI reaches into ORM directly.
