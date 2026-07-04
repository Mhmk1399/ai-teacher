# Target Architecture

A **modular monolith** (no microservices yet). The learner knowledge graph is
represented relationally (competencies + prerequisite edge table), not in a graph
database. We migrate toward the structure below **incrementally**, preserving
working imports — no big-bang relocation.

## Layered view

```mermaid
flowchart TD
  subgraph Presentation
    ST[Streamlit admin] 
    API[Future REST/WebSocket API]
    NEXT[Future student app]
  end
  subgraph Application["Application services (UI-independent)"]
    SVC[student / assessment / evidence / progress / placement / lesson / review services]
  end
  subgraph Domain
    CD[Competency definitions]
    EV[Evidence observations]
    LC[Learner competency state]
    MR[Mastery rules]
    CP[CEFR projection]
    LP[Learning plans]
  end
  subgraph AI["AI layer"]
    PI[Provider interface]
    SCO[Scoring evaluator]
    DET[Competency detector]
    ERR[Error analyzer]
    GEN[Lesson generator]
    REG[Prompt registry]
  end
  subgraph Infra["Infrastructure"]
    REPO[SQLAlchemy repositories]
    DBI[(SQLite / PostgreSQL)]
    OLL[Ollama adapter]
    FAKE[Fake adapter - tests]
    LOG[Logging / config]
  end

  Presentation --> Application
  Application --> Domain
  Application --> AI
  AI --> PI --> OLL
  PI --> FAKE
  Application --> Infra
  Domain --> Infra
  REPO --> DBI
```

## Evidence flow (new)

```mermaid
flowchart LR
  SRC[Answer / conversation / writing / lesson activity] --> CAND[Candidate competency selection]
  CAND --> AI[AI competency detector - schema-constrained]
  AI --> VAL[Pydantic validation]
  VAL -->|valid| OBS[(EvidenceObservation)]
  VAL -->|invalid| RUN[(EvaluationRun: failure recorded)]
  AI --> RUN2[(EvaluationRun: prompt+model version, latency)]
  OBS --> REV{Expert review}
  REV -->|accept/reject/override| OBS
```

## Competency projection flow (new)

```mermaid
flowchart LR
  OBS[(EvidenceObservation*)] --> ENG[Deterministic progress engine]
  ENG -->|per competency| LC[(LearnerCompetency state + reason)]
  LC --> PROJ[CEFR projection per skill + overall]
  PROJ --> CEFR[(CEFRProjection snapshot)]
  note["Rebuildable: projection is a pure function of valid observations + thresholds + algorithm_version"]
  ENG -.-> note
```

## Continuous learning loop (target)

```mermaid
flowchart LR
  LESSON[Lesson] --> INT[Interaction]
  INT --> ANA[Language analysis]
  ANA --> OBS[Competency observations]
  OBS --> UPD[Learner profile update]
  UPD --> NEXT[Next lesson generation]
  NEXT --> LESSON
```

## Target folder structure (incremental destination)

```
src/
  domain/        competencies/ evidence/ learners/ assessment/ progress/ lessons/
  application/   services/ commands/ queries/ dto/
  infrastructure/database/ repositories/ ai_providers/ storage/
  ai/            prompts/ schemas/ evaluators/ generators/
  interfaces/    streamlit/ api/
tests/           unit/ integration/ contract/ evaluation/
migrations/  data/competency_catalogs/  docs/decisions/
```

### Interim mapping (this milestone)

We do **not** relocate yet. The new code lives in additive packages under
`core/` that mirror the destination layers, so a later move is mechanical:

| Target layer | Interim location (this milestone) |
|---|---|
| domain (competency/evidence/progress) | `core/competency/`, `core/evidence/`, `core/progress/` |
| AI provider interface + adapters | `core/ai/` |
| infrastructure repositories | `core/competency/repository.py` |
| interfaces | existing `pages/`, new `pages/7_🧠_Competencies.py` |

## Design principles

- Mastery and CEFR logic live in **deterministic, testable domain code** — never
  in prompts or Streamlit.
- AI is always behind a `LanguageModelProvider` interface; tests use a fake.
- Projections are **pure functions** of valid observations → fully rebuildable.
- Everything important is **versioned** and **traceable**.
