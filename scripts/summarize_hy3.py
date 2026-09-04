"""Summarize a real Hy3 benchmark run: rates, bootstrap CIs, per-level and per-type breakdown.

Usage:
    PYTHONPATH=src python scripts/summarize_hy3.py [results/hy3_benchmark.json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from hy3_process_eval.metrics import bootstrap_ci

LEVELS = ("easy", "medium", "hard")


def _pct(x: float | None) -> str:
    return "  n/a" if x is None else f"{x * 100:5.1f}%"


def _ci(values: list[int]) -> str:
    if not values:
        return ""
    bounds = bootstrap_ci(values)
    if bounds is None:
        return ""
    return f"[{bounds[0]:.3f}, {bounds[1]:.3f}]"


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/hy3_benchmark.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    if report.get("demo_mode"):
        print("!! WARNING: this file was produced in DEMO_MODE - it is NOT a model result.")
        return

    rows = [r for r in report["rows"] if r.get("evaluation") is not None]
    failed = [r for r in report["rows"] if r.get("evaluation") is None]
    n = len(rows)
    print(f"file   : {path}")
    print(f"model  : {report['model']}   generated_at: {report['generated_at']}")
    print(f"rows   : {n} ok, {len(failed)} failed")
    if failed:
        print(f"failed : {[r['task']['id'] for r in failed]}")
    if not n:
        return

    def correct(row: dict, key: str) -> int:
        return 1 if row["evaluation"][key] else 0

    ans = [correct(r, "final_correct") for r in rows]
    proc = [correct(r, "process_correct") for r in rows]
    cbu = [1 if (r["evaluation"]["final_correct"] and not r["evaluation"]["process_correct"]) else 0 for r in rows]

    print("\n=== OVERALL ===")
    print(f"answer_accuracy            : {_pct(sum(ans) / n)}  {_ci(ans)}")
    print(f"process_accuracy (passed)  : {_pct(sum(proc) / n)}  {_ci(proc)}")
    print(f"process_flag_rate          : {_pct(1 - sum(proc) / n)}")
    print(f"correct_but_unsupported    : {_pct(sum(cbu) / n)}  ({sum(cbu)} samples)")

    print("\n=== BY DIFFICULTY ===")
    print(f"{'level':8} {'n':>4} {'answer':>8} {'process':>8} {'flag':>8} {'cbu':>8}")
    by_level: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_level[r["task"]["difficulty"]].append(r)
    level_answer: dict[str, float] = {}
    for level in LEVELS:
        items = by_level.get(level, [])
        if not items:
            continue
        a = [correct(r, "final_correct") for r in items]
        p = [correct(r, "process_correct") for r in items]
        f = [1 - x for x in p]
        c = [1 if (r["evaluation"]["final_correct"] and not r["evaluation"]["process_correct"]) else 0 for r in items]
        level_answer[level] = sum(a) / len(items)
        print(f"{level:8} {len(items):>4} {_pct(sum(a)/len(items)):>8} {_pct(sum(p)/len(items)):>8} "
              f"{_pct(sum(f)/len(items)):>8} {_pct(sum(c)/len(items)):>8}   answer CI {_ci(a)}")

    if len(level_answer) >= 2:
        print("\n=== CAPABILITY CLIFF (answer accuracy drop) ===")
        prev_level, prev_val = None, None
        for level in LEVELS:
            if level not in level_answer:
                continue
            if prev_val is not None:
                delta = level_answer[level] - prev_val
                print(f"  {prev_level} -> {level}: {prev_val:.3f} -> {level_answer[level]:.3f}  ({delta:+.3f})")
            prev_level, prev_val = level, level_answer[level]

    print("\n=== ERROR TYPE DISTRIBUTION (predicted) ===")
    dist = Counter(r["evaluation"].get("error_type") or "无错误" for r in rows)
    for k, v in dist.most_common():
        print(f"  {k:12} {v:>4}  ({v / n * 100:.1f}%)")

    print("\n=== VERDICT DISTRIBUTION ===")
    for k, v in Counter(r["evaluation"]["verdict"] for r in rows).most_common():
        print(f"  {k:28} {v:>4}  ({v / n * 100:.1f}%)")

    print("\n=== REVIEW SOURCE (rule veto vs Hy3 judge) ===")
    for k, v in Counter(r["evaluation"]["process_review"]["source"] for r in rows).most_common():
        print(f"  {k:12} {v:>4}  ({v / n * 100:.1f}%)")

    print("\n=== HIDDEN TEST PASS RATE ===")
    totals = [r["evaluation"]["hidden_tests"]["total"] for r in rows]
    passed = [r["evaluation"]["hidden_tests"]["passed"] for r in rows]
    print(f"  assertions passed: {sum(passed)} / {sum(totals)}  ({sum(passed) / sum(totals) * 100:.1f}%)")
    full = sum(1 for r in rows if r["evaluation"]["hidden_tests"]["passed"] == r["evaluation"]["hidden_tests"]["total"])
    print(f"  tasks fully passing: {full} / {n}")

    print("\n=== WORST TASKS (answer wrong) ===")
    wrong = [r for r in rows if not r["evaluation"]["final_correct"]]
    for r in wrong[:20]:
        pr = r["evaluation"]["process_review"]
        print(f"  {r['task']['id']:5} {r['task']['difficulty']:7} hidden {r['evaluation']['hidden_tests']['passed']}"
              f"/{r['evaluation']['hidden_tests']['total']}  type={pr.get('error_type')}  step={pr.get('first_error_step')}")
    if len(wrong) > 20:
        print(f"  ... and {len(wrong) - 20} more")

    _report_correction(path, rows, n)


def _report_correction(path: Path, rows: list[dict], n: int) -> None:
    """Report metrics after semantic adjudication of rule-layer flags.

    deterministic_review() flags `条件遗漏` whenever a required_concepts keyword is
    absent, which fires on paraphrase. scripts/audit_weak_signals.py asks the model
    whether each such flag is a genuine omission or merely a rewording.  An optional
    rule-signal audit similarly checks non-weak regex hits with the full process judge.
    Cases cleared by either audit are dropped here.
    """
    suffix = path.stem.removeprefix("hy3_benchmark")
    audit_path = path.parent / f"weak_signal_audit{suffix}.json"
    if not audit_path.exists():
        print("\n=== CORRECTED (vocabulary artifact removed) ===")
        print("  run scripts/audit_weak_signals.py first to enable this section")
        return

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    false_alarm = {r["task_id"] for r in audit["results"] if r.get("addressed") is True}
    rule_audit_path = path.parent / f"rule_signal_audit{suffix}.json"
    if rule_audit_path.exists():
        rule_audit = json.loads(rule_audit_path.read_text(encoding="utf-8"))
        false_alarm.update(
            r["task_id"] for r in rule_audit["results"]
            if r.get("semantic_review", {}).get("process_correct") is True
        )

    # Keep every raw flag except cases explicitly cleared by one of the semantic
    # adjudication files.  If the non-weak audit is absent, strong rule flags are
    # conservatively retained for backward compatibility.
    kept: list[int] = []
    for row in rows:
        tid = row["task"]["id"]
        pr = row["evaluation"]["process_review"]
        if pr["process_correct"]:
            kept.append(0)
            continue
        kept.append(0 if tid in false_alarm else 1)

    dropped = sum(1 for row, k in zip(rows, kept)
                  if not row["evaluation"]["process_correct"] and not k)
    cbu = [1 if (r["evaluation"]["final_correct"] and k) else 0 for r, k in zip(rows, kept)]
    raw_flag = sum(0 if r["evaluation"]["process_correct"] else 1 for r in rows)

    print("\n=== CORRECTED (semantic adjudication applied) ===")
    print(f"  rule flags cleared as false alarms : {dropped}")
    print(f"  process_flag_rate   : {_pct(raw_flag / n)} -> {_pct(sum(kept) / n)}")
    corrected_pass = [1 - flag for flag in kept]
    print(f"  process_accuracy    : {_pct(1 - raw_flag / n)} -> {_pct(sum(corrected_pass) / n)}   {_ci(corrected_pass)}")
    print(f"  correct_but_unsupported : {_pct(sum(cbu) / n)}  ({sum(cbu)} samples)")

    print("\n  by level:")
    per_level: dict[str, list[int]] = defaultdict(list)
    for row, k in zip(rows, kept):
        per_level[row["task"]["difficulty"]].append(k)
    for level in LEVELS:
        vals = per_level.get(level, [])
        if vals:
            print(f"    {level:8} flag {_pct(sum(vals) / len(vals))}")
    print("\n  NOTE: the correction is adjudicated by the model, not by humans.")
    print("  Treat it as an estimate; the uncorrected figures above are the raw measurement.")


if __name__ == "__main__":
    main()
