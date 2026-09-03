from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    answer_accuracy = sum(bool(r["evaluation"]["final_correct"]) for r in rows) / n
    process_accuracy = sum(bool(r["evaluation"]["process_correct"]) for r in rows) / n
    error_dist = Counter(r["evaluation"].get("error_type") or "无错误" for r in rows)

    by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_difficulty[row["difficulty"]].append(row)
    difficulty = {}
    for level, items in by_difficulty.items():
        difficulty[level] = {
            "n": len(items),
            "answer_accuracy": sum(i["evaluation"]["final_correct"] for i in items) / len(items),
            "process_accuracy": sum(i["evaluation"]["process_correct"] for i in items) / len(items),
        }

    wrong_process = [r for r in rows if not r["gold"]["process_correct"]]
    localized = [
        r for r in wrong_process
        if r["evaluation"].get("first_error_step") == r["gold"].get("first_error_step")
    ]
    correct_answer_gold_process = [
        r for r in rows if r["gold"]["final_correct"] and r["gold"]["process_correct"]
    ]
    false_positives = [r for r in correct_answer_gold_process if not r["evaluation"]["process_correct"]]
    flagged_correct_answer = [
        r for r in rows if r["gold"]["final_correct"] and not r["evaluation"]["process_correct"]
    ]
    true_issues = [r for r in flagged_correct_answer if not r["gold"]["process_correct"]]
    return {
        "n": n,
        "answer_accuracy": answer_accuracy,
        "process_accuracy": process_accuracy,
        "error_type_distribution": dict(error_dist),
        "difficulty": difficulty,
        "localization_accuracy": len(localized) / len(wrong_process) if wrong_process else None,
        "localization_denominator": len(wrong_process),
        "false_positive_rate": len(false_positives) / len(correct_answer_gold_process) if correct_answer_gold_process else None,
        "false_positive_denominator": len(correct_answer_gold_process),
        "flagged_correct_answer_count": len(flagged_correct_answer),
        "flagged_true_issue_ratio": len(true_issues) / len(flagged_correct_answer) if flagged_correct_answer else None,
    }


def summarize_model_outputs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a real model run where no human gold labels are available."""
    n = len(rows)
    if not n:
        return {"n": 0}
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "answer": 0, "process": 0})
    errors = Counter()
    for row in rows:
        level = row["task"]["difficulty"]
        ev = row["evaluation"]
        counts[level]["n"] += 1
        counts[level]["answer"] += int(ev["final_correct"])
        counts[level]["process"] += int(ev["process_correct"])
        errors[ev.get("error_type") or "无错误"] += 1
    return {
        "n": n,
        "answer_accuracy": sum(r["evaluation"]["final_correct"] for r in rows) / n,
        "process_accuracy": sum(r["evaluation"]["process_correct"] for r in rows) / n,
        "correct_but_unsupported_rate": sum(
            r["evaluation"]["final_correct"] and not r["evaluation"]["process_correct"] for r in rows
        ) / n,
        "error_type_distribution": dict(errors),
        "difficulty": {
            level: {
                "n": values["n"],
                "answer_accuracy": values["answer"] / values["n"],
                "process_accuracy": values["process"] / values["n"],
            }
            for level, values in counts.items()
        },
    }
