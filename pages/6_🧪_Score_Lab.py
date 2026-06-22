"""Score Lab — try sample answers against exam items without saving a session."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db import session_scope
from core.llm import LLMError
from core.models import Item
from core.scoring import score_response_for_item


def _example_answer(level: str) -> str:
    examples = {
        "A1": "I wake up at seven. I eat breakfast. I go to school by bus. In the evening I watch TV.",
        "A2": "Last weekend I went to the park with my family. We had lunch there and played football. It was nice because the weather was good.",
        "B1": "I prefer working in a small company because people can communicate more easily. You may not earn as much money, but you can learn different skills.",
        "B2": "In my view, phones can help students learn, but they also create distractions. Schools should teach responsible use instead of simply banning them.",
        "C1": "AI can support decision-making in sensitive fields, but it should remain transparent and accountable. Human review is essential when a decision affects someone's future.",
        "C2": "The central issue is not whether AI can outperform humans on narrow tasks, but whether institutions can preserve accountability when delegating consequential judgement.",
    }
    return examples.get(level, examples["B1"])


def _render_score_result(result: dict):
    band = result.get("band") or "—"
    confidence = result.get("confidence")
    confidence_label = f"{float(confidence):.2f}" if confidence is not None else "—"

    st.markdown(f"**Band:** `{band}` · **Confidence:** {confidence_label}")

    scores = result.get("scores") or {}
    if scores:
        cols = st.columns(min(6, len(scores)))
        for idx, (name, value) in enumerate(scores.items()):
            cols[idx % len(cols)].metric(name.replace("_", " ").title(), value)

    if result.get("feedback_student"):
        st.markdown("**Feedback to student**")
        st.info(result["feedback_student"])

    if result.get("feedback_internal"):
        with st.expander("Internal scoring notes"):
            st.write(result["feedback_internal"])

    with st.expander("Raw scorer JSON"):
        st.json(result)


st.set_page_config(page_title="Score Lab", page_icon="🧪", layout="wide")
st.title("🧪 Score Lab")
st.caption("Try example answers against your item bank and see how the AI scores them. Results here are not saved as real exam sessions.")

with session_scope() as db:
    items = db.query(Item).filter(Item.active == True).order_by(Item.cefr_level, Item.skill, Item.topic).all()  # noqa: E712

if not items:
    st.warning("No active items found. Add items first, or restart the app so the sample seed items can load.")
    st.stop()

left, right = st.columns([2, 3])

with left:
    item_id = st.selectbox(
        "Exam item",
        options=[item.id for item in items],
        format_func=lambda i: (
            f"#{i} · {next(item.cefr_level for item in items if item.id == i)} · "
            f"{next(item.skill for item in items if item.id == i)} · "
            f"{next(item.topic for item in items if item.id == i)}"
        ),
    )
    item = next(item for item in items if item.id == item_id)

    st.markdown(f"**Prompt** · `{item.cefr_level}` · `{item.skill}`")
    st.info(item.prompt)

    with st.expander("Expected patterns / sample / rubric", expanded=True):
        if item.expected_patterns:
            st.markdown("**Expected patterns**")
            for pattern in item.expected_patterns:
                st.write(f"- {pattern}")
        if item.sample_response:
            st.markdown("**Model sample response**")
            st.write(item.sample_response)
        if item.rubric:
            st.markdown("**Rubric**")
            st.dataframe(
                pd.DataFrame([{"criterion": key, "description": value} for key, value in item.rubric.items()]),
                use_container_width=True,
                hide_index=True,
            )

with right:
    answer_key = f"score_lab_answer_{item.id}"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = ""

    c1, c2 = st.columns(2)
    if c1.button("Use model sample", disabled=not bool(item.sample_response)):
        st.session_state[answer_key] = item.sample_response or ""
    if c2.button("Use quick example"):
        st.session_state[answer_key] = _example_answer(item.cefr_level)

    response_text = st.text_area(
        "Answer to score",
        key=answer_key,
        height=260,
        placeholder="Paste or type a student/sample answer here, then run the scorer.",
    )

    if st.button("Score this answer", type="primary"):
        if not response_text.strip():
            st.warning("Add an answer first.")
        else:
            with st.spinner("Scoring with the local AI model..."):
                try:
                    result = score_response_for_item(item, response_text.strip())
                except LLMError as exc:
                    st.error(f"LLM scoring failed: {exc}")
                else:
                    st.session_state["score_lab_last_result"] = result
                    st.session_state["score_lab_last_item_id"] = item.id

    result = st.session_state.get("score_lab_last_result")
    result_item_id = st.session_state.get("score_lab_last_item_id")
    if result and result_item_id == item.id:
        st.divider()
        _render_score_result(result)
