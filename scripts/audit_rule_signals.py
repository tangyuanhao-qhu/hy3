"""Semantically adjudicate non-weak rule flags from an existing benchmark.

The weak-keyword cases are handled by ``audit_weak_signals.py``.  This script
reviews the remaining rule flags with the full Hy3 judge, because even a
forbidden-claim regex can produce a false match through negation scope or an
unrelated later word in the same step.

Usage:
    PYTHONPATH=src python scripts/audit_rule_signals.py \
      --input results/hy3_benchmark_run2.json \
      --weak-audit results/weak_signal_audit_run2.json \
      --output results/rule_signal_audit_run2.json
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from hy3_process_eval.dataset import load_tasks
from hy3_process_eval.hy3_client import Hy3Client
from hy3_process_eval.schemas import Solution


ROOT = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 4


def _review(client: Hy3Client, task: dict, row: dict) -> dict:
    evaluation = row["evaluation"]
    evidence = {
        "visible": {
            "passed": evaluation["visible_tests"]["passed"],
            "total": evaluation["visible_tests"]["total"],
            "failures": evaluation["visible_tests"].get("failures", [])[:2],
        },
        "hidden": {
            "passed": evaluation["hidden_tests"]["passed"],
            "total": evaluation["hidden_tests"]["total"],
            "failures": evaluation["hidden_tests"].get("failures", [])[:2],
        },
        "static_policy_error": evaluation["hidden_tests"].get("policy_error"),
        "rule_signal": evaluation["process_review"],
    }
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            review = client.review(task, Solution.from_dict(row["solution"]), evidence)
            return {"semantic_review": {
                "process_correct": review.process_correct,
                "first_error_step": review.first_error_step,
                "error_type": review.error_type,
                "confidence": review.confidence,
                "step_reviews": [vars(item) for item in review.step_reviews],
                "source": review.source,
            }}
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(5 * (2 ** (attempt - 1)))
    return {"semantic_review": None, "error": last_error}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results/hy3_benchmark_run2.json")
    parser.add_argument("--weak-audit", default="results/weak_signal_audit_run2.json")
    parser.add_argument("--output", default="results/rule_signal_audit_run2.json")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    client = Hy3Client()
    tasks = {task["id"]: task for task in load_tasks(ROOT / "data")}
    report = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    weak = json.loads((ROOT / args.weak_audit).read_text(encoding="utf-8"))
    weak_ids = {row["task_id"] for row in weak["results"]}

    cases = [
        row for row in report["rows"]
        if row.get("evaluation") is not None
        and not row["evaluation"]["process_correct"]
        and row["evaluation"]["process_review"]["source"] == "rules"
        and row["task"]["id"] not in weak_ids
    ]
    print(f"non-weak rule signals to adjudicate: {len(cases)}", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_review, client, tasks[row["task"]["id"]], row): row
            for row in cases
        }
        for done, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            item = {
                "task_id": row["task"]["id"],
                "difficulty": row["task"]["difficulty"],
                "original_review": row["evaluation"]["process_review"],
                **future.result(),
            }
            results.append(item)
            verdict = item["semantic_review"]["process_correct"] if item["semantic_review"] else None
            print(f"[{done}/{len(cases)}] {item['task_id']} process_correct={verdict}", flush=True)

    order = {row["task"]["id"]: i for i, row in enumerate(cases)}
    results.sort(key=lambda item: order[item["task_id"]])
    successful = [item for item in results if item["semantic_review"] is not None]
    cleared = [item for item in successful if item["semantic_review"]["process_correct"]]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": client.model,
        "n_cases": len(results),
        "n_adjudicated": len(successful),
        "n_cleared_false_alarm": len(cleared),
        "false_alarm_rate": len(cleared) / len(successful) if successful else None,
        "results": results,
    }
    path = ROOT / args.output
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
