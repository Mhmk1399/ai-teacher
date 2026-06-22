"""LLM-based scoring engine with strict JSON, confidence flagging, and audit hooks."""
from __future__ import annotations
from datetime import datetime
import json

from sqlalchemy.orm import Session

from core.models import Answer, Item, AuditLog
from core.prompts import SCORER_SYSTEM, build_scoring_user
from core.llm import get_client, LLMError


# If confidence is below this, we flag for human review.
CONFIDENCE_THRESHOLD = 0.6


def score_response_for_item(item: Item, student_response: str) -> dict:
    """Run the scorer for a response against a single item without saving it."""
    client = get_client()
    user = build_scoring_user(
        item_prompt=item.prompt,
        rubric=item.rubric or {},
        expected_patterns=item.expected_patterns,
        sample_response=item.sample_response,
        student_response=student_response,
        cefr_level=item.cefr_level,
    )
    return client.score(SCORER_SYSTEM, user)


def score_answer(db: Session, answer_id: int) -> Answer:
    """Score an answer in place. Returns the Answer with new fields populated."""
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise ValueError(f"No Answer with id={answer_id}")
    item = db.get(Item, answer.item_id)
    if item is None:
        raise ValueError(f"Answer {answer_id} references missing item {answer.item_id}")

    try:
        result = score_response_for_item(item, answer.response_text)
    except LLMError as e:
        # We never want a transient LLM error to crash the session — record it.
        answer.raw_llm_output = {"error": str(e)}
        answer.confidence = 0.0
        answer.flagged_for_review = True
        answer.feedback_internal = f"LLM scoring failed: {e}"
        db.add(AuditLog(actor="scorer", action="score_error",
                        entity_type="answer", entity_id=answer.id,
                        payload={"error": str(e)}))
        db.commit()
        return answer

    # Parse + persist.
    answer.raw_llm_output = result
    answer.band = _norm_band(result.get("band"))
    answer.scores = result.get("scores") or {}
    answer.feedback_student = result.get("feedback_student") or ""
    answer.feedback_internal = result.get("feedback_internal") or ""
    answer.confidence = float(result.get("confidence") or 0.0)
    answer.flagged_for_review = (answer.confidence < CONFIDENCE_THRESHOLD) or answer.band is None

    db.add(AuditLog(actor="scorer", action="auto_score",
                    entity_type="answer", entity_id=answer.id,
                    payload={"band": answer.band, "confidence": answer.confidence}))
    db.commit()
    db.refresh(answer)
    return answer


def apply_override(
    db: Session,
    *,
    answer_id: int,
    reviewer_id: str,
    band: str,
    scores: dict,
    note: str,
) -> Answer:
    """PhD master overrides an auto-grade. This is the gold for future fine-tuning."""
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise ValueError(f"No Answer with id={answer_id}")

    answer.reviewer_override_band = _norm_band(band)
    answer.reviewer_override_scores = scores
    answer.reviewer_note = note
    answer.reviewer_id = reviewer_id
    answer.reviewed_at = datetime.utcnow()
    answer.flagged_for_review = False  # resolved

    db.add(AuditLog(actor=reviewer_id, action="override_score",
                    entity_type="answer", entity_id=answer.id,
                    payload={"band": band, "scores": scores, "note": note}))
    db.commit()
    db.refresh(answer)
    return answer


def _norm_band(b: str | None) -> str | None:
    if not b:
        return None
    b = b.strip().upper()
    # Strip CEFR- prefix or "Band X" chatter.
    for prefix in ("CEFR ", "BAND "):
        if b.startswith(prefix):
            b = b[len(prefix):]
    if b in {"A1", "A2", "B1", "B2", "C1", "C2"}:
        return b
    # Try last token.
    for tok in reversed(b.split()):
        if tok in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            return tok
    return None
