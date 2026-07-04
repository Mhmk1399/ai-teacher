"""Competency extraction engine.

Pipeline (ADR-006, ADR-007):

    language sample + candidate competencies
        -> LLM (provider interface)
        -> EvaluationRun recorded (always, success or failure)
        -> strict Pydantic validation
        -> EvidenceObservation rows (pending review), linked to source + run

Guarantees:
- Every call produces an ``EvaluationRun`` (failures are never silently dropped).
- Invalid/malformed AI output produces zero observations (cannot corrupt progress).
- Re-processing the same source with the same evaluator version does not create
  uncontrolled duplicates: prior *pending* observations for that source are
  replaced; human-reviewed ones are preserved and not duplicated.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.ai.provider import LanguageModelProvider, ProviderError
from core.competency.models import CompetencyDefinition, EvaluationRun, EvidenceObservation
from core.competency.schemas import ExtractionResult
from core.prompts import (
    COMPETENCY_EXTRACTOR_SYSTEM,
    COMPETENCY_EXTRACTOR_VERSION,
    build_competency_extraction_user,
)

log = logging.getLogger("lingua.evidence")

EVALUATOR_TYPE = "competency_extractor"
_REVIEWED = ("accepted", "rejected", "overridden")


@dataclass
class ExtractionOutcome:
    evaluation_run: EvaluationRun
    observations: list[EvidenceObservation] = field(default_factory=list)
    error: str | None = None
    skipped_unknown_codes: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error is None


def _strip_json(text: str) -> str:
    """Tolerate a code-fence wrapper but nothing else; real parsing happens after."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def extract_observations_for_answer(
    db: Session,
    provider: LanguageModelProvider,
    *,
    learner_id: int,
    candidate_competencies: list[CompetencyDefinition],
    student_response: str,
    source_type: str = "exam_answer",
    source_id: int | None = None,
    activity_type: str | None = "exam",
    context_key: str = "exam",
    modality: str = "text",
    item_prompt: str | None = None,
    cefr_level: str | None = None,
) -> ExtractionOutcome:
    """Run extraction and persist observations. Always records an EvaluationRun."""
    cand_payload = [
        {
            "code": c.code, "name": c.name, "domain": c.domain,
            "cefr_level_hint": c.cefr_level_hint,
            "positive_patterns": c.positive_patterns,
            "negative_patterns": c.negative_patterns,
        }
        for c in candidate_competencies
    ]
    system = COMPETENCY_EXTRACTOR_SYSTEM
    user = build_competency_extraction_user(
        candidate_competencies=cand_payload,
        student_response=student_response,
        item_prompt=item_prompt,
        cefr_level=cefr_level,
    )
    input_hash = hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()

    run = EvaluationRun(
        evaluator_type=EVALUATOR_TYPE,
        model_provider=provider.provider_name,
        model_name=provider.model_name,
        prompt_version=COMPETENCY_EXTRACTOR_VERSION,
        input_hash=input_hash,
        raw_input=user,
        success=False,
    )

    # 1) Call the provider.
    try:
        resp = provider.generate_json(system, user)
        run.raw_output = resp.raw_text
        run.latency_ms = resp.latency_ms
    except ProviderError as e:
        run.error = f"provider_error: {e}"
        db.add(run); db.commit(); db.refresh(run)
        log.warning("evaluation_failed run=%s err=%s", run.id, run.error)
        return ExtractionOutcome(evaluation_run=run, error=run.error)

    # 2) Parse + validate strictly. Malformed output -> failed run, no observations.
    try:
        parsed = json.loads(_strip_json(resp.raw_text))
        result = ExtractionResult.model_validate(parsed)
        run.parsed_output = result.model_dump()
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        run.error = f"schema_validation_failed: {e}"
        db.add(run); db.commit(); db.refresh(run)
        log.warning("evaluation_invalid run=%s err=%s", run.id, run.error)
        return ExtractionOutcome(evaluation_run=run, error=run.error)

    run.success = True
    db.add(run)
    db.flush()  # need run.id for FK

    # 3) Map codes -> active competency ids.
    code_to_comp = {c.code: c for c in candidate_competencies}

    # 4) Idempotency: drop prior PENDING observations for this exact source+evaluator;
    #    keep human-reviewed ones and avoid duplicating their competencies.
    reviewed_comp_ids: set[int] = set()
    if source_id is not None:
        existing = db.execute(
            select(EvidenceObservation).where(
                EvidenceObservation.source_type == source_type,
                EvidenceObservation.source_id == source_id,
                EvidenceObservation.evaluator_version == COMPETENCY_EXTRACTOR_VERSION,
            )
        ).scalars().all()
        for obs in existing:
            if obs.human_review_status in _REVIEWED:
                reviewed_comp_ids.add(obs.competency_id)
            else:
                db.delete(obs)
        db.flush()

    created: list[EvidenceObservation] = []
    skipped: list[str] = []
    for o in result.observations:
        comp = code_to_comp.get(o.competency_code)
        if comp is None:
            skipped.append(o.competency_code)
            continue
        if comp.id in reviewed_comp_ids:
            continue  # don't duplicate a human-reviewed competency for this source
        obs = EvidenceObservation(
            learner_id=learner_id,
            competency_id=comp.id,
            source_type=source_type,
            source_id=source_id,
            activity_type=activity_type,
            context_key=context_key,
            modality=modality,
            observed_text=o.evidence_excerpt,
            outcome=o.outcome,
            correctness_score=o.correctness_score,
            evaluator_confidence=o.confidence,
            evidence_weight=max(0.05, o.confidence),  # base weight; engine applies review multipliers
            detected_error=o.detected_error,
            explanation=o.explanation,
            prompt_version=COMPETENCY_EXTRACTOR_VERSION,
            evaluator_version=COMPETENCY_EXTRACTOR_VERSION,
            model_name=provider.model_name,
            evaluation_run_id=run.id,
            human_review_status="pending",
        )
        db.add(obs)
        created.append(obs)

    db.commit()
    db.refresh(run)
    for obs in created:
        db.refresh(obs)
    if skipped:
        log.info("extractor skipped unknown codes: %s", skipped)
    log.info("observations_created run=%s count=%s", run.id, len(created))
    return ExtractionOutcome(
        evaluation_run=run, observations=created, skipped_unknown_codes=skipped
    )
