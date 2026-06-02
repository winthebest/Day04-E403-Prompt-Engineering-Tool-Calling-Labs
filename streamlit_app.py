from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from grade.scoring import coerce_result, load_cases
from src.agent.graph import run_agent

ROOT_DIR = Path(__file__).resolve().parent
SCORE_FILE = ROOT_DIR / "Score.md"
CASES_FILE = ROOT_DIR / "data" / "graded_cases.json"


def _load_score_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                candidate = part.replace("json", "", 1).strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _render_agent_error(error: Exception) -> None:
    message = str(error)
    lower = message.lower()
    if "resource_exhausted" in lower or "spending cap" in lower or "quota" in lower:
        st.error("Model bi gioi han quota/spending cap. Hay doi provider hoac tang quota.")
        return
    if "authentication" in lower or "api key" in lower or "unauthorized" in lower:
        st.error("Loi xac thuc API key. Kiem tra lai .env va key dang dung.")
        return
    st.error(f"Run that bai: {message}")


def _render_score_snapshot() -> None:
    st.subheader("Score Snapshot")
    snapshot = _load_score_snapshot(SCORE_FILE)
    if not snapshot:
        st.info("Chua co Score.md hop le. Hay chay grader de tao snapshot.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Overall", f"{float(snapshot.get('overall_score', 0.0)):.2f}")
    col2.metric("Earned", f"{float(snapshot.get('total_earned', 0.0)):.0f}")
    col3.metric("Max", f"{float(snapshot.get('total_max', 0.0)):.0f}")

    st.caption(f"Loaded from `{SCORE_FILE.name}`")
    st.dataframe(
        [
            {
                "case_id": item.get("case_id", ""),
                "score": item.get("score", 0),
                "max_score": item.get("max_score", 0),
            }
            for item in snapshot.get("cases", [])
        ],
        hide_index=True,
        use_container_width=True,
    )


def _render_live_query() -> None:
    st.subheader("Run Live Query")

    col1, col2, col3 = st.columns(3)
    provider = col1.selectbox("Provider", ["google", "openai", "ollama"], index=0)
    model_name = col2.text_input("Model override (optional)", value="")
    today = col3.date_input("Today", value=date(2026, 6, 1)).isoformat()

    if "live_query" not in st.session_state:
        st.session_state["live_query"] = (
            "Tao don hang cho Nguyen Lan Anh, so dien thoai 0901234567, "
            "email lananh@example.com, giao den 18 Nguyen Hue, Quan 1, TP.HCM. "
            "Toi can 1 ASUS ROG Zephyrus G14, 2 Logitech Pebble 2 M350s va 1 LG UltraGear 27GP850-B."
        )

    cases = load_cases(CASES_FILE)
    case_options = {f"[{case['category']}] {case['id']}": case["query"] for case in cases}
    selected_case = st.selectbox("Quick test case", ["(none)"] + list(case_options.keys()))
    if st.button("Load selected case", use_container_width=True) and selected_case != "(none)":
        st.session_state["live_query"] = case_options[selected_case]

    query = st.text_area("User query", key="live_query", height=140)

    if st.button("Run Agent", type="primary", use_container_width=True):
        with st.spinner("Dang chay agent..."):
            try:
                raw_result = run_agent(
                    query,
                    provider=provider,
                    model_name=model_name or None,
                    today=today,
                )
            except Exception as error:  # noqa: BLE001
                _render_agent_error(error)
                return

        result = coerce_result(raw_result, query=query, provider=provider, model_name=model_name or None)
        st.success("Run xong.")
        st.markdown("### Final Answer")
        st.write(result.get("final_answer", ""))

        st.markdown("### Tool Trace")
        tool_calls = result.get("tool_calls", [])
        st.dataframe(
            [
                {
                    "name": tc["name"] if isinstance(tc, dict) else getattr(tc, "name", ""),
                    "args": tc["args"] if isinstance(tc, dict) else getattr(tc, "args", {}),
                    "output_preview": (tc["output"] if isinstance(tc, dict) else getattr(tc, "output", ""))[:160],
                }
                for tc in tool_calls
            ],
            hide_index=True,
            use_container_width=True,
        )

        if result.get("saved_order"):
            st.markdown("### Saved Order")
            st.json(result["saved_order"])
            st.caption(f"saved_order_path: {result.get('saved_order_path')}")
        else:
            st.info("Khong co saved_order.")


def _render_test_scenarios() -> None:
    st.subheader("Official Test Scenarios")
    cases = load_cases(CASES_FILE)
    categories = sorted({case["category"] for case in cases})
    selected_categories = st.multiselect("Filter categories", categories, default=categories)
    visible_cases = [case for case in cases if case["category"] in selected_categories]

    st.dataframe(
        [
            {
                "case_id": case["id"],
                "category": case["category"],
                "expect_saved_order": bool(case["expected"].get("expect_saved_order", False)),
                "required_tools": " -> ".join(case["expected"].get("required_tools", [])),
                "query": case["query"],
            }
            for case in visible_cases
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("### Case Details + Example")
    for case in visible_cases:
        expected = case.get("expected", {})
        required_tools = expected.get("required_tools", [])
        order_file = expected.get("expected_order_file")
        label = f"[{case['category']}] {case['id']}"
        with st.expander(label):
            st.markdown("**Query**")
            st.code(case["query"], language="text")

            col1, col2 = st.columns(2)
            col1.markdown(f"**Expect saved order:** `{bool(expected.get('expect_saved_order', False))}`")
            col2.markdown(f"**Required tools:** `{' -> '.join(required_tools) if required_tools else '(none)'}`")

            st.markdown("**Weights**")
            st.json(case.get("weights", {}))

            rubric = expected.get("grading_rubric", "")
            if rubric:
                st.markdown("**Rubric**")
                st.write(rubric)

            if order_file:
                st.markdown(f"**Expected order example:** `{order_file}`")
                order_path = ROOT_DIR / order_file
                if order_path.exists():
                    try:
                        st.json(json.loads(order_path.read_text(encoding="utf-8")))
                    except json.JSONDecodeError:
                        st.warning("Expected order file exists but is not valid JSON.")

            if st.button(f"Use case in Live Query: {case['id']}", key=f"use_case_{case['id']}"):
                st.session_state["live_query"] = case["query"]
                st.success("Da nap query vao tab Live Query.")


def main() -> None:
    st.set_page_config(page_title="OrderDesk Agent Demo", layout="wide")
    st.title("OrderDesk Agent Demo")
    st.caption("UI de chay agent, test cases va trinh bay ket qua.")

    tab1, tab2, tab3 = st.tabs(
        ["Score Snapshot", "Live Query", "Test Scenarios"]
    )
    with tab1:
        _render_score_snapshot()
    with tab2:
        _render_live_query()
    with tab3:
        _render_test_scenarios()


if __name__ == "__main__":
    main()
