from __future__ import annotations

import re
from typing import Any

from .hy3_client import Hy3Client
from .sandbox import run_tests
from .schemas import Evaluation, ProcessReview, Solution, StepReview


ERROR_TYPES = {
    "题意误读", "概念错误", "条件遗漏", "计算错误", "跳步推导", "复杂度错误",
    "边界错误", "实现不一致", "格式不符", "幻觉",
}


def deterministic_review(task: dict[str, Any], solution: Solution) -> ProcessReview:
    reviews: list[StepReview] = []
    first_error = None
    first_type = None
    combined = " ".join(f"{s.claim} {s.evidence}" for s in solution.steps).lower()

    for step in solution.steps:
        status, error_type, reason = "valid", None, "未命中确定性错误规则"
        text = f"{step.claim} {step.evidence}".lower()
        for rule in task.get("rubric", {}).get("forbidden_claims", []):
            if re.search(rule["pattern"], text, flags=re.I):
                status = "invalid"
                error_type = rule["error_type"]
                reason = rule["reason"]
                if first_error is None:
                    first_error, first_type = step.id, error_type
                break
        reviews.append(StepReview(step_id=step.id, status=status, error_type=error_type, reason=reason))

    if not solution.steps:
        first_error, first_type = "S1", "跳步推导"
        reviews.append(StepReview("S1", "skipped", "跳步推导", "未提供可审计步骤"))

    missing = [c for c in task.get("rubric", {}).get("required_concepts", []) if c.lower() not in combined]
    if missing and first_error is None:
        first_error, first_type = solution.steps[-1].id if solution.steps else "S1", "条件遗漏"
        reviews.append(StepReview(first_error, "unsupported", first_type, f"缺少关键说明：{', '.join(missing)}"))

    return ProcessReview(
        process_correct=first_error is None,
        first_error_step=first_error,
        error_type=first_type,
        step_reviews=reviews,
        confidence=0.72 if first_error else 0.62,
        source="rules",
    )


class ProcessEvaluator:
    def __init__(self, client: Hy3Client | None = None, timeout: float = 3.0, use_llm_judge: bool = True) -> None:
        self.client = client
        self.timeout = timeout
        self.use_llm_judge = use_llm_judge

    def evaluate(self, task: dict[str, Any], solution: Solution) -> Evaluation:
        visible = run_tests(solution.code, task["visible_tests"], self.timeout)
        hidden = run_tests(solution.code, task["hidden_tests"], self.timeout)
        rule_review = deterministic_review(task, solution)
        evidence = {
            "visible": {"passed": visible.passed, "total": visible.total, "failures": visible.failures[:2]},
            "hidden": {"passed": hidden.passed, "total": hidden.total, "failures": hidden.failures[:2]},
            "static_policy_error": hidden.policy_error,
        }
        review = rule_review
        if self.use_llm_judge and self.client is not None and not self.client.demo_mode:
            try:
                llm_review = self.client.review(task, solution, evidence)
                # A deterministic contradiction has veto power; otherwise use Hy3's richer review.
                review = rule_review if not rule_review.process_correct else llm_review
            except Exception:
                review = rule_review

        final_correct = hidden.all_passed
        process_correct = review.process_correct
        if final_correct and process_correct:
            verdict = "答案与过程均成立"
        elif final_correct:
            verdict = "答案正确但过程不成立"
        elif process_correct:
            verdict = "过程主张未发现错误，但实现未通过"
        else:
            verdict = "答案与过程均存在问题"
        first_step = review.first_error_step
        error_type = review.error_type
        if not final_correct and first_step is None:
            first_step, error_type = "CODE", "实现不一致"
        return Evaluation(
            task_id=task["id"], final_correct=final_correct, process_correct=process_correct,
            verdict=verdict, first_error_step=first_step, error_type=error_type,
            visible_tests=visible, hidden_tests=hidden, process_review=review,
        )

