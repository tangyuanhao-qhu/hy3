from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from hy3_process_eval.dataset import load_tasks
from hy3_process_eval.evaluator import ProcessEvaluator
from hy3_process_eval.hy3_client import Hy3Client


load_dotenv()
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / os.getenv("DATA_DIR", "data")

st.set_page_config(page_title="Hy3 VerifyLab", page_icon="✓", layout="wide")
st.title("Hy3 VerifyLab：代码解题过程评估")
st.caption("隐藏测试验证结果 · 规则/执行证据核验实现 · Hy3 分步复核定位首错")

tasks = load_tasks(DATA_DIR)
selected = st.sidebar.selectbox(
    "选择题目", tasks, format_func=lambda x: f"[{x['difficulty']}] {x['id']} · {x['title']}"
)
demo_mode = os.getenv("DEMO_MODE", "0") == "1"
st.sidebar.info("当前为 Demo 模式，不调用模型。" if demo_mode else "当前连接 Hy3 API。")

left, right = st.columns([1, 1.15])
with left:
    st.subheader("题目")
    st.write(selected["prompt"])
    st.code(selected["signature"], language="python")
    st.write("约束：")
    for item in selected["constraints"]:
        st.write(f"- {item}")
    st.write("可见测试：")
    for test in selected["visible_tests"]:
        st.code(test, language="python")

with right:
    st.subheader("完整解题与评估")
    if st.button("让 Hy3 解题并评估", type="primary", use_container_width=True):
        with st.spinner("生成可审计步骤并运行验证…"):
            client = Hy3Client()
            solution = client.solve(selected)
            evaluator = ProcessEvaluator(client=client, timeout=float(os.getenv("SANDBOX_TIMEOUT_SECONDS", "3")))
            result = evaluator.evaluate(selected, solution)
            st.session_state["solution"] = solution.to_dict()
            st.session_state["evaluation"] = result.to_dict()

    if "solution" in st.session_state:
        solution = st.session_state["solution"]
        evaluation = st.session_state["evaluation"]
        st.markdown(f"**方案：** {solution['summary']}")
        st.dataframe(pd.DataFrame(solution["steps"]), use_container_width=True, hide_index=True)
        st.code(solution["code"], language="python")

        if evaluation["final_correct"] and evaluation["process_correct"]:
            st.success(evaluation["verdict"])
        elif evaluation["final_correct"]:
            st.warning(evaluation["verdict"])
        else:
            st.error(evaluation["verdict"])

        c1, c2, c3 = st.columns(3)
        c1.metric("最终答案", "正确" if evaluation["final_correct"] else "错误")
        c2.metric("过程", "成立" if evaluation["process_correct"] else "不成立")
        c3.metric("首错位置", evaluation["first_error_step"] or "无")
        st.write(f"错误类型：{evaluation['error_type'] or '无'}")
        st.write("逐步审查：")
        st.dataframe(pd.DataFrame(evaluation["process_review"]["step_reviews"]), use_container_width=True, hide_index=True)
        with st.expander("测试证据（隐藏用例不显示原文）"):
            st.json({
                "visible": {k: evaluation["visible_tests"][k] for k in ("passed", "total", "policy_error", "timed_out")},
                "hidden": {k: evaluation["hidden_tests"][k] for k in ("passed", "total", "policy_error", "timed_out")},
            })
        st.download_button(
            "下载本次评估 JSON", json.dumps(evaluation, ensure_ascii=False, indent=2),
            file_name=f"{selected['id']}_evaluation.json", mime="application/json",
        )

