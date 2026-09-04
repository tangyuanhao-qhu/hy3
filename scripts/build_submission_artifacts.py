"""Build the machine-readable final summary and the single-review audit record.

This script performs no model calls.  It joins the frozen task bank, the Hy3
benchmark, the weak-signal adjudication and the evaluator gold validation into
two submission artifacts:

* results/submission_summary.json
* results/human_spot_check.csv

Usage:
    PYTHONPATH=src python scripts/build_submission_artifacts.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from hy3_process_eval.metrics import bootstrap_ci, summarize


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "results" / "hy3_benchmark_run2.json"
WEAK_AUDIT = ROOT / "results" / "weak_signal_audit_run2.json"
RULE_AUDIT = ROOT / "results" / "rule_signal_audit_run2.json"
VALIDATION = ROOT / "results" / "validation_details.json"
SAMPLES = ROOT / "data" / "validation_samples.jsonl"
TASKS = ROOT / "data" / "tasks.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> None:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    weak_audit = json.loads(WEAK_AUDIT.read_text(encoding="utf-8"))
    rule_audit = json.loads(RULE_AUDIT.read_text(encoding="utf-8"))
    validation_rows = json.loads(VALIDATION.read_text(encoding="utf-8"))
    samples = {sample["id"]: sample for sample in _load_jsonl(SAMPLES)}
    tasks = {task["id"]: task for task in _load_jsonl(TASKS)}

    rows = [row for row in benchmark["rows"] if row.get("evaluation") is not None]
    if len(rows) != len(tasks):
        raise SystemExit(f"benchmark/task mismatch: {len(rows)} completed rows vs {len(tasks)} tasks")
    if len({row['task']['id'] for row in rows}) != len(rows):
        raise SystemExit("benchmark contains duplicate task ids")

    weak_false_alarms = {
        row["task_id"] for row in weak_audit["results"] if row.get("addressed") is True
    }
    rule_false_alarms = {
        row["task_id"] for row in rule_audit["results"]
        if row.get("semantic_review", {}).get("process_correct") is True
    }
    corrected: list[tuple[dict, bool]] = []
    for row in rows:
        raw_flag = not row["evaluation"]["process_correct"]
        task_id = row["task"]["id"]
        keep = raw_flag and task_id not in weak_false_alarms and task_id not in rule_false_alarms
        corrected.append((row, keep))

    per_level: dict[str, list[tuple[dict, bool]]] = defaultdict(list)
    for item in corrected:
        per_level[item[0]["task"]["difficulty"]].append(item)

    raw_flags = [not row["evaluation"]["process_correct"] for row in rows]
    corrected_flags = [flag for _, flag in corrected]
    final_correct = [bool(row["evaluation"]["final_correct"]) for row in rows]
    corrected_error_dist = Counter(
        row["evaluation"].get("error_type") or "未分类"
        for row, flag in corrected if flag
    )

    human_rows = [
        row for row in validation_rows if samples[row["sample_id"]].get("source", "human") == "human"
    ]
    constructed_rows = [
        row for row in validation_rows if samples[row["sample_id"]].get("source", "human") == "constructed"
    ]

    summary = {
        "schema_version": 1,
        # Stable across rebuilds: the summary is tied to this benchmark run.
        "generated_at": benchmark["generated_at"],
        "scenario": "可验证 Python 代码任务的过程评估与错误定位",
        "model": {
            "name": benchmark.get("model"),
            "endpoint": "https://tokenhub.tencentmaas.com/v1",
            "reasoning_effort": "high",
            "temperature": 0.2,
            "api_key_recorded": False,
        },
        "task_bank": {
            "n": len(tasks),
            "by_difficulty": dict(Counter(task["difficulty"] for task in tasks.values())),
            "hidden_assertions": sum(len(task["hidden_tests"]) for task in tasks.values()),
            "sha256": _sha256(TASKS),
        },
        "hy3_run2": {
            "completed": len(rows),
            "failed": len(benchmark["rows"]) - len(rows),
            "final_answer_accuracy": _rate(final_correct),
            "final_answer_ci95": bootstrap_ci([int(x) for x in final_correct]),
            "hidden_assertions_passed": sum(row["evaluation"]["hidden_tests"]["passed"] for row in rows),
            "hidden_assertions_total": sum(row["evaluation"]["hidden_tests"]["total"] for row in rows),
            "raw_process_pass_rate": 1 - _rate(raw_flags),
            "raw_process_flag_count": sum(raw_flags),
            "raw_correct_but_unsupported_count": sum(
                row["evaluation"]["final_correct"] and flag
                for row, flag in zip(rows, raw_flags)
            ),
            "corrected_process_pass_rate_estimate": 1 - _rate(corrected_flags),
            "corrected_process_pass_ci95": bootstrap_ci([int(not x) for x in corrected_flags]),
            "corrected_process_flag_count_estimate": sum(corrected_flags),
            "corrected_correct_but_unsupported_count_estimate": sum(
                row["evaluation"]["final_correct"] and flag for row, flag in corrected
            ),
            "corrected_error_type_distribution_estimate": dict(corrected_error_dist),
            "by_difficulty": {
                level: {
                    "n": len(items),
                    "final_answer_accuracy": _rate([
                        bool(row["evaluation"]["final_correct"]) for row, _ in items
                    ]),
                    "raw_process_pass_rate": _rate([
                        bool(row["evaluation"]["process_correct"]) for row, _ in items
                    ]),
                    "corrected_process_pass_rate_estimate": _rate([not flag for _, flag in items]),
                }
                for level, items in sorted(per_level.items())
            },
            "capability_cliff": {
                "answer": "not_observed_all_levels_1.0",
                "corrected_process": "not_observed",
                "scope_note": "只适用于本仓库90道自构纯函数题；满分可能表示题集仍未触及Hy3能力边界。",
            },
            "benchmark_sha256": _sha256(BENCHMARK),
        },
        "weak_signal_adjudication": {
            "n_cases": weak_audit["n_cases"],
            "n_adjudicated": weak_audit["n_adjudicated"],
            "paraphrase_false_alarms": weak_audit["n_paraphrased_false_alarm"],
            "genuine_omissions_estimate": weak_audit["n_adjudicated"] - weak_audit["n_paraphrased_false_alarm"],
            "false_alarm_rate_within_weak_signals": weak_audit["false_alarm_rate"],
            "adjudicator": "Hy3 model; estimate, not human ground truth",
            "sha256": _sha256(WEAK_AUDIT),
        },
        "rule_signal_adjudication": {
            "n_cases": rule_audit["n_cases"],
            "n_adjudicated": rule_audit["n_adjudicated"],
            "cleared_false_alarms": rule_audit["n_cleared_false_alarm"],
            "false_alarm_rate": rule_audit["false_alarm_rate"],
            "adjudicator": "Hy3 full process judge; estimate, not human ground truth",
            "sha256": _sha256(RULE_AUDIT),
        },
        "combined_process_adjudication": {
            "raw_flags": sum(raw_flags),
            "cleared_false_alarms": sum(raw_flags) - sum(corrected_flags),
            "estimated_true_issues": sum(corrected_flags),
            "estimated_true_issue_ratio_among_raw_flags": (
                sum(corrected_flags) / sum(raw_flags) if sum(raw_flags) else None
            ),
        },
        "evaluator_validity": {
            "all_gold": summarize(validation_rows),
            "human_single_review_subset": summarize(human_rows),
            "constructed_injection_subset": summarize(constructed_rows),
            "human_subset_limitation": (
                "16条为早期单人复核样本，样本量小且与规则开发同源；单列报告，不与独立构造集混作人工双标金标。"
            ),
        },
        "provenance": {
            "validation_samples_sha256": _sha256(SAMPLES),
            "validation_details_sha256": _sha256(VALIDATION),
            "solver_and_judge_prompt_sha256": _sha256(ROOT / "src" / "hy3_process_eval" / "prompts.py"),
        },
    }

    out = ROOT / "results" / "submission_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_out = ROOT / "results" / "human_spot_check.csv"
    with audit_out.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "sample_id", "task_id", "difficulty", "final_correct",
            "manual_process_correct", "manual_first_error_step", "manual_error_type",
            "evaluator_process_correct", "evaluator_first_error_step", "evaluator_error_type",
            "localization_match", "false_positive", "manual_note",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in human_rows:
            gold = row["gold"]
            evaluation = row["evaluation"]
            writer.writerow({
                "sample_id": row["sample_id"],
                "task_id": row["task_id"],
                "difficulty": row["difficulty"],
                "final_correct": evaluation["final_correct"],
                "manual_process_correct": gold["process_correct"],
                "manual_first_error_step": gold.get("first_error_step") or "NONE",
                "manual_error_type": gold.get("error_type") or "NONE",
                "evaluator_process_correct": evaluation["process_correct"],
                "evaluator_first_error_step": evaluation.get("first_error_step") or "NONE",
                "evaluator_error_type": evaluation.get("error_type") or "NONE",
                "localization_match": (
                    evaluation.get("first_error_step") == gold.get("first_error_step")
                    if not gold["process_correct"] else ""
                ),
                "false_positive": (
                    not evaluation["process_correct"]
                    if gold["final_correct"] and gold["process_correct"] else ""
                ),
                "manual_note": row["audit_note"],
            })

    print(f"saved: {out}")
    print(f"saved: {audit_out}")


if __name__ == "__main__":
    main()
