from hy3_process_eval.metrics import summarize


def test_metrics_denominators():
    rows = [{
        "difficulty": "easy",
        "gold": {"final_correct": True, "process_correct": False, "first_error_step": "S1"},
        "evaluation": {"final_correct": True, "process_correct": False, "first_error_step": "S1", "error_type": "概念错误"},
    }]
    out = summarize(rows)
    assert out["localization_accuracy"] == 1.0
    assert out["flagged_true_issue_ratio"] == 1.0

