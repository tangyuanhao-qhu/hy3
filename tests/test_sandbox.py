from hy3_process_eval.sandbox import policy_check, run_tests


def test_runs_safe_function():
    result = run_tests("def add(a,b):\n    return a+b\n", ["add(2,3)==5"])
    assert result.all_passed


def test_denies_import_and_open():
    assert "Denied syntax" in policy_check("import os")
    assert "Denied call" in policy_check("open('x')")


def test_reports_failure():
    result = run_tests("def add(a,b):\n    return a-b\n", ["add(2,3)==5"])
    assert result.passed == 0 and result.total == 1

