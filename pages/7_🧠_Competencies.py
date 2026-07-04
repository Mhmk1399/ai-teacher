"""Competencies page — catalog, evidence extraction, and the expert review queue.

This is the UI for the "Answer -> Living Competency Projection" slice:
- seed/inspect the grammar competency catalog;
- run competency extraction on an existing answer (local Ollama by default);
- inspect the learner's competency map + derived CEFR projection;
- accept / reject / override AI observations (rebuilds the projection).

All mastery/CEFR logic lives in core.progress (deterministic); this page only
orchestrates and displays.
"""
from __future__ import annotations

import streamlit as st

from core.ai.ollama_provider import OllamaProvider
from core.competency.models import (
    CEFRProjection, CompetencyDefinition, EvidenceObservation, LearnerCompetency,
)
from core.competency.repository import get_active_competencies, review_observation
from core.db import session_scope
from core.evidence.pipeline import process_answer
from core.llm import get_client
from core.models import Answer, ExamSession, Item, Student
from core.progress.cefr import compute_cefr
from core.progress.engine import rebuild_learner
from core.seed import load_competency_catalog

st.set_page_config(page_title="Competencies", page_icon="🧠", layout="wide")
st.title("🧠 Competencies & Evidence")
st.caption(
    "Competencies are the source of truth; CEFR is a derived projection. The LLM "
    "only proposes observations — a deterministic engine decides mastery."
)

tab_catalog, tab_extract, tab_review = st.tabs(
    ["📚 Catalog", "🔬 Extract from answer", "🧑‍⚖️ Learner map & review"]
)

# ---------------- Catalog ----------------
with tab_catalog:
    with session_scope() as db:
        comps = get_active_competencies(db)
        rows = [
            {"code": c.code, "name": c.name, "domain": c.domain,
             "level_hint": c.cefr_level_hint, "evidence_required": c.evidence_required,
             "accuracy_threshold": c.accuracy_threshold,
             "contexts_required": c.contexts_required}
            for c in comps
        ]
    c1, c2 = st.columns([1, 4])
    if c1.button("🌱 Seed grammar catalog", help="Idempotent: safe to click repeatedly"):
        with session_scope() as db:
            n = load_competency_catalog(db, "grammar")
        st.success(f"Catalog seeded/validated ({n} competencies).")
        st.rerun()
    c2.metric("Active competencies", len(rows))
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No competencies yet — click **Seed grammar catalog**.")

# ---------------- Extraction ----------------
with tab_extract:
    health = get_client().health()
    if not health.get("reachable"):
        st.warning("Ollama is not reachable. Extraction needs a local model "
                   "(`ollama serve`). The rest of the app still works.")
    with session_scope() as db:
        answers = (
            db.query(Answer).order_by(Answer.id.desc()).limit(50).all()
        )
        answer_opts = {
            f"#{a.id} · {(a.response_text or '')[:60]}…": a.id for a in answers
        }
    if not answer_opts:
        st.info("No answers yet. Run an exam session first.")
    else:
        label = st.selectbox("Answer to analyze", list(answer_opts.keys()))
        if st.button("🔬 Extract competency evidence", type="primary"):
            answer_id = answer_opts[label]
            try:
                with session_scope() as db:
                    res = process_answer(db, OllamaProvider(), answer_id, domain="grammar")
                    ok = res.outcome.success
                    err = res.outcome.error
                    n_obs = len(res.outcome.observations)
                if ok:
                    st.success(f"Created {n_obs} observation(s) and rebuilt the learner map.")
                else:
                    st.error(f"Extraction did not update progress: {err}")
            except Exception as e:  # provider/transport issues surface here
                st.error(f"Extraction failed: {e}")

