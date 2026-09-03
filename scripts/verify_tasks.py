"""Quality gate for the task bank.

Validates every task in a JSONL file against the contract that the rest of the
toolkit assumes. Run it before committing any new tasks:

    PYTHONPATH=src python scripts/verify_tasks.py
    PYTHONPATH=src python scripts/verify_tasks.py data/tasks.jsonl

Checks performed per task
-------------------------
1.  Schema      : all required fields present and of the right shape.
2.  Execution   : reference_solution passes every visible and hidden test.
3.  Test count  : at least MIN_HIDDEN_TESTS hidden tests (per docs/PLAN.md).
4.  Rubric      : required_concepts non-empty; forbidden_claims compile as regex.
5.  Demo round  : replaying demo_solution through the *deterministic* reviewer
                  yields process_correct == True, i.e. the shipped demo steps
                  are self-consistent and would not be flagged as 条件遗漏.
6.  Uniqueness  : task ids are unique.

Exit code is 0 only when every check passes for every task.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hy3_process_eval.evaluator import deterministic_review  # noqa: E402
from hy3_process_eval.sandbox import run_tests  # noqa: E402
from hy3_process_eval.schemas import Solution  # noqa: E402

MIN_HIDDEN_TESTS = 5

# Tasks authored before the >= 5 hidden-test rule was introduced. They are kept
# byte-for-byte unchanged so that previously reported numbers stay reproducible;
# they are therefore exempt from that one rule and from that rule only.
LEGACY_IDS = {"E01", "E02", "E03", "M01", "M02", "M03", "H01", "H02", "H03"}

REQUIRED_FIELDS = [
    "id", "title", "difficulty", "source", "prompt", "signature",
    "constraints", "visible_tests", "hidden_tests", "reference_solution",
    "rubric", "demo_solution",
]
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def _err(task_id: str, message: str, errors: list[str]) -> None:
    errors.append(f"[{task_id}] {message}")


def verify_task(task: dict, errors: list[str], warnings: list[str]) -> bool:
    """Return True when the task passes every hard check."""
    raw_id = task.get("id", "<missing id>")

    # 1. Schema -------------------------------------------------------------
    for field in REQUIRED_FIELDS:
        if field not in task:
            _err(raw_id, f"missing field '{field}'", errors)
    if "id" not in task:
        return False

    tid = task["id"]
    if task.get("difficulty") not in VALID_DIFFICULTIES:
        _err(tid, f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}, got {task.get('difficulty')!r}", errors)

    for key in ("constraints", "visible_tests", "hidden_tests"):
        value = task.get(key)
        if not isinstance(value, list) or not value:
            _err(tid, f"'{key}' must be a non-empty list", errors)

    if not isinstance(task.get("reference_solution"), str) or not task["reference_solution"].strip():
        _err(tid, "'reference_solution' must be a non-empty code string", errors)
        return False

    demo = task.get("demo_solution") or {}
    if not isinstance(demo, dict) or not demo.get("steps"):
        _err(tid, "'demo_solution.steps' must be a non-empty list", errors)

    # 2. Test count ---------------------------------------------------------
    hidden = task.get("hidden_tests") or []
    if tid not in LEGACY_IDS and len(hidden) < MIN_HIDDEN_TESTS:
        _err(tid, f"only {len(hidden)} hidden tests, need >= {MIN_HIDDEN_TESTS}", errors)

    # 3. Rubric -------------------------------------------------------------
    rubric = task.get("rubric") or {}
    if not rubric.get("required_concepts"):
        _err(tid, "'rubric.required_concepts' must be non-empty", errors)
    for rule in rubric.get("forbidden_claims", []):
        for key in ("pattern", "error_type", "reason"):
            if key not in rule:
                _err(tid, f"forbidden_claim missing '{key}': {rule}", errors)
        try:
            re.compile(rule["pattern"], flags=re.I)
        except re.error as exc:
            _err(tid, f"forbidden_claim pattern does not compile: {rule['pattern']!r} ({exc})", errors)

    # 4. Execution: reference solution must pass every test ------------------
    code = task["reference_solution"]
    for label, tests in (("visible", task.get("visible_tests") or []), ("hidden", hidden)):
        if not tests:
            continue
        result = run_tests(code, tests, 3.0)
        if result.policy_error:
            _err(tid, f"{label} tests: sandbox policy rejected reference solution -> {result.policy_error}", errors)
        elif not result.all_passed:
            failed = "; ".join(f"{f['test']} -> {f['error']}" for f in result.failures[:3])
            _err(tid, f"{label} tests: reference solution failed {result.total - result.passed}/{result.total}: {failed}", errors)

    # 5. Demo round-trip ----------------------------------------------------
    if demo.get("steps"):
        try:
            solution = Solution.from_dict({
                "task_id": tid,
                "summary": demo.get("summary", ""),
                "steps": demo["steps"],
                "code": code,
                "final_answer": "implemented",
            })
            review = deterministic_review(task, solution)
            if not review.process_correct:
                _err(
                    tid,
                    f"demo_solution is flagged by the deterministic reviewer at "
                    f"{review.first_error_step} ({review.error_type}) - demo steps contradict the rubric",
                    errors,
                )
        except Exception as exc:  # noqa: BLE001 - surface any schema mismatch verbatim
            _err(tid, f"demo_solution could not be replayed: {type(exc).__name__}: {exc}", errors)

    # 6. Soft checks --------------------------------------------------------
    if not str(task.get("source", "")).strip():
        warnings.append(f"[{tid}] empty 'source' provenance")
    if tid not in LEGACY_IDS and len(hidden) < 5:
        warnings.append(f"[{tid}] fewer than 5 hidden tests")

    return not any(e.startswith(f"[{tid}]") for e in errors)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "tasks.jsonl"
    if not path.exists():
        print(f"task file not found: {path}")
        return 2

    tasks: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"FATAL: invalid JSONL at {path}:{line_no}: {exc}")
                return 2

    errors: list[str] = []
    warnings: list[str] = []

    seen: set[str] = set()
    for task in tasks:
        tid = task.get("id")
        if tid in seen:
            errors.append(f"[{tid}] duplicate task id")
        elif tid:
            seen.add(tid)
        verify_task(task, errors, warnings)

    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.get("difficulty", "?")] = counts.get(task.get("difficulty", "?"), 0) + 1

    print(f"file      : {path}")
    print(f"tasks     : {len(tasks)}")
    print(f"by level  : " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"hidden    : min={min((len(t.get('hidden_tests') or []) for t in tasks), default=0)}")

    for warning in warnings:
        print(f"WARN  {warning}")

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for err in errors[:60]:
            print(f"  ERR {err}")
        if len(errors) > 60:
            print(f"  ... and {len(errors) - 60} more")
        return 1

    print("\nTASK_BANK_OK: every task passes schema, execution, rubric and demo checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
