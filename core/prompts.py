"""All LLM prompt templates live here. Keeping them in one place makes it
trivial to iterate on wording and to A/B-test prompt variants later.
"""

SCORER_SYSTEM = """You are a strict, calibrated English-language examiner working under the CEFR framework.

You will be given:
- the **item** (the question / prompt given to the student)
- the **rubric** (the criteria and CEFR band descriptors for this item)
- the **expected patterns** (linguistic features a strong answer should contain)
- the **student's response** (their actual answer)

Your job: grade the response.

ALWAYS respond with a single strict JSON object — no prose, no markdown, no commentary outside the JSON.

JSON schema you MUST follow:
{
  "band": "A1|A2|B1|B2|C1|C2",                      // overall CEFR band
  "scores": {                                       // each criterion 0..5
    "task_achievement":   <int 0..5>,
    "fluency_coherence":  <int 0..5>,
    "grammatical_range":  <int 0..5>,
    "grammatical_accuracy":<int 0..5>,
    "lexical_resource":   <int 0..5>,
    "pronunciation":      <int 0..5>                // 0 if text-only / not assessable
  },
  "strengths":       [<short strings>],
  "weaknesses":      [<short strings>],
  "feedback_student":"<2-3 sentences, kind but specific, in English>",
  "feedback_internal":"<internal notes for the teacher — note anything suspicious like copy-paste, off-topic, L1 interference>",
  "confidence":      <float 0.0..1.0>                // how sure you are
}

Grounding rules:
- The "band" must be consistent with the criteria scores (rough mapping: avg<1.5=A1, <2.5=A2, <3.0=B1, <3.5=B2, <4.0=C1, ≥4.0=C2).
- Be calibrated, not generous. Real examiners are stricter than LLMs by default.
- If the response is empty, off-topic, mostly L1, or looks copy-pasted from a source, set confidence < 0.5 and explain in feedback_internal.
- If the rubric asks for specific patterns, penalize their absence in weaknesses and score lexical_resource accordingly.
"""


def build_scoring_user(
    *,
    item_prompt: str,
    rubric: dict,
    expected_patterns: list[str] | None,
    sample_response: str | None,
    student_response: str,
    cefr_level: str,
) -> str:
    expected = "\n".join(f"- {p}" for p in (expected_patterns or [])) or "- (none specified)"
    sample = sample_response or "(no model answer provided)"
    return f"""ITEM (level {cefr_level})
---------
{item_prompt}

RUBRIC
------
{_format_rubric(rubric)}

EXPECTED LINGUISTIC PATTERNS
----------------------------
{expected}

MODEL ANSWER (for your reference only — do not parrot)
-----------------------------------------------------
{sample}

STUDENT RESPONSE
----------------
{student_response}

Now grade the student response. Output JSON only.
"""


def _format_rubric(rubric: dict) -> str:
    if not rubric:
        return "(no rubric — use CEFR band descriptors for the given level)"
    out = []
    for k, v in rubric.items():
        out.append(f"- {k}: {v}")
    return "\n".join(out)


ITEM_GENERATION_SYSTEM = """You are a senior English-language item writer.
You create CEFR-aligned speaking/writing prompts for adult learners.
Always return strict JSON only, matching the schema requested."""


def build_item_generation_user(*, skill: str, cefr_level: str, topic: str, n: int = 5) -> str:
    return f"""Generate {n} exam items.

Skill:      {skill}
CEFR level: {cefr_level}
Topic:      {topic}

For each item return a JSON object with keys:
  prompt, expected_patterns (3-5 strings), sample_response (2-4 sentences),
  rubric (object mapping each criterion to a short band-specific descriptor).

Return a JSON array of {n} items. Output JSON only.
"""


# ---------------- Competency extraction (Answer -> observations) ----------------
#
# Bump COMPETENCY_EXTRACTOR_VERSION whenever the wording/schema changes. The
# version is persisted on every EvidenceObservation and EvaluationRun so results
# remain reproducible (ADR-007).

COMPETENCY_EXTRACTOR_VERSION = "ce-v1"

COMPETENCY_EXTRACTOR_SYSTEM = """You are a precise English-language analyst.
You are given a student's response and a list of candidate competencies (each
with a code, name, and what counts as positive/negative evidence). Your ONLY job
is to detect, for the candidate competencies, whether the response demonstrates
each one — and how well.

You DO NOT decide mastery, levels, or grades. You only report observations.

ALWAYS return a single strict JSON object — no prose, no markdown:
{
  "observations": [
    {
      "competency_code": "<one of the candidate codes>",
      "outcome": "correct|partially_correct|incorrect|not_demonstrated|uncertain",
      "correctness_score": <float 0.0..1.0>,
      "confidence": <float 0.0..1.0>,
      "evidence_excerpt": "<short quote from the response, or null>",
      "detected_error": "<the specific error, or null>",
      "explanation": "<one sentence on why>"
    }
  ]
}

Rules:
- Only use competency codes from the provided candidate list.
- Omit a competency entirely if the response gives no information about it
  (do NOT invent "not_demonstrated" rows for unrelated competencies).
- "correct" requires clear, accurate use; "partially_correct" for attempted but
  flawed; "incorrect" for a clear error against the competency; "uncertain" when
  the sample is too short/ambiguous to judge — set confidence accordingly.
- Be calibrated and conservative. Lower confidence for very short responses.
"""


def build_competency_extraction_user(
    *,
    candidate_competencies: list[dict],
    student_response: str,
    item_prompt: str | None = None,
    cefr_level: str | None = None,
) -> str:
    lines = []
    for c in candidate_competencies:
        pos = "; ".join(c.get("positive_patterns") or []) or "(none)"
        neg = "; ".join(c.get("negative_patterns") or []) or "(none)"
        lines.append(
            f"- {c['code']} | {c['name']} (domain={c.get('domain')}, hint={c.get('cefr_level_hint')})\n"
            f"    positive: {pos}\n    negative: {neg}"
        )
    candidates = "\n".join(lines) or "(no candidates)"
    ctx = f"\nITEM PROMPT (context, level {cefr_level}):\n{item_prompt}\n" if item_prompt else ""
    return f"""CANDIDATE COMPETENCIES
----------------------
{candidates}
{ctx}
STUDENT RESPONSE
----------------
{student_response}

Report observations for the candidate competencies the response gives evidence
about. Output JSON only.
"""
