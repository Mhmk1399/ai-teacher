"""Items page — the PhD master's content authoring tool."""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st

from core.config import settings
from core.db import session_scope
from core.models import Item, AuditLog


st.set_page_config(page_title="Items", page_icon="✍️", layout="wide")
st.title("✍️ Items — the exam-question bank")

st.caption("Each item is a single question the AI can ask a student. The PhD master owns this content. "
           "Expected patterns + sample response + rubric are what make AI scoring consistent.")

# ----- Add / edit single item -----
mode = st.radio("Mode", ["Add new", "Edit existing"], horizontal=True)

with session_scope() as db:
    items = db.query(Item).order_by(Item.id.desc()).all()


if mode == "Add new":
    with st.form("add_item"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Code (optional)", placeholder="B1-S-001")
        skill = c2.selectbox("Skill", ["speaking", "writing", "reading", "listening"])
        level = c3.selectbox("CEFR level", settings.CEFR_LEVELS, index=2)
        topic = st.text_input("Topic", placeholder="Travel memory")
        prompt = st.text_area("Prompt *", height=100,
                              placeholder="Talk about a journey you remember well…")
        expected = st.text_area("Expected linguistic patterns (one per line)",
                                placeholder="past simple for narrative events\nsequencers (first, then, after that)")
        sample = st.text_area("Sample response (model answer)", height=140)
        rubric_text = st.text_area(
            "Rubric (one criterion per line, format: `criterion : description`)",
            height=140,
            value=(
                "task_achievement : Narrates a past journey with setting, characters, memorable moment\n"
                "fluency_coherence : Sequenced narrative; clear progression\n"
                "grammatical_range : Past simple/continuous, some present for commentary\n"
                "grammatical_accuracy : Errors do not impede meaning\n"
                "lexical_resource : Travel + descriptive vocabulary"
            ),
        )
        tags = st.text_input("Tags (comma-separated)")
        if st.form_submit_button("Add item"):
            if not prompt.strip():
                st.error("Prompt is required.")
            else:
                rubric = {}
                for line in rubric_text.splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    rubric[k.strip()] = v.strip()
                patterns = [p.strip() for p in expected.splitlines() if p.strip()]
                with session_scope() as db:
                    it = Item(
                        code=code.strip() or None,
                        skill=skill, cefr_level=level, topic=topic.strip() or "",
                        prompt=prompt.strip(),
                        expected_patterns=patterns or None,
                        sample_response=sample.strip() or None,
                        rubric=rubric,
                        tags=[t.strip() for t in tags.split(",") if t.strip()] or None,
                        created_by="phd",
                    )
                    db.add(it)
                    db.flush()
                    db.add(AuditLog(actor="phd", action="create_item",
                                    entity_type="item", entity_id=it.id,
                                    payload={"skill": skill, "cefr_level": level}))
                st.success(f"Added item #{it.id}.")


else:  # Edit existing
    if not items:
        st.info("No items yet.")
    else:
        labels = [f"#{i.id} · {i.skill}/{i.cefr_level} · {i.topic[:40]}" for i in items]
        idx = st.selectbox("Pick an item", range(len(items)),
                           format_func=lambda i: labels[i])
        it = items[idx]
        with st.form(f"edit_{it.id}"):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("Code", it.code or "")
            skill = c2.selectbox("Skill", ["speaking", "writing", "reading", "listening"],
                                 index=["speaking", "writing", "reading", "listening"].index(it.skill))
            level = c3.selectbox("CEFR level", settings.CEFR_LEVELS,
                                 index=settings.CEFR_LEVELS.index(it.cefr_level))
            topic = st.text_input("Topic", it.topic)
            prompt = st.text_area("Prompt *", it.prompt, height=100)
            expected = st.text_area("Expected patterns", "\n".join(it.expected_patterns or []), height=100)
            sample = st.text_area("Sample response", it.sample_response or "", height=140)
            rubric_text = "\n".join(f"{k} : {v}" for k, v in (it.rubric or {}).items())
            rubric_text = st.text_area("Rubric", rubric_text, height=140)
            tags = st.text_input("Tags", ", ".join(it.tags or []))
            active = st.checkbox("Active (eligible for exam generation)", value=it.active)
            if st.form_submit_button("Save changes"):
                rubric = {}
                for line in rubric_text.splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    rubric[k.strip()] = v.strip()
                patterns = [p.strip() for p in expected.splitlines() if p.strip()]
                with session_scope() as db:
                    it2 = db.get(Item, it.id)
                    it2.code = code.strip() or None
                    it2.skill = skill
                    it2.cefr_level = level
                    it2.topic = topic.strip()
                    it2.prompt = prompt.strip()
                    it2.expected_patterns = patterns or None
                    it2.sample_response = sample.strip() or None
                    it2.rubric = rubric
                    it2.tags = [t.strip() for t in tags.split(",") if t.strip()] or None
                    it2.active = active
                    db.add(AuditLog(actor="phd", action="update_item",
                                    entity_type="item", entity_id=it2.id,
                                    payload={"skill": skill, "cefr_level": level, "active": active}))
                st.success("Saved.")


# ----- Browse all -----
st.divider()
st.subheader("All items")

with session_scope() as db:
    rows = db.query(Item).order_by(Item.id.desc()).all()
    data = [{
        "id": i.id,
        "code": i.code or "",
        "skill": i.skill,
        "level": i.cefr_level,
        "topic": i.topic,
        "active": "✅" if i.active else "❌",
        "prompt": (i.prompt[:80] + "…") if len(i.prompt) > 80 else i.prompt,
    } for i in rows]

if data:
    df = pd.DataFrame(data)
    c1, c2, c3, c4 = st.columns(4)
    f_skill = c1.multiselect("Skill", sorted(df["skill"].unique()))
    f_level = c2.multiselect("Level", settings.CEFR_LEVELS)
    f_active = c3.selectbox("Active", ["all", "yes", "no"])
    q = c4.text_input("🔎 Search topic / prompt / code")
    view = df.copy()
    if f_skill:
        view = view[view["skill"].isin(f_skill)]
    if f_level:
        view = view[view["level"].isin(f_level)]
    if f_active != "all":
        view = view[view["active"] == ("✅" if f_active == "yes" else "❌")]
    if q:
        ql = q.lower()
        view = view[view.apply(lambda r: ql in str(r["topic"]).lower()
                                          or ql in str(r["prompt"]).lower()
                                          or ql in str(r["code"]).lower(), axis=1)]
    st.caption(f"{len(view)} / {len(df)} items shown")
    st.dataframe(view, use_container_width=True, hide_index=True)
else:
    st.info("No items yet. Use the form above to add some.")
