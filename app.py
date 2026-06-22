"""Lingua Nova — PhD Master Dashboard (home / overview)."""
from __future__ import annotations
import streamlit as st

from core.config import settings
from core.db import init_db
from core.llm import get_client
from core.seed import load_sample_items
from core.db import session_scope
from sqlalchemy import select, func

from core.models import Student, Item, Exam, ExamSession, Answer, AuditLog


st.set_page_config(
    page_title=f"{settings.APP_NAME} · PhD Console",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Boot: DB + sample data (idempotent).
init_db()
with session_scope() as db:
    added = load_sample_items(db)

if added:
    st.toast(f"Loaded {added} sample items from data/seeds/sample_items.json", icon="🌱")


# ---------------- Sidebar ----------------

with st.sidebar:
    st.markdown(f"### 🎓 {settings.APP_NAME}")
    st.caption("PhD Master Console · Exam Machine MVP")
    st.divider()
    client = get_client()
    h = client.health()
    if h.get("reachable") and h.get("model_pulled"):
        st.success(f"Ollama · {settings.OLLAMA_MODEL}")
    elif h.get("reachable"):
        st.warning(f"Ollama reachable but model not pulled\n\nRun: `ollama pull {settings.OLLAMA_MODEL}`")
    else:
        st.error("Ollama not reachable. Start it with `ollama serve`.")
    st.divider()
    st.caption(f"Phase: **{settings.PHASE}** (1=text, 2=voice)")
    st.caption(f"DB: `{settings.DATABASE_URL}`")


# ---------------- Home ----------------

st.title("🎓 Lingua Nova · Exam Machine")
st.markdown(
    """
This is the **PhD Master Console** for the Lingua Nova exam engine. The goal of this MVP is simple:
**let your expert author items, manage students, generate exams, and review the AI's scoring — all powered by a local LLM that you own and can fine-tune.**

Use the sidebar to navigate:
1. **Students** — manage your 600 students; set their CEFR level.
2. **Items** — author the exam questions the AI will use.
3. **Exams** — assemble exams from items by level + skill.
4. **Sessions** — run a student through an exam (text-based, voice coming in Phase 2).
5. **Audit** — review the AI's grades and override when it's wrong. *This is the data that makes the system smarter.*
"""
)


# ---------------- Live stats ----------------

with session_scope() as db:
    n_students = db.scalar(select(func.count(Student.id))) or 0
    n_items = db.scalar(select(func.count(Item.id))) or 0
    n_active_items = db.scalar(select(func.count(Item.id)).where(Item.active == True)) or 0  # noqa: E712
    n_exams = db.scalar(select(func.count(Exam.id))) or 0
    n_sessions = db.scalar(select(func.count(ExamSession.id))) or 0
    n_finished = db.scalar(select(func.count(ExamSession.id)).where(ExamSession.status == "finished")) or 0
    n_flagged = db.scalar(select(func.count(Answer.id)).where(Answer.flagged_for_review == True)) or 0  # noqa: E712

c1, c2, c3, c4 = st.columns(4)
c1.metric("Students", n_students, help="Imported via the Students page")
c2.metric("Active items", f"{n_active_items} / {n_items}", help="Questions in your bank")
c3.metric("Exams", n_exams, help="Templates ready to run")
c4.metric("Flagged answers", n_flagged, help="Awaiting PhD review in the Audit queue")

c5, c6, c7, _ = st.columns(4)
c5.metric("Sessions run", n_sessions)
c6.metric("Sessions finished", n_finished)
c7.metric("Completion rate", f"{(n_finished / n_sessions * 100):.0f}%" if n_sessions else "—")

st.divider()


# ---------------- Quick-start ----------------

st.markdown("### 🚀 First-time checklist")
checklist = [
    ("Ollama running with the model pulled", _ := client.health().get("model_pulled", False)),
    ("Database initialized", True),
    ("Sample items loaded", n_items > 0),
    ("At least one student imported", n_students > 0),
    ("First exam generated", n_exams > 0),
    ("First session completed", n_finished > 0),
]
for label, done in checklist:
    st.write(("✅ " if done else "⬜ ") + label)


st.divider()
st.markdown(
    """
> **Next step:** open **Students** in the sidebar, import your 600-student CSV, and start setting their CEFR levels.
> Then go to **Items** to add exam questions, and **Exams** to assemble the first exam template.
"""
)
