from __future__ import annotations

import csv
import json
from pathlib import Path

from hy3_process_eval.dataset import load_jsonl, task_index
from hy3_process_eval.evaluator import ProcessEvaluator
from hy3_process_eval.metrics import summarize
from hy3_process_eval.schemas import Solution


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tasks = task_index(ROOT / "data")
    samples = load_jsonl(ROOT / "data" / "validation_samples.jsonl")
    evaluator = ProcessEvaluator(use_llm_judge=False)
    rows = []
    for sample in samples:
        task = tasks[sample["task_id"]]
        evaluation = evaluator.evaluate(task, Solution.from_dict(sample["solution"]))
        rows.append({
            "sample_id": sample["id"], "task_id": task["id"], "difficulty": task["difficulty"],
            "gold": sample["gold"], "evaluation": evaluation.to_dict(), "audit_note": sample["audit_note"],
        })
    metrics = summarize(rows)
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "validation_details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "validation_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # The audit sheet doubles as the blind double-annotation form: the right-hand
    # columns are intentionally left empty for two independent human annotators,
    # with a final adjudication column for disagreements. See docs/ANNOTATION_PROTOCOL.md.
    with (out_dir / "human_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "sample_id", "task_id", "difficulty", "gold_source", "intended_error_type",
            "gold_final_correct", "gold_process_correct", "gold_first_error_step",
            "pred_process_correct", "pred_first_error_step", "pred_error_type",
            "ann1_step", "ann1_type", "ann1_is_real_issue",
            "ann2_step", "ann2_type", "ann2_is_real_issue",
            "agreement", "adjudicated_step", "adjudicated_type", "adjudicator_note",
            "audit_note",
        ])
        writer.writeheader()
        for row, sample in zip(rows, samples):
            construction = sample.get("construction") or {}
            writer.writerow({
                "sample_id": row["sample_id"], "task_id": row["task_id"], "difficulty": row["difficulty"],
                "gold_source": sample.get("source", "human"),
                "intended_error_type": construction.get("intended_type", ""),
                "gold_final_correct": row["gold"]["final_correct"],
                "gold_process_correct": row["gold"]["process_correct"],
                "gold_first_error_step": row["gold"].get("first_error_step"),
                "pred_process_correct": row["evaluation"]["process_correct"],
                "pred_first_error_step": row["evaluation"].get("first_error_step"),
                "pred_error_type": row["evaluation"].get("error_type"),
                # left blank on purpose for human annotators
                "ann1_step": "", "ann1_type": "", "ann1_is_real_issue": "",
                "ann2_step": "", "ann2_type": "", "ann2_is_real_issue": "",
                "agreement": "", "adjudicated_step": "", "adjudicated_type": "",
                "adjudicator_note": "",
                "audit_note": row["audit_note"],
            })
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

