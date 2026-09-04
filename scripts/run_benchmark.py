from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Transient API failures are retried with exponential backoff; a task that still
# fails after all attempts is recorded as an error row instead of aborting the run.
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 5


def _solve_one(client: Hy3Client, evaluator: ProcessEvaluator, task: dict) -> dict:
    """Evaluate one task. Retries transient API errors, gives up after MAX_ATTEMPTS."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            solution = client.solve(task)
            evaluation = evaluator.evaluate(task, solution)
            return {
                "task": {"id": task["id"], "difficulty": task["difficulty"]},
                "solution": solution.to_dict(),
                "evaluation": evaluation.to_dict(),
            }
        except Exception as exc:  # noqa: BLE001 - one bad task must not kill the run
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    return {
        "task": {"id": task["id"], "difficulty": task["difficulty"]},
        "solution": None,
        "evaluation": None,
        "error": last_error,
    }


def _write(report: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 means all tasks")
    parser.add_argument("--output", default="results/hy3_benchmark.json")
    parser.add_argument("--workers", type=int, default=4, help="parallel model calls")
    parser.add_argument("--resume", action="store_true", help="skip tasks already present in --output")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    client = Hy3Client()
    evaluator = ProcessEvaluator(client=client)
    tasks = load_tasks(ROOT / "data")
    if args.limit:
        tasks = tasks[: args.limit]

    output = ROOT / args.output
    done: dict[str, dict] = {}
    if args.resume and output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            for row in previous.get("rows", []):
                tid = row["task"]["id"]
                if row.get("evaluation") is not None:
                    done[tid] = row
        except Exception as exc:  # noqa: BLE001
            print(f"resume: could not read {output} ({exc}); starting fresh")

    pending = [t for t in tasks if t["id"] not in done]
    print(f"tasks={len(tasks)} already_done={len(done)} pending={len(pending)} workers={args.workers}", flush=True)

    rows = list(done.values())
    lock = threading.Lock()
    completed = 0

    def _collect(row: dict) -> None:
        nonlocal completed
        with lock:
            rows.append(row)
            completed += 1
            if row.get("evaluation") is not None:
                print(f"[{completed}/{len(pending)}] {row['task']['id']} {row['evaluation']['verdict']}", flush=True)
            else:
                print(f"[{completed}/{len(pending)}] {row['task']['id']} FAILED {row.get('error')}", flush=True)
            # Checkpoint after every task so an interrupted run is never lost.
            summary = summarize_model_outputs([r for r in rows if r.get("evaluation") is not None])
            _write({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "demo_mode": client.demo_mode,
                "model": client.model,
                "summary": summary,
                "rows": rows,
            }, output)

    if args.workers <= 1:
        for task in pending:
            _collect(_solve_one(client, evaluator, task))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_solve_one, client, evaluator, t): t for t in pending}
            for future in as_completed(futures):
                _collect(future.result())

    # Re-emit in the canonical task order so the file is reproducible regardless of
    # the order in which parallel workers happened to finish.
    order = {t["id"]: i for i, t in enumerate(tasks)}
    rows.sort(key=lambda r: order.get(r["task"]["id"], 10**9))

    ok_rows = [r for r in rows if r.get("evaluation") is not None]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo_mode": client.demo_mode,
        "model": client.model,
        "summary": summarize_model_outputs(ok_rows),
        "rows": rows,
    }
    _write(report, output)

    failed = [r["task"]["id"] for r in rows if r.get("evaluation") is None]
    if failed:
        print(f"failed tasks ({len(failed)}): {failed}")
        print("re-run with --resume to retry only those")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
