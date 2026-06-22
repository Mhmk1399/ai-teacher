"""Sessions page — run an exam with a student (text-based for MVP).

In Phase 2 this page adds a microphone recorder (Whisper ASR → text) and a TTS voice
for prompts. The data model already supports it.
"""
from __future__ import annotations
from datetime import datetime
import pandas as pd
import streamlit as st

from core.config import settings
from core.db import session_scope
from core.exam_engine import items_for_exam
from core.scoring import score_answer
from core.models import Exam, Student, ExamSession, Answer, Item, AuditLog


def _median_band(bands: list[str]) -> str:
    order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    inv = {v: k for k, v in order.items()}
    nums = sorted(order[b] for b in bands if b in order)
    if not nums:
        return "—"
    mid = nums[len(nums) // 2]
    return inv[mid]


def _render_answer_result(ans: Answer):
    band = ans.reviewer_override_band or ans.band or "—"
    confidence = f"{ans.confidence:.2f}" if ans.confidence is not None else "—"
    flagged = "🚩 FLAGGED" if ans.flagged_for_review else ""
    st.markdown(f"**Band:** `{band}` · **Confidence:** {confidence} · {flagged}")

    scores = ans.reviewer_override_scores or ans.scores or {}
    if scores:
        s_cols = st.columns(min(6, len(scores)))
        for i, (k, v) in enumerate(scores.items()):
            s_cols[i % len(s_cols)].metric(k.replace("_", " ").title(), v)

    if ans.feedback_student:
        st.markdown("**Feedback to student:**")
        st.info(ans.feedback_student)
    if ans.feedback_internal:
        with st.expander("Internal notes (PhD only)"):
            st.write(ans.feedback_internal)

    if ans.reviewer_note:
        st.markdown(f"**PhD override:** _{ans.reviewer_note}_  · by `{ans.reviewer_id}`")
    if ans.reviewed_at:
        st.caption(f"Reviewed at {ans.reviewed_at:%Y-%m-%d %H:%M}")

    # Rescore button
    if st.button("🔄 Rescore", key=f"rescore_{ans.id}"):
        with session_scope() as db:
            score_answer(db, ans.id)
        st.success("Rescored.")
        st.rerun()


st.set_page_config(page_title="Sessions", page_icon="🎤", layout="wide")
st.title("🎤 Exam Sessions")

st.caption(f"Phase **{settings.PHASE}** · "
           + ("text-only mode (typing answers); voice (Whisper+TTS) coming in Phase 2."
              if settings.PHASE == 1 else
              "voice mode — microphone recorder active (Phase 2 work)."))


# ============================================================
# START a new session
# ============================================================
st.subheader("Start a new session")

with session_scope() as db:
    students = db.query(Student).order_by(Student.full_name).all()
    exams = db.query(Exam).order_by(Exam.id.desc()).all()

if not students:
    st.warning("Add students first (Students page).")
    st.stop()
if not exams:
    st.warning("Create an exam template first (Exams page).")
    st.stop()

c1, c2 = st.columns(2)
student = c1.selectbox("Student *",
                       options=students,
                       format_func=lambda s: f"{s.full_name} · {s.cefr_level} ({s.external_id or 'no id'})")
exam = c2.selectbox("Exam *",
                    options=exams,
                    format_func=lambda e: f"#{e.id} · {e.name} ({e.cefr_level})")

if st.button("▶️ Start session"):
    with session_scope() as db:
        s = ExamSession(student_id=student.id, exam_id=exam.id, status="open")
        db.add(s)
        db.flush()
        db.add(AuditLog(actor="phd", action="start_session",
                        entity_type="session", entity_id=s.id,
                        payload={"student_id": student.id, "exam_id": exam.id}))
    st.success(f"Session #{s.id} started. Scroll down to answer items.")
    st.session_state["active_session_id"] = s.id
    st.rerun()


# ============================================================
# ACTIVE session runner
# ============================================================

active_id = st.session_state.get("active_session_id")
# Pick up most recent open session if none pinned
if not active_id:
    with session_scope() as db:
        latest = db.query(ExamSession).filter(ExamSession.status == "open") \
                                       .order_by(ExamSession.id.desc()).first()
        if latest:
            active_id = latest.id
            st.session_state["active_session_id"] = active_id

if active_id:
    st.divider()
    st.subheader(f"Active session: #{active_id}")

    with session_scope() as db:
        sess = db.get(ExamSession, active_id)
        if sess is None:
            st.error("Session not found.")
            st.stop()
        exam = db.get(Exam, sess.exam_id)
        student = db.get(Student, sess.student_id)
        items = items_for_exam(db, exam)
        answers = {a.item_id: a for a in sess.answers}

    st.write(f"**Student:** {student.full_name} · CEFR target **{exam.cefr_level}**")
    st.write(f"**Exam:** #{exam.id} · {exam.name}")

    if not items:
        st.error("No active items match this exam. Add items or change the exam.")
        st.stop()

    # Render each item as an answer card
    for idx, item in enumerate(items, start=1):
        ans = answers.get(item.id)
        with st.container(border=True):
            st.markdown(f"**Item {idx} / {len(items)}** · `{item.skill}` · `{item.cefr_level}` · _{item.topic}_")
            st.markdown(f"> {item.prompt}")
            with st.expander("Show expected patterns / sample / rubric", expanded=False):
                if item.expected_patterns:
                    st.markdown("**Expected patterns**")
                    for p in item.expected_patterns:
                        st.write(f"- {p}")
                if item.sample_response:
                    st.markdown("**Sample response**")
                    st.info(item.sample_response)
                if item.rubric:
                    st.markdown("**Rubric**")
                    for k, v in item.rubric.items():
                        st.write(f"- **{k}**: {v}")

            # Answer input / display
            if ans is None:
                # Not yet answered
                txt = st.text_area("Student answer", key=f"resp_{item.id}",
                                   height=120,
                                   placeholder="Type the student's answer here. "
                                               "(In Phase 2 the student's voice is captured by the mic and transcribed.)")
                c_a, c_b = st.columns([1, 5])
                if c_a.button("💾 Save & score", key=f"save_{item.id}"):
                    if not txt.strip():
                        st.warning("Type something first.")
                    else:
                        with session_scope() as db:
                            ans = Answer(session_id=active_id, item_id=item.id, response_text=txt.strip())
                            db.add(ans)
                            db.flush()
                            answer_id = ans.id
                            db.add(AuditLog(actor="phd", action="save_answer",
                                            entity_type="answer", entity_id=ans.id, payload={}))
                        # Score outside session (LLM call)
                        with session_scope() as db:
                            score_answer(db, answer_id)
                        st.success("Saved & scored. Scroll down / refresh.")
                        st.rerun()
            else:
                # Already answered — show result
                _render_answer_result(ans)


    # Finish session
    if st.button("🏁 Finish session", type="primary"):
        with session_scope() as db:
            sess = db.get(ExamSession, active_id)
            sess.status = "finished"
            sess.finished_at = datetime.utcnow()
            # Aggregate final band from non-overridden answers
            bands = [a.reviewer_override_band or a.band for a in sess.answers if (a.reviewer_override_band or a.band)]
            if bands:
                # simple median-as-band mapping
                sess.final_band = _median_band(bands)
            db.add(AuditLog(actor="phd", action="finish_session",
                            entity_type="session", entity_id=active_id,
                            payload={"final_band": sess.final_band}))
        st.success(f"Session finished. Final band: **{sess.final_band or '—'}**")
        st.session_state.pop("active_session_id", None)
        st.rerun()


# ============================================================
# HISTORY
# ============================================================
st.divider()
st.subheader("Session history")

with session_scope() as db:
    finished = db.query(ExamSession).order_by(ExamSession.id.desc()).limit(50).all()
    rows = []
    for s in finished:
        st_row = db.get(Student, s.student_id)
        ex_row = db.get(Exam, s.exam_id)
        rows.append({
            "id": s.id, "student": st_row.full_name if st_row else "?",
            "exam": ex_row.name if ex_row else "?", "level": ex_row.cefr_level if ex_row else "?",
            "status": s.status, "answers": len(s.answers),
            "flagged": sum(1 for a in s.answers if a.flagged_for_review),
            "final_band": s.final_band or "—",
            "started": s.started_at.strftime("%Y-%m-%d %H:%M"),
            "finished": s.finished_at.strftime("%Y-%m-%d %H:%M") if s.finished_at else "—",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No sessions yet.")

