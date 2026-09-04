from pathlib import Path

from hy3_process_eval.dataset import load_jsonl, task_index
from hy3_process_eval.evaluator import ProcessEvaluator, deterministic_review
from hy3_process_eval.schemas import ProcessReview, Solution, StepReview


ROOT = Path(__file__).resolve().parents[1]


def test_correct_but_unsupported_is_detected():
    tasks = task_index(ROOT / "data")
    sample = next(x for x in load_jsonl(ROOT / "data" / "validation_samples.jsonl") if x["id"] == "V04")
    result = ProcessEvaluator(use_llm_judge=False).evaluate(tasks[sample["task_id"]], Solution.from_dict(sample["solution"]))
    assert result.final_correct is True
    assert result.process_correct is False
    assert result.verdict == "答案正确但过程不成立"
    assert result.first_error_step == "S1"


def test_reference_solutions_pass_hidden_tests():
    for task in task_index(ROOT / "data").values():
        solution = Solution.from_dict({
            "task_id": task["id"], "summary": task["demo_solution"]["summary"],
            "steps": task["demo_solution"]["steps"], "code": task["reference_solution"],
        })
        result = ProcessEvaluator(use_llm_judge=False).evaluate(task, solution)
        assert result.final_correct, task["id"]
        assert result.process_correct, task["id"]


class _AcceptingJudge:
    demo_mode = False

    def __init__(self):
        self.calls = 0

    def review(self, _task, _solution, _evidence):
        self.calls += 1
        return ProcessReview(
            process_correct=True,
            first_error_step=None,
            error_type=None,
            step_reviews=[StepReview("S1", "valid", reason="语义等价")],
            confidence=0.9,
            source="hy3",
        )


def _minimal_task(forbidden=None):
    return {
        "id": "T",
        "signature": "def identity(x):",
        "visible_tests": ["identity(1) == 1"],
        "hidden_tests": ["identity(2) == 2"],
        "rubric": {
            "required_concepts": ["线性复杂度"],
            "forbidden_claims": forbidden or [],
        },
    }


def test_missing_keyword_is_weak_and_hy3_can_clear_it():
    task = _minimal_task()
    solution = Solution.from_dict({
        "task_id": "T",
        "summary": "直接返回",
        "steps": [{"id": "S1", "claim": "只访问输入一次", "evidence": "无循环嵌套"}],
        "code": "def identity(x):\n    return x\n",
    })
    assert deterministic_review(task, solution).source == "rules_weak"

    judge = _AcceptingJudge()
    result = ProcessEvaluator(client=judge).evaluate(task, solution)
    assert judge.calls == 1
    assert result.process_correct is True
    assert result.process_review.source == "hy3"


def test_explicit_contradiction_is_sent_as_evidence_to_hy3():
    task = _minimal_task([{
        "pattern": "常数时间",
        "error_type": "复杂度错误",
        "reason": "复杂度主张与实现矛盾",
    }])
    solution = Solution.from_dict({
        "task_id": "T",
        "summary": "直接返回",
        "steps": [{"id": "S1", "claim": "这是常数时间", "evidence": "错误主张"}],
        "code": "def identity(x):\n    return x\n",
    })
    judge = _AcceptingJudge()
    result = ProcessEvaluator(client=judge).evaluate(task, solution)
    assert deterministic_review(task, solution).source == "rules_strong"
    assert judge.calls == 1
    assert result.process_correct is True
    assert result.process_review.source == "hy3"
