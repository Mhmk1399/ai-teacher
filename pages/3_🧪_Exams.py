"""Exams page — assemble exam templates from items."""
from __future__ import annotations
from datetime import datetime
import pandas as pd
import streamlit as st

from core.config import settings
from core.db import session_scope
from core.exam_engine import generate_exam, items_for_exam
from core.models import Exam, Item, AuditLog
from sqlalchemy import select, func


st.set_page_config(page_title="Exams", page_icon="🧪", layout="wide")
st.title("🧪 Exams — templates assembled from items")


# ----- Create a new exam template -----
st.subheader("Create an exam template")

with session_scope() as db:
    pool_counts = db.execute(
        select(Item.cefr_level, Item.skill, func.count(Item.id))
        .where(Item.active == True)  # noqa: E712
        .group_by(Item.cefr_level, Item.skill)
    ).all()

if not pool_counts:
    st.warning("Your item bank is empty. Add items in the **Items** page first.")
else:
    df_pool = pd.DataFrame(pool_counts, columns=["level", "skill", "count"])
    with st.expander("📊 Item bank by level + skill", expanded=False):
        pivot = df_pool.pivot_table(index="level", columns="skill", values="count", fill_value=0)
        st.dataframe(pivot, use_container_width=True)

with st.form("create_exam"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name *", placeholder="A2 Speaking diagnostic v1")
    cefr = c2.selectbox("CEFR level *", settings.CEFR_LEVELS)
    skills = st.multiselect("Skills *", ["speaking", "writing"], default=["speaking"])
    item_count = st.slider("Number of items", min_value=1, max_value=10, value=5)
    fmt = st.selectbox("Format", ["text", "voice"], index=0 if settings.PHASE == 1 else 1)
    description = st.text_area("Description (optional)")
    if st.form_submit_button("Generate exam template"):
        if not name.strip():
            st.error("Name is required.")
        elif not skills:
            st.error("Pick at least one skill.")
        else:
            try:
                with session_scope() as db:
                    exam = generate_exam(
                        db, name=name.strip(), cefr_level=cefr,
                        skills=skills, item_count=item_count, fmt=fmt,
                        description=description.strip() or None,
                    )
                    db.add(AuditLog(actor="phd", action="create_exam",
                                    entity_type="exam", entity_id=exam.id,
                                    payload={"cefr_level": cefr, "skills": skills, "item_count": item_count}))
                st.success(f"Created exam **#{exam.id} · {name}** with {exam.item_count} item(s).")
            except ValueError as e:
                st.error(str(e))


# ----- List & preview -----
st.divider()
st.subheader("All exams")

with session_scope() as db:
    exams = db.query(Exam).order_by(Exam.id.desc()).all()

if not exams:
    st.info("No exams yet.")
else:
    rows = [{
        "id": e.id,
        "name": e.name,
        "level": e.cefr_level,
        "skills": ", ".join(e.skills or []),
        "items": e.item_count,
        "format": e.format,
        "created": e.created_at.strftime("%Y-%m-%d %H:%M"),
    } for e in exams]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    target_id = st.selectbox("Preview / delete", options=[e.id for e in exams],
                             format_func=lambda i: f"#{i} · {next(e.name for e in exams if e.id == i)}")
    target = next(e for e in exams if e.id == target_id)

    with session_scope() as db:
        et = db.get(Exam, target_id)
        preview_items = items_for_exam(db, et)
        preview_rows = [{
            "id": i.id, "skill": i.skill, "level": i.cefr_level,
            "topic": i.topic, "prompt": i.prompt,
        } for i in preview_items]

    if preview_rows:
        st.markdown(f"**Sample of items this exam would draw (level {target.cefr_level}, skills {target.skills}):**")
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("No active items match this exam's filters.")

    if st.button(f"🗑️ Delete exam #{target_id}", type="secondary"):
        with session_scope() as db:
            et = db.get(Exam, target_id)
            db.delete(et)
            db.add(AuditLog(actor="phd", action="delete_exam",
                            entity_type="exam", entity_id=target_id, payload={}))
        st.success(f"Deleted exam #{target_id}.")
        st.rerun()
