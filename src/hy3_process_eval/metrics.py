from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Any, Callable


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def bootstrap_ci(values: list[int], n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = 20260903) -> list[float] | None:
    """Percentile bootstrap CI for the mean of 0/1 indicators.

    Pure-Python on purpose: keeps the metric layer dependency-free and the
    result reproducible given the fixed seed.
    """
    n = len(values)
    if n == 0:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        total = 0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(int((1 - alpha / 2) * n_boot), n_boot - 1)]
    return [lo, hi]


def _binary_stats(gold_flawed: list[int], pred_flawed: list[int]) -> dict[str, Any]:
    """Precision/recall/F1 of 'this solution has a process problem' detection."""
    tp = sum(1 for g, p in zip(gold_flawed, pred_flawed) if g and p)
    fp = sum(1 for g, p in zip(gold_flawed, pred_flawed) if not g and p)
    fn = sum(1 for g, p in zip(gold_flawed, pred_flawed) if g and not p)
    tn = sum(1 for g, p in zip(gold_flawed, pred_flawed) if not g and not p)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else (
        0.0 if (precision is not None and recall is not None) else None
    )
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "agreement_with_gold": (tp + tn) / len(gold_flawed) if gold_flawed else None,
    }


def _level_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    gold_flawed = [0 if i["gold"]["process_correct"] else 1 for i in items]
    pred_flawed = [0 if i["evaluation"]["process_correct"] else 1 for i in items]
    wrong_process = [r for r in items if not r["gold"]["process_correct"]]
    localized = [
        r for r in wrong_process
        if r["evaluation"].get("first_error_step") == r["gold"].get("first_error_step")
    ]
    correct_gold = [r for r in items if r["gold"]["final_correct"] and r["gold"]["process_correct"]]
    false_pos = [r for r in correct_gold if not r["evaluation"]["process_correct"]]
    return {
        "n": len(items),
        "answer_accuracy": sum(bool(i["evaluation"]["final_correct"]) for i in items) / len(items),
        "process_flag_rate": _mean(pred_flawed),
        "gold_process_flaw_rate": _mean(gold_flawed),
        "localization_accuracy": len(localized) / len(wrong_process) if wrong_process else None,
        "localization_denominator": len(wrong_process),
        "false_positive_rate": len(false_pos) / len(correct_gold) if correct_gold else None,
        "false_positive_denominator": len(correct_gold),
        "detection": _binary_stats(gold_flawed, pred_flawed),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize an evaluator run against gold labels.

    Naming note: ``process_accuracy`` is retained for backward compatibility but
    it is the *flag rate* (1 - share judged process-correct), NOT accuracy
    against gold. Accuracy against gold lives in ``detection``.
    """
    n = len(rows)
    if not n:
        return {"n": 0}

    error_dist = Counter(r["evaluation"].get("error_type") or "无错误" for r in rows)

    by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_difficulty[row["difficulty"]].append(row)
    difficulty = {level: _level_stats(items) for level, items in sorted(by_difficulty.items())}

    gold_flawed = [0 if r["gold"]["process_correct"] else 1 for r in rows]
    pred_flawed = [0 if r["evaluation"]["process_correct"] else 1 for r in rows]

    wrong_process = [r for r in rows if not r["gold"]["process_correct"]]
    localized = [
        r for r in wrong_process
        if r["evaluation"].get("first_error_step") == r["gold"].get("first_error_step")
    ]
    # Of the gold-flawed samples the evaluator actually caught, how many were
    # localized to the exact step? Separates "caught but wrong step" from total miss.
    caught = [r for r in wrong_process if not r["evaluation"]["process_correct"]]
    localized_among_caught = [r for r in caught if r["evaluation"].get("first_error_step") == r["gold"].get("first_error_step")]

    correct_answer_gold_process = [
        r for r in rows if r["gold"]["final_correct"] and r["gold"]["process_correct"]
    ]
    false_positives = [r for r in correct_answer_gold_process if not r["evaluation"]["process_correct"]]
    flagged_correct_answer = [
        r for r in rows if r["gold"]["final_correct"] and not r["evaluation"]["process_correct"]
    ]
    true_issues = [r for r in flagged_correct_answer if not r["gold"]["process_correct"]]

    gold_error_dist = Counter(r["gold"].get("error_type") or "无错误" for r in rows)

    # Bootstrap CIs over per-sample indicator vectors.
    ci_input: dict[str, list[int]] = {
        "answer_accuracy": [1 if r["evaluation"]["final_correct"] else 0 for r in rows],
        "process_flag_rate": pred_flawed,
    }
    if wrong_process:
        ci_input["localization_accuracy"] = [
            1 if r["evaluation"].get("first_error_step") == r["gold"].get("first_error_step") else 0
            for r in wrong_process
        ]
    if correct_answer_gold_process:
        ci_input["false_positive_rate"] = [
            1 if not r["evaluation"]["process_correct"] else 0 for r in correct_answer_gold_process
        ]
    confidence = {k: bootstrap_ci(v) for k, v in ci_input.items()}

    return {
        "n": n,
        # Retained for backward compatibility; this is the flag rate, not accuracy.
        "process_accuracy": _mean([1 - p for p in pred_flawed]),
        "process_flag_rate": _mean(pred_flawed),
        "answer_accuracy": _mean(ci_input["answer_accuracy"]),
        "error_type_distribution": dict(error_dist),
        "gold_error_type_distribution": dict(gold_error_dist),
        "difficulty": difficulty,
        "localization_accuracy": len(localized) / len(wrong_process) if wrong_process else None,
        "localization_denominator": len(wrong_process),
        "localization_accuracy_among_caught": (
            len(localized_among_caught) / len(caught) if caught else None
        ),
        "caught_denominator": len(caught),
        "false_positive_rate": len(false_positives) / len(correct_answer_gold_process) if correct_answer_gold_process else None,
        "false_positive_denominator": len(correct_answer_gold_process),
        "flagged_correct_answer_count": len(flagged_correct_answer),
        "flagged_true_issue_ratio": len(true_issues) / len(flagged_correct_answer) if flagged_correct_answer else None,
        "detection": _binary_stats(gold_flawed, pred_flawed),
        "confidence_interval_95": confidence,
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
        "process_flag_rate": sum(not r["evaluation"]["process_correct"] for r in rows) / n,
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
