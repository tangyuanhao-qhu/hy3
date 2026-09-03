from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return records


def load_tasks(data_dir: str | Path = "data") -> list[dict[str, Any]]:
    return load_jsonl(Path(data_dir) / "tasks.jsonl")


def task_index(data_dir: str | Path = "data") -> dict[str, dict[str, Any]]:
    return {task["id"]: task for task in load_tasks(data_dir)}

