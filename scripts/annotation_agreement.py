"""Inter-annotator agreement for the blind double-annotation sheet.

Reads results/human_audit.csv (the sheet produced by scripts/run_validation.py,
whose ann1_/ann2_ columns are filled in by two independent human annotators) and
reports:

  * coverage      - how many samples each annotator completed
  * raw agreement - share of samples where both annotated the same step
  * Cohen's kappa - chance-corrected agreement on the nominal step label
  * per-type      - agreement broken down by the intended error type
  * conflicts     - the exact sample ids that need third-party adjudication

Usage:
    PYTHONPATH=src python scripts/annotation_agreement.py results/human_audit.csv

Nothing here needs the sandbox or the model: it is pure bookkeeping over the CSV.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters assigning nominal labels."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    c1 = Counter(a for a, _ in pairs)
    c2 = Counter(b for _, b in pairs)
    expected = sum((c1[k] / n) * (c2[k] / n) for k in set(c1) | set(c2))
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def adjacent(a: str, b: str) -> bool:
    """True when two step labels refer to neighbouring steps, e.g. S2 vs S3."""
    if not (a.startswith("S") and b.startswith("S")):
        return False
    try:
        return abs(int(a[1:]) - int(b[1:])) == 1
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("results/human_audit.csv")
    if not path.exists():
        print(f"missing file: {path}")
        return 2

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    both = [r for r in rows if r.get("ann1_step", "").strip() and r.get("ann2_step", "").strip()]
    a1 = sum(1 for r in rows if r.get("ann1_step", "").strip())
    a2 = sum(1 for r in rows if r.get("ann2_step", "").strip())

    print(f"file              : {path}")
    print(f"samples           : {len(rows)}")
    print(f"annotator 1 done  : {a1}")
    print(f"annotator 2 done  : {a2}")
    print(f"both done         : {len(both)}")

    if not both:
        print("\nNo sample has been annotated by both annotators yet.")
        print("Fill the ann1_step / ann2_step columns in the CSV, then re-run.")
        return 0

    pairs = [(r["ann1_step"].strip(), r["ann2_step"].strip()) for r in both]
    agree = sum(1 for a, b in pairs if a == b)
    kappa = cohens_kappa(pairs)

    print()
    print(f"raw agreement     : {agree}/{len(both)} = {agree / len(both):.4f}")
    print(f"Cohen's kappa     : {kappa:.4f}" if kappa is not None else "Cohen's kappa     : n/a")
    if kappa is not None:
        verdict = "acceptable" if kappa >= 0.6 else "BELOW 0.6 - reconcile the codebook before trusting the gold"
        print(f"                    ({verdict})")

    # Agreement by intended error type -------------------------------------
    by_type: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row, pair in zip(both, pairs):
        by_type[row.get("intended_error_type") or "(none)"].append(pair)
    print("\nagreement by intended error type:")
    for key in sorted(by_type):
        items = by_type[key]
        hit = sum(1 for a, b in items if a == b)
        print(f"  {key:<12} {hit}/{len(items)} = {hit / len(items):.3f}" if items else f"  {key:<12} -")

    # Conflicts -------------------------------------------------------------
    conflicts = [r for r, (a, b) in zip(both, pairs) if a != b]
    print(f"\nconflicts needing adjudication: {len(conflicts)}")
    for row in conflicts:
        kind = "adjacent" if adjacent(row["ann1_step"], row["ann2_step"]) else "far/NONE"
        print(f"  {row['sample_id']:<6} {row['task_id']:<5} ann1={row['ann1_step']:<5} "
              f"ann2={row['ann2_step']:<5} ({kind})")

    # Real-issue disagreement (drives the false-positive audit) --------------
    ri = [(r.get("ann1_is_real_issue", "").strip(), r.get("ann2_is_real_issue", "").strip())
          for r in both if r.get("ann1_is_real_issue", "").strip() and r.get("ann2_is_real_issue", "").strip()]
    if ri:
        hit = sum(1 for a, b in ri if a == b)
        print(f"\nis_real_issue agreement: {hit}/{len(ri)} = {hit / len(ri):.4f} (kappa={cohens_kappa(ri):.4f})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
