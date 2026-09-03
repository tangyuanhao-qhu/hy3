"""Consistency gate for the constructed gold set.

The gold set is built by *defect injection*: a flawed claim is planted at a
known step, and the label records the injection intent. This script checks that
the recorded labels agree with ground-truth execution, while deliberately NOT
checking them against the process evaluator (that comparison is the measurement
itself and is done by scripts/run_validation.py).

Run before merging any gold batch:

    PYTHONPATH=src python scripts/verify_gold.py data/gold_g1.jsonl

Checks
------
1. Schema          : required fields present and well formed.
2. Execution truth : gold.final_correct must equal "code passes all hidden
                     tests". This is objective and must hold exactly.
3. Error taxonomy  : error_type is one of the 10 defined types, or null when
                     the process is correct.
4. Step integrity  : first_error_step, when present, must be a real step id.
5. Uniqueness      : sample ids unique.
6. Balance         : warn when any error type falls below the per-type floor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hy3_process_eval.dataset import load_jsonl, task_index  # noqa: E402
from hy3_process_eval.evaluator import ERROR_TYPES  # noqa: E402
from hy3_process_eval.sandbox import run_tests  # noqa: E402

MIN_PER_TYPE = 15


def verify(path: Path) -> int:
    tasks = task_index(ROOT / "data")
    samples = load_jsonl(path)
    errors: list[str] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}

    for sample in samples:
        sid = sample.get("id", "<no id>")
        if sid in seen:
            errors.append(f"[{sid}] duplicate sample id")
        seen.add(sid)

        task_id = sample.get("task_id")
        if task_id not in tasks:
            errors.append(f"[{sid}] unknown task_id {task_id!r}")
            continue
        task = tasks[task_id]

        solution = sample.get("solution") or {}
        gold = sample.get("gold") or {}
        if not solution.get("steps"):
            errors.append(f"[{sid}] solution.steps is empty")
        if "final_correct" not in gold or "process_correct" not in gold:
            errors.append(f"[{sid}] gold must declare final_correct and process_correct")
            continue

        code = solution.get("code", "")
        result = run_tests(code, task["hidden_tests"], 3.0)

        # 2. Execution truth -------------------------------------------------
        if result.policy_error:
            errors.append(f"[{sid}] sandbox policy rejected the code: {result.policy_error}")
            continue
        if bool(gold["final_correct"]) != result.all_passed:
            detail = "; ".join(f["test"] for f in result.failures[:2])
            errors.append(
                f"[{sid}] gold.final_correct={gold['final_correct']} but hidden tests "
                f"{'all passed' if result.all_passed else 'FAILED (' + detail + ')'}"
            )

        # 3. Taxonomy --------------------------------------------------------
        etype = gold.get("error_type")
        if gold.get("process_correct"):
            if etype is not None:
                errors.append(f"[{sid}] process_correct=True must have error_type=None, got {etype!r}")
            if gold.get("first_error_step") is not None:
                errors.append(f"[{sid}] process_correct=True must have first_error_step=None")
        else:
            if etype not in ERROR_TYPES:
                errors.append(f"[{sid}] error_type {etype!r} is not one of the 10 defined types")
            else:
                counts[etype] = counts.get(etype, 0) + 1
            if not gold.get("first_error_step"):
                errors.append(f"[{sid}] process_correct=False must name a first_error_step")

        # 4. Step integrity --------------------------------------------------
        step_ids = {s.get("id") for s in solution.get("steps", [])}
        fes = gold.get("first_error_step")
        if fes and fes not in step_ids and fes != "CODE":
            errors.append(f"[{sid}] first_error_step {fes!r} is not a step id in this solution")

    total = len(samples)
    flawed = sum(1 for s in samples if not (s.get("gold") or {}).get("process_correct", True))
    print(f"file    : {path}")
    print(f"samples : {total}  (process-correct={total - flawed}, process-flawed={flawed})")
    print("types   : " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else "types   : none")

    below = {t: counts.get(t, 0) for t in sorted(ERROR_TYPES) if counts.get(t, 0) < MIN_PER_TYPE}
    if below:
        print(f"WARN    : below the {MIN_PER_TYPE}-per-type floor -> " +
              ", ".join(f"{k}={v}" for k, v in below.items()))

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for err in errors[:40]:
            print(f"  ERR {err}")
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    print("\nGOLD_OK: labels agree with execution; taxonomy and step ids valid")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: verify_gold.py <gold.jsonl> [...]")
        return 2
    worst = 0
    for arg in argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"missing file: {path}")
            worst = 2
            continue
        worst = max(worst, verify(path))
        print()
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
