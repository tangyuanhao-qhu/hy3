from pathlib import Path

from hy3_process_eval.dataset import load_jsonl, task_index
from hy3_process_eval.evaluator import ProcessEvaluator
from hy3_process_eval.schemas import Solution


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

