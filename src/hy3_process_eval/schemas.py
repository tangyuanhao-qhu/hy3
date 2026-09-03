from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Step:
    id: str
    claim: str
    evidence: str = ""


@dataclass
class Solution:
    task_id: str
    summary: str
    steps: list[Step]
    code: str
    final_answer: str = "implemented"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Solution":
        steps = [Step(**s) for s in payload.get("steps", [])]
        return cls(
            task_id=str(payload.get("task_id", "")),
            summary=str(payload.get("summary", "")),
            steps=steps,
            code=str(payload.get("code", "")),
            final_answer=str(payload.get("final_answer", "implemented")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    passed: int
    total: int
    failures: list[dict[str, str]] = field(default_factory=list)
    policy_error: str | None = None
    timed_out: bool = False

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed == self.total and not self.policy_error


@dataclass
class StepReview:
    step_id: str
    status: str
    error_type: str | None = None
    reason: str = ""


@dataclass
class ProcessReview:
    process_correct: bool
    first_error_step: str | None
    error_type: str | None
    step_reviews: list[StepReview]
    confidence: float
    source: str


@dataclass
class Evaluation:
    task_id: str
    final_correct: bool
    process_correct: bool
    verdict: str
    first_error_step: str | None
    error_type: str | None
    visible_tests: TestResult
    hidden_tests: TestResult
    process_review: ProcessReview

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

