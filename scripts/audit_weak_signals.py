"""Adjudicate the rule layer's weak signal.

deterministic_review() flags a solution with error_type="条件遗漏" whenever a
rubric.required_concepts keyword is absent from the model's step text. That is a
vocabulary check, not a reasoning check: a solution may state the same idea in
different words and still get flagged. This script asks Hy3 to decide, for each
weak-signal case, whether the concept is genuinely omitted or merely paraphrased,
so the headline process metrics can be reported with a quantified correction.

Usage:
    PYTHONPATH=src python scripts/audit_weak_signals.py [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]

JUDGE_SYSTEM = """你是一名严格的算法题解评审员。
你会拿到：一道编程题、题目要求必须说明的若干"关键概念"、以及一份模型给出的解题步骤。
其中某个关键概念的字面关键词没有出现在步骤文本里。

你的任务：判断该概念是被【真正遗漏】了，还是【用不同措辞表达了同一含义】。

判据：
- 真正遗漏：步骤中完全找不到该概念所描述的推理、判断或处理，且该缺失会导致解法不完整。
- 换词表达：步骤中虽未使用该字面词，但明确描述了等价的处理逻辑或结论。

只输出 JSON，不要解释，不要代码块：
{"addressed": true|false, "confidence": 0.0-1.0, "reason": "一句话中文理由"}
"""

MAX_ATTEMPTS = 4


def _missing_concepts(task: dict, steps: list[dict]) -> list[str]:
    combined = " ".join(f"{s['claim']} {s['evidence']}" for s in steps).lower()
    return [c for c in task.get("rubric", {}).get("required_concepts", []) if c.lower() not in combined]


def _json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in response")
        return json.loads(text[start:end + 1])


def _adjudicate(client: OpenAI, model: str, effort: str, task: dict, steps: list[dict],
                concepts: list[str]) -> dict:
    payload = {
        "task_id": task["id"],
        "prompt": task["prompt"],
        "signature": task["signature"],
        "constraints": task["constraints"],
        "required_concepts": task["rubric"]["required_concepts"],
        "missing_concepts": concepts,
        "solution_steps": steps,
    }
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.0,
                top_p=1.0,
                extra_body={"chat_template_kwargs": {"reasoning_effort": effort}},
            )
            out = _json_object(resp.choices[0].message.content or "")
            return {
                "addressed": bool(out.get("addressed")),
                "confidence": float(out.get("confidence", 0.5)),
                "reason": str(out.get("reason", "")),
            }
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS:
                import time
                time.sleep(5 * (2 ** (attempt - 1)))
    return {"addressed": None, "confidence": 0.0, "reason": f"FAILED: {last}"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--input", default="results/hy3_benchmark.json")
    parser.add_argument("--output", default="results/weak_signal_audit.json")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if os.getenv("DEMO_MODE", "0") == "1":
        raise SystemExit("DEMO_MODE=1 - this script needs a real model. Set DEMO_MODE=0 in .env")
    client = OpenAI(base_url=os.getenv("HY3_BASE_URL"), api_key=os.getenv("HY3_API_KEY"))
    model = os.getenv("HY3_MODEL", "hy3")
    effort = os.getenv("HY3_REASONING_EFFORT", "high")

    report = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    tasks = {json.loads(l)["id"]: json.loads(l)
             for l in (ROOT / "data" / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}

    # Only the weak signal is in scope: ruled flawed by `rules` but with no forbidden_claim hit.
    cases = []
    for row in report["rows"]:
        if row.get("evaluation") is None:
            continue
        pr = row["evaluation"]["process_review"]
        if pr["source"] != "rules" or pr["process_correct"]:
            continue
        tid = row["task"]["id"]
        steps = row["solution"]["steps"]
        combined = " ".join(f"{s['claim']} {s['evidence']}" for s in steps)
        hit = any(re.search(rule["pattern"], combined, flags=re.I)
                  for rule in tasks[tid]["rubric"].get("forbidden_claims", []))
        if hit:
            continue  # strong signal - not a vocabulary artifact
        concepts = _missing_concepts(tasks[tid], steps)
        cases.append({"task_id": tid, "difficulty": row["task"]["difficulty"],
                      "missing_concepts": concepts, "steps": steps})

    print(f"weak-signal cases to adjudicate: {len(cases)}", flush=True)

    results: list[dict] = []
    lock = threading.Lock()
    done = 0

    def work(case: dict) -> dict:
        verdict = _adjudicate(client, model, effort, tasks[case["task_id"]], case["steps"],
                              case["missing_concepts"])
        return {**case, **verdict}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, c) for c in cases]
        for future in as_completed(futures):
            res = future.result()
            with lock:
                results.append(res)
                done += 1
                print(f"[{done}/{len(cases)}] {res['task_id']} addressed={res['addressed']}", flush=True)

    order = {c["task_id"]: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: order.get(r["task_id"], 10**9))

    ok = [r for r in results if r["addressed"] is not None]
    paraphrased = [r for r in ok if r["addressed"]]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "n_cases": len(results),
        "n_adjudicated": len(ok),
        "n_paraphrased_false_alarm": len(paraphrased),
        "false_alarm_rate": len(paraphrased) / len(ok) if ok else None,
        "results": results,
    }
    (ROOT / args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nadjudicated : {len(ok)}/{len(results)}")
    print(f"paraphrased (false alarm): {len(paraphrased)}  -> rate {out['false_alarm_rate']}")
    print(f"saved: {ROOT / args.output}")


if __name__ == "__main__":
    main()
