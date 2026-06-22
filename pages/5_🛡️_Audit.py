"""Audit page — the PhD master's review queue.

Every flagged answer lands here. Overrides become the fine-tune dataset.
"""
from __future__ import annotations
import json
from datetime import datetime
import pandas as pd
import streamlit as st

from core.config import settings
from core.db import session_scope
from core.scoring import apply_override
from core.models import Answer, AuditLog


st.set_page_config(page_title="Audit", page_icon="🛡️", layout="wide")
st.title("🛡️ PhD Review Queue")


# ---------- Filter / queue ----------
with session_scope() as db:
    flagged = db.query(Answer).filter(Answer.flagged_for_review == True) \
                               .order_by(Answer.id.desc()).all()  # noqa: E712

st.metric("Flagged answers awaiting review", len(flagged))

if not flagged:
    st.info("🎉 Nothing flagged right now. The AI is confident on everything in the queue.")
    st.stop()

st.caption("Each row below is an answer the auto-grader was uncertain about (confidence < "
           f"{0.6:.2f}) or returned an invalid band. Override the band and criterion scores; "
           "your override becomes training data for the next model version.")


# ---------- Reviewer identity (for audit trail) ----------
reviewer_id = st.text_input("Reviewer ID", value="phd-master",
                            help="Used in the audit log and the future fine-tune dataset.")


# ---------- Render each flagged answer as a review card ----------
for ans in flagged:
    with session_scope() as db:
        ans = db.get(Answer, ans.id)
        item = ans.item
        sess = ans.session
        student = sess.student if sess else None

    with st.container(border=True):
        h1, h2, h3 = st.columns([3, 1, 1])
        h1.markdown(f"**Answer #{ans.id}** · Session #{sess.id if sess else '?'} · _{student.full_name if student else '?'}_")
        h2.markdown(f"Item: `{item.skill}/{item.cefr_level}`")
        h3.markdown(f"Confidence: **{ans.confidence:.2f if ans.confidence is not None else '—'}**")

        with st.expander("Show prompt & rubric", expanded=False):
            st.markdown(f"> **{item.prompt}**")
            if item.expected_patterns:
                st.markdown("**Expected patterns**")
                for p in item.expected_patterns:
                    st.write(f"- {p}")
            if item.rubric:
                st.markdown("**Rubric**")
                for k, v in item.rubric.items():
                    st.write(f"- **{k}**: {v}")
            if item.sample_response:
                st.markdown("**Sample response**")
                st.info(item.sample_response)

        st.markdown("**Student's answer:**")
        st.code(ans.response_text or "(empty)", language=None)

        st.markdown("**Auto-grader output:**")
        cols = st.columns(6)
        scores = ans.scores or {}
        keys = ["task_achievement", "fluency_coherence", "grammatical_range",
                "grammatical_accuracy", "lexical_resource", "pronunciation"]
        for i, k in enumerate(keys):
            cols[i].metric(k.replace("_", " ").title(), scores.get(k, "—"))
        st.write(f"**Auto band:** `{ans.band or '—'}`")
        if ans.feedback_student:
            st.info(f"To student: {ans.feedback_student}")
        if ans.feedback_internal:
            with st.expander("Internal notes from AI"):
                st.write(ans.feedback_internal)

        st.divider()
        st.markdown("#### Your override")
        with st.form(f"override_{ans.id}"):
            c1, c2 = st.columns([1, 3])
            new_band = c1.selectbox("Band", settings.CEFR_LEVELS,
                                    index=settings.CEFR_LEVELS.index(ans.band)
                                    if ans.band in settings.CEFR_LEVELS else 2,
                                    key=f"band_{ans.id}")
            new_scores_text = c2.text_area(
                "Scores (JSON)",
                value=json.dumps({k: scores.get(k, 3) for k in keys}, indent=2),
                height=120, key=f"scores_{ans.id}",
            )
            note = st.text_area("Reviewer note (why did you override?)",
                                key=f"note_{ans.id}", height=70,
                                placeholder="e.g. AI underrated grammatical range — student uses past perfect and conditionals accurately.")
            submitted = st.form_submit_button("✅ Submit override & clear flag")

            if submitted:
                try:
                    parsed = json.loads(new_scores_text)
                except Exception as e:
                    st.error(f"Scores must be valid JSON: {e}")
                    st.stop()
                with session_scope() as db:
                    apply_override(
                        db,
                        answer_id=ans.id,
                        reviewer_id=reviewer_id,
                        band=new_band,
                        scores=parsed,
                        note=note.strip(),
                    )
                st.success(f"Override saved for answer #{ans.id}.")
                st.rerun()


# ---------- Export the override dataset for fine-tuning ----------
st.divider()
st.subheader("Export fine-tune dataset")
st.caption("All reviewed answers — auto-score vs. your override — in JSONL format. Ready for "
           "QLoRA fine-tuning of the local model.")
with session_scope() as db:
    reviewed = db.query(Answer).filter(Answer.reviewed_at.isnot(None)) \
                                .order_by(Answer.reviewed_at.desc()).all()  # noqa: E712
    n = len(reviewed)
st.metric("Reviewed answers in dataset", n)

if n:
    out_lines = []
    with session_scope() as db:
        for a in reviewed:
            item = db.get(__import__('core.models', fromlist=['Item']).Item, a.item_id)
            line = {
                "answer_id": a.id,
                "item_prompt": item.prompt,
                "cefr_level": item.cefr_level,
                "skill": item.skill,
                "rubric": item.rubric,
                "expected_patterns": item.expected_patterns,
                "student_response": a.response_text,
                "auto_band": a.band,
                "auto_scores": a.scores,
                "human_band": a.reviewer_override_band,
                "human_scores": a.reviewer_override_scores,
                "human_note": a.reviewer_note,
                "reviewer_id": a.reviewer_id,
                "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
            }
            out_lines.append(json.dumps(line, ensure_ascii=False))
    st.download_button(
        "⬇️ Download JSONL",
        data="\n".join(out_lines),
        file_name=f"finetune_{datetime.now():%Y%m%d_%H%M}.jsonl",
        mime="application/x-ndjson",
    )
