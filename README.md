# Lingua Nova — Exam Machine (MVP)

A local, privacy-first English exam engine. The PhD master owns the content, sets student levels, generates exams, and audits the AI's grading. Everything runs on a local LLM via Ollama — no API keys, no data leaving your machine.

## Phase 1 (this MVP, text-only)

1. PhD master authors **items** (questions + rubric + sample answer + expected patterns)
2. PhD master manages **students** (CSV import, set CEFR level A1→C2)
3. PhD master assembles **exams** from items by level + skill
4. Student runs a **session** (text-based — student types answers; voice coming in Phase 2)
5. Local LLM **scores** every answer with strict JSON output, per-criterion scores, and a confidence flag
6. PhD master reviews **flagged** answers in the **audit queue**, overrides when wrong
7. Overrides auto-export to **JSONL fine-tune dataset** for the next model version

## Phase 2 (next)

- Voice loop: Whisper ASR + Piper TTS (works with the same data model)
- Concurrent-validity study (compare our scores against real IELTS mocks)
- The 4 specialized AI teachers (Communicative / Grammar / Narrative / Task-Based)

---

## Setup

### 1. Prerequisites

- Linux (or macOS / WSL2)
- NVIDIA GPU with ≥ 12 GB VRAM recommended
- Python 3.10+
- [Ollama](https://ollama.com/download) installed and running

### 2. Install Ollama + pull the model

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama serve           # leave running in another terminal

# Pull the default model — adjust if your GPU is tighter
ollama pull qwen2.5:14b-instruct-q4_K_M
```

If 14B is too heavy for your GPU, pull `qwen2.5:7b-instruct-q4_K_M` and update `.env`.

### 3. Install Python deps

```bash
cd lingua-nova
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env if you want a different model
```

### 4. Smoke-test Ollama connectivity

```bash
python scripts/test_ollama.py
```

You should see `✅ Smoke test passed.`

### 5. Launch the dashboard

```bash
./run.sh
```

Open `http://localhost:8501` in your browser.

---

## First-time workflow

1. **Students** page → paste a CSV of your 600 students. Required columns:
   `full_name, external_id, l1, cefr_level, goal, notes`
2. **Students** page → set the CEFR level for each student (or use the bulk-update box).
3. **Items** page → add exam items. A few samples are auto-seeded from `data/seeds/sample_items.json`.
4. **Exams** page → assemble an exam template (e.g. "B1 Speaking diagnostic v1", 5 items).
5. **Sessions** page → pick a student, pick the exam, click **Start session**. Type the student's answer, click **Save & score**. Repeat for each item.
6. **Audit** page → review flagged answers, override when the AI is wrong, export the JSONL dataset for fine-tuning.

---

## Project layout

```
lingua-nova/
├── app.py                       # Home / overview
├── pages/
│   ├── 1_📚_Students.py        # CSV import, level setting
│   ├── 2_✍️_Items.py            # Author exam questions
│   ├── 3_🧪_Exams.py            # Assemble exam templates
│   ├── 4_🎤_Sessions.py         # Run a session with a student
│   └── 5_🛡️_Audit.py            # Review & override queue + fine-tune export
├── core/
│   ├── config.py                # env loader
│   ├── db.py                    # SQLAlchemy engine + session
│   ├── models.py                # ORM (students, items, exams, sessions, answers, audit)
│   ├── llm.py                   # Ollama HTTP client (chat, JSON mode, health)
│   ├── prompts.py               # All LLM prompt templates
│   ├── scoring.py               # Score → strict JSON → confidence flag
│   ├── exam_engine.py           # Generate exam templates
│   └── seed.py                  # Load sample_items.json
├── data/
│   ├── lingua.db                # SQLite (auto-created, gitignored)
│   └── seeds/sample_items.json  # Starter items
├── scripts/test_ollama.py       # Smoke test
├── requirements.txt
├── .env.example
├── run.sh
└── README.md
```

---

## Data model (the audit trail is the moat)

| Table | Purpose |
|---|---|
| `students` | The 600 students + their CEFR level (set by PhD master) |
| `items` | Exam questions with prompt, rubric, sample response, expected patterns |
| `exams` | Templates: name + level + skills + N items |
| `exam_sessions` | One student's run of an exam |
| `answers` | One student response + auto-grade + (later) reviewer override |
| `audit_log` | Append-only. Overrides go here → becomes fine-tune data |

The two key design choices:
1. **Every auto-grade has a confidence flag.** Below 0.6 → routed to PhD.
2. **Every override is logged with the same schema as the auto-grade.** That's what makes the system improvable.

---

## Tuning notes

- Confidence threshold (`CONFIDENCE_THRESHOLD` in `core/scoring.py`) — start at 0.6, raise it as your model gets better.
- Model name (`OLLAMA_MODEL` in `.env`) — `qwen2.5:14b-instruct-q4_K_M` is the recommended starting point for an English exam-scorer on a single ≥ 12 GB GPU. For tighter hardware: `qwen2.5:7b-instruct-q4_K_M` or `llama3.1:8b-instruct-q4_0`.
- Temperature — the scorer uses 0.2 by default. Lower (0.0) = more consistent, higher (0.4) = more "creative" feedback.

---

## Phase 2 — Voice (when you're ready)

- Replace the `text_area` in `pages/4_🎤_Sessions.py` with `streamlit-audio-recorder` or a small HTML mic widget.
- Send recorded WAV to `faster-whisper` for transcription → same `score_answer()` pipeline.
- Use `piper` TTS to play the item prompt aloud before recording.

Everything in the data model is already voice-ready (`format='voice'`, `response_audio_path`).
