"""Students page — manage your cohort, set CEFR levels."""
from __future__ import annotations
import io
from datetime import datetime
import pandas as pd
import streamlit as st

from core.config import settings
from core.db import session_scope
from core.models import Student, AuditLog


st.set_page_config(page_title="Students", page_icon="📚", layout="wide")
st.title("📚 Students")

# ----- Add single student -----
with st.expander("➕ Add a student manually", expanded=False):
    with st.form("add_student"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Full name *")
        ext_id = c2.text_input("External ID (optional)", help="e.g. student number")
        l1 = c3.selectbox("L1 (first language)", ["fa", "en", "ar", "tr", "ur", "other"], index=0)
        c4, c5 = st.columns(2)
        level = c4.selectbox("CEFR level *", settings.CEFR_LEVELS, index=1)
        goal = c5.text_input("Goal (optional)", placeholder="IELTS / job English / migration…")
        notes = st.text_area("Notes (optional)")
        if st.form_submit_button("Add"):
            if not name.strip():
                st.error("Name is required.")
            else:
                with session_scope() as db:
                    s = Student(full_name=name.strip(), external_id=ext_id.strip() or None,
                                l1=l1, cefr_level=level, goal=goal.strip() or None, notes=notes.strip() or None)
                    db.add(s)
                    db.flush()
                    db.add(AuditLog(actor="phd", action="create_student",
                                    entity_type="student", entity_id=s.id,
                                    payload={"cefr_level": level}))
                st.success(f"Added **{name}** at level {level}.")


# ----- Bulk CSV import -----
with st.expander("📥 Bulk import from CSV", expanded=False):
    st.caption("CSV columns (header row required): `full_name, external_id, l1, cefr_level, goal, notes`")
    csv_text = st.text_area("Paste CSV content here", height=180,
                            placeholder="full_name,external_id,l1,cefr_level,goal,notes\nSara Mohammadi,1001,fa,A2,IELTS,\n…")
    if st.button("Import CSV"):
        if not csv_text.strip():
            st.error("Paste some CSV first.")
        else:
            try:
                df = pd.read_csv(io.StringIO(csv_text))
            except Exception as e:
                st.error(f"Could not parse CSV: {e}")
                st.stop()
            needed = {"full_name", "cefr_level"}
            missing = needed - set(df.columns)
            if missing:
                st.error(f"Missing required columns: {missing}")
                st.stop()
            added, skipped = 0, 0
            with session_scope() as db:
                for _, row in df.iterrows():
                    name = str(row.get("full_name", "")).strip()
                    if not name:
                        skipped += 1
                        continue
                    level = str(row.get("cefr_level", "")).strip().upper()
                    if level not in settings.CEFR_LEVELS:
                        skipped += 1
                        continue
                    s = Student(
                        full_name=name,
                        external_id=(str(row.get("external_id", "")).strip() or None) if "external_id" in df.columns else None,
                        l1=str(row.get("l1", "fa")).strip() if "l1" in df.columns else "fa",
                        cefr_level=level,
                        goal=str(row.get("goal", "")).strip() or None if "goal" in df.columns else None,
                        notes=str(row.get("notes", "")).strip() or None if "notes" in df.columns else None,
                    )
                    db.add(s)
                    added += 1
            st.success(f"Imported **{added}** students, skipped **{skipped}**.")


# ----- List & edit -----
st.divider()
st.subheader("All students")

with session_scope() as db:
    rows = db.query(Student).order_by(Student.id.desc()).all()
    data = [{
        "id": s.id,
        "name": s.full_name,
        "ext_id": s.external_id or "",
        "l1": s.l1,
        "level": s.cefr_level,
        "goal": s.goal or "",
        "notes": s.notes or "",
        "created": s.created_at.strftime("%Y-%m-%d"),
    } for s in rows]

if not data:
    st.info("No students yet. Add some above, or import via CSV.")
else:
    df = pd.DataFrame(data)

    # Quick filters
    c1, c2, c3 = st.columns([2, 1, 1])
    name_q = c1.text_input("🔎 Filter by name / ext_id")
    level_f = c2.multiselect("Level", settings.CEFR_LEVELS)
    l1_f = c3.multiselect("L1", sorted(df["l1"].unique().tolist()))

    view = df.copy()
    if name_q:
        q = name_q.lower()
        view = view[view["name"].str.lower().str.contains(q) | view["ext_id"].astype(str).str.lower().str.contains(q)]
    if level_f:
        view = view[view["level"].isin(level_f)]
    if l1_f:
        view = view[view["l1"].isin(l1_f)]

    st.caption(f"{len(view)} / {len(df)} students shown")
    st.dataframe(view, use_container_width=True, hide_index=True)

    # Bulk level update
    st.divider()
    st.subheader("Bulk update CEFR levels")
    st.caption("Paste a mapping `external_id,level` to update many students at once. Lines starting with `#` are ignored.")
    bulk = st.text_area("Mapping", height=140,
                        placeholder="# external_id,level\n1001,B2\n1002,B1\n…")
    if st.button("Apply bulk update"):
        updates = 0
        with session_scope() as db:
            for line in bulk.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 2:
                    continue
                ext, lvl = parts
                lvl = lvl.upper()
                if lvl not in settings.CEFR_LEVELS:
                    continue
                s = db.query(Student).filter(Student.external_id == ext).first()
                if s:
                    prev = s.cefr_level
                    s.cefr_level = lvl
                    db.add(AuditLog(actor="phd", action="bulk_level_update",
                                    entity_type="student", entity_id=s.id,
                                    payload={"from": prev, "to": lvl}))
                    updates += 1
        st.success(f"Updated {updates} students.")

    # Quick level edit
    st.divider()
    st.subheader("Edit one student")
    target = st.selectbox("Pick a student", options=[s["name"] for s in data])
    if target:
        s_row = next(s for s in data if s["name"] == target)
        c1, c2, c3 = st.columns(3)
        new_name = c1.text_input("Name", s_row["name"], key="ename")
        new_level = c2.selectbox("Level", settings.CEFR_LEVELS,
                                 index=settings.CEFR_LEVELS.index(s_row["level"]), key="elevel")
        new_goal = c3.text_input("Goal", s_row["goal"], key="egoal")
        new_notes = st.text_area("Notes", s_row["notes"], key="enotes")
        if st.button("Save changes"):
            with session_scope() as db:
                s = db.get(Student, s_row["id"])
                s.full_name = new_name.strip()
                prev_level = s.cefr_level
                s.cefr_level = new_level
                s.goal = new_goal.strip() or None
                s.notes = new_notes.strip() or None
                if prev_level != new_level:
                    db.add(AuditLog(actor="phd", action="update_level",
                                    entity_type="student", entity_id=s.id,
                                    payload={"from": prev_level, "to": new_level}))
            st.success("Saved.")

    # CSV export
    st.divider()
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button("⬇️ Export current view as CSV", data=csv_buf.getvalue(),
                       file_name=f"students_{datetime.now():%Y%m%d_%H%M}.csv", mime="text/csv")
