from __future__ import annotations

from pathlib import Path

from hy3_process_eval.dataset import load_jsonl, task_index
from hy3_process_eval.evaluator import ProcessEvaluator
from hy3_process_eval.sandbox import policy_check, run_tests
from hy3_process_eval.schemas import Solution


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    assert run_tests("def add(a,b):\n    return a+b\n", ["add(2,3)==5"]).all_passed
    assert "Denied syntax" in (policy_check("import os") or "")
    tasks = task_index(ROOT / "data")
    for task in tasks.values():
        solution = Solution.from_dict({
            "task_id": task["id"], "summary": task["demo_solution"]["summary"],
            "steps": task["demo_solution"]["steps"], "code": task["reference_solution"],
        })
        result = ProcessEvaluator(use_llm_judge=False).evaluate(task, solution)
        assert result.final_correct, f"reference failed hidden tests: {task['id']}"
        assert result.process_correct, f"demo process failed rubric: {task['id']}"
    sample = next(x for x in load_jsonl(ROOT / "data" / "validation_samples.jsonl") if x["id"] == "V04")
    result = ProcessEvaluator(use_llm_judge=False).evaluate(tasks[sample["task_id"]], Solution.from_dict(sample["solution"]))
    assert result.final_correct and not result.process_correct and result.first_error_step == "S1"
    print(f"SELF_CHECK_OK: {len(tasks)} tasks, sandbox and unsupported-process case")


if __name__ == "__main__":
    main()
