from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .schemas import TestResult


DENIED_CALLS = {"eval", "exec", "compile", "open", "input", "__import__", "breakpoint"}
DENIED_NAMES = {"globals", "locals", "vars", "dir", "help", "memoryview"}
ALLOWED_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
    "frozenset", "int", "isinstance", "len", "list", "map", "max", "min", "next",
    "pow", "range", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "zip", "Exception", "ValueError", "TypeError", "IndexError", "KeyError",
}


def policy_check(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} at line {exc.lineno}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            return f"Denied syntax: {type(node).__name__}"
        if isinstance(node, ast.Name) and (node.id in DENIED_NAMES or node.id.startswith("__")):
            return f"Denied name: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"Denied attribute: {node.attr}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DENIED_CALLS:
            return f"Denied call: {node.func.id}"
    return None


def run_tests(code: str, tests: list[str], timeout: float = 3.0) -> TestResult:
    violation = policy_check(code)
    if violation:
        return TestResult(passed=0, total=len(tests), policy_error=violation)
    runner = r'''
import json, sys
SAFE_NAMES = json.loads(sys.stdin.readline())
CODE = json.loads(sys.stdin.readline())
TESTS = json.loads(sys.stdin.readline())
safe = {name: getattr(__builtins__, name) for name in SAFE_NAMES if hasattr(__builtins__, name)}
ns = {"__builtins__": safe}
results = []
try:
    exec(compile(CODE, "<candidate>", "exec"), ns, ns)
    for expr in TESTS:
        try:
            ok = bool(eval(compile(expr, "<test>", "eval"), ns, ns))
            results.append({"test": expr, "passed": ok, "error": "" if ok else "assertion false"})
        except Exception as exc:
            results.append({"test": expr, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
except Exception as exc:
    results = [{"test": expr, "passed": False, "error": f"load error: {type(exc).__name__}: {exc}"} for expr in TESTS]
print(json.dumps(results, ensure_ascii=False))
'''
    payload = "\n".join((json.dumps(sorted(ALLOWED_BUILTINS)), json.dumps(code), json.dumps(tests))) + "\n"
    env = {"PYTHONHASHSEED": "0", "PATH": os.getenv("PATH", "")}
    try:
        with tempfile.TemporaryDirectory(prefix="hy3_eval_") as tmp:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-c", runner], input=payload, text=True,
                capture_output=True, timeout=timeout, cwd=Path(tmp), env=env,
            )
    except subprocess.TimeoutExpired:
        return TestResult(passed=0, total=len(tests), timed_out=True)
    if proc.returncode != 0:
        return TestResult(passed=0, total=len(tests), policy_error=proc.stderr.strip() or "runner failed")
    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return TestResult(passed=0, total=len(tests), policy_error="runner returned invalid JSON")
    failures = [{"test": r["test"], "error": r["error"]} for r in rows if not r["passed"]]
    return TestResult(passed=len(rows) - len(failures), total=len(rows), failures=failures)

