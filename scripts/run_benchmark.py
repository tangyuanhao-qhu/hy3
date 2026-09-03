from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

from hy3_process_eval.dataset import load_tasks
from hy3_process_eval.evaluator import ProcessEvaluator
from hy3_process_eval.hy3_client import Hy3Client
from hy3_process_eval.metrics import summarize_model_outputs


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 means all tasks")
    parser.add_argument("--output", default="results/hy3_benchmark.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    client = Hy3Client()
    evaluator = ProcessEvaluator(client=client)
    tasks = load_tasks(ROOT / "data")
    if args.limit:
        tasks = tasks[: args.limit]
    rows = []
    for task in tasks:
        solution = client.solve(task)
        evaluation = evaluator.evaluate(task, solution)
        rows.append({"task": {"id": task["id"], "difficulty": task["difficulty"]}, "solution": solution.to_dict(), "evaluation": evaluation.to_dict()})
        print(task["id"], evaluation.verdict)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo_mode": client.demo_mode,
        "model": client.model,
        "summary": summarize_model_outputs(rows),
        "rows": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
