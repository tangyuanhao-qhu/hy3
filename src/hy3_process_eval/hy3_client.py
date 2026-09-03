from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # Allows offline validation before optional app dependencies are installed.
    OpenAI = None  # type: ignore[assignment]

from .prompts import JUDGE_SYSTEM, SOLVER_SYSTEM
from .schemas import ProcessReview, Solution, StepReview


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Hy3 response does not contain a JSON object")
        return json.loads(text[start : end + 1])


class Hy3Client:
    def __init__(self) -> None:
        self.base_url = os.getenv("HY3_BASE_URL", "http://127.0.0.1:8000/v1")
        self.api_key = os.getenv("HY3_API_KEY", "EMPTY")
        self.model = os.getenv("HY3_MODEL", "hy3")
        self.reasoning_effort = os.getenv("HY3_REASONING_EFFORT", "high")
        self.demo_mode = os.getenv("DEMO_MODE", "0") == "1"
        if not self.demo_mode and OpenAI is None:
            raise RuntimeError("Missing dependency 'openai'. Run: pip install -e .")
        self.client = None if self.demo_mode else OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _chat(self, system: str, user: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Hy3 call requested while DEMO_MODE=1")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            top_p=1.0,
            extra_body={"chat_template_kwargs": {"reasoning_effort": self.reasoning_effort}},
        )
        return _json_object(response.choices[0].message.content or "")

    def solve(self, task: dict[str, Any]) -> Solution:
        if self.demo_mode:
            return Solution.from_dict({
                "task_id": task["id"],
                "summary": task["demo_solution"]["summary"],
                "steps": task["demo_solution"]["steps"],
                "code": task["reference_solution"],
                "final_answer": "implemented",
            })
        payload = self._chat(SOLVER_SYSTEM, json.dumps({
            "task_id": task["id"],
            "prompt": task["prompt"],
            "signature": task["signature"],
            "constraints": task["constraints"],
        }, ensure_ascii=False))
        payload["task_id"] = task["id"]
        return Solution.from_dict(payload)

    def review(self, task: dict[str, Any], solution: Solution, evidence: dict[str, Any]) -> ProcessReview:
        payload = self._chat(JUDGE_SYSTEM, json.dumps({
            "task": {k: task[k] for k in ("id", "prompt", "signature", "constraints", "rubric")},
            "solution": solution.to_dict(),
            "test_evidence": evidence,
        }, ensure_ascii=False))
        return ProcessReview(
            process_correct=bool(payload["process_correct"]),
            first_error_step=payload.get("first_error_step"),
            error_type=payload.get("error_type"),
            confidence=float(payload.get("confidence", 0.5)),
            step_reviews=[StepReview(**item) for item in payload.get("step_reviews", [])],
            source="hy3",
        )