# ---------------- Learner map & review ----------------
with tab_review:
    with session_scope() as db:
        students = db.query(Student).order_by(Student.full_name).all()
        student_opts = {f"{s.full_name} (#{s.id})": s.id for s in students}
    if not student_opts:
        st.info("No students yet.")
        st.stop()

    who = st.selectbox("Learner", list(student_opts.keys()))
    learner_id = student_opts[who]

    colA, colB = st.columns(2)
    if colA.button("🔁 Rebuild projections"):
        with session_scope() as db:
            rebuild_learner(db, learner_id)
        st.success("Rebuilt learner competency projections.")
        st.rerun()

    # CEFR projection (derived).
    with session_scope() as db:
        cefr = compute_cefr(db, learner_id)
    colB.metric("Overall CEFR (derived)", cefr.overall_level or "below A1",
                help=cefr.explanation)
    st.caption(cefr.explanation)

    # Learner competency states.
    with session_scope() as db:
        lcs = (
            db.query(LearnerCompetency, CompetencyDefinition)
            .join(CompetencyDefinition,
                  CompetencyDefinition.id == LearnerCompetency.competency_id)
            .filter(LearnerCompetency.learner_id == learner_id)
            .all()
        )
        lc_rows = [
            {"code": c.code, "name": c.name, "state": lc.state,
             "valid_evidence": lc.valid_evidence_count,
             "contexts": lc.distinct_context_count,
             "weighted_accuracy": lc.weighted_accuracy, "confidence": lc.confidence,
             "reason": lc.reason}
            for lc, c in lcs
        ]
    st.subheader("Competency map")
    if lc_rows:
        st.dataframe(lc_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No projections yet for this learner. Extract evidence first.")

    # Observation review queue.
    st.subheader("Evidence observations")
    with session_scope() as db:
        obs_join = (
            db.query(EvidenceObservation, CompetencyDefinition)
            .join(CompetencyDefinition,
                  CompetencyDefinition.id == EvidenceObservation.competency_id)
            .filter(EvidenceObservation.learner_id == learner_id)
            .order_by(EvidenceObservation.id.desc())
            .all()
        )
        obs_view = [
            {"id": o.id, "code": c.code, "outcome": o.outcome,
             "correctness": o.correctness_score, "confidence": o.evaluator_confidence,
             "context": o.context_key, "status": o.human_review_status,
             "excerpt": o.observed_text, "error": o.detected_error}
            for o, c in obs_join
        ]

    if not obs_view:
        st.info("No observations yet.")
    else:
        reviewer = st.text_input("Reviewer ID", value="phd-master")
        for ov in obs_view:
            with st.expander(
                f"#{ov['id']} · {ov['code']} · {ov['outcome']} "
                f"(conf {ov['confidence']:.2f}) · [{ov['status']}]"
            ):
                st.write(f"**Excerpt:** {ov['excerpt'] or '—'}")
                if ov["error"]:
                    st.write(f"**Detected error:** {ov['error']}")
                b1, b2, b3 = st.columns(3)
                if b1.button("✅ Accept", key=f"acc{ov['id']}"):
                    with session_scope() as db:
                        review_observation(db, ov["id"], status="accepted",
                                           reviewer_id=reviewer)
                    st.rerun()
                if b2.button("❌ Reject", key=f"rej{ov['id']}"):
                    with session_scope() as db:
                        review_observation(db, ov["id"], status="rejected",
                                           reviewer_id=reviewer)
                    st.rerun()
                new_outcome = b3.selectbox(
                    "Override outcome", ["", "correct", "partially_correct",
                                         "incorrect", "not_demonstrated"],
                    key=f"ovsel{ov['id']}")
                if b3.button("✏️ Override", key=f"ov{ov['id']}") and new_outcome:
                    score = {"correct": 1.0, "partially_correct": 0.5,
                             "incorrect": 0.0, "not_demonstrated": 0.0}[new_outcome]
                    with session_scope() as db:
                        review_observation(
                            db, ov["id"], status="overridden", reviewer_id=reviewer,
                            override={"outcome": new_outcome, "correctness_score": score})
                    st.rerun()
