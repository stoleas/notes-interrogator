from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from notes_interrogator.models import ExtractedTask, ProcessedEntry


def task_fingerprint(target: date, task: ExtractedTask) -> str:
    source_key = ",".join(sorted(task.source_ids))
    normalized_title = " ".join(task.title.lower().split())
    payload = f"{target.isoformat()}|{source_key}|{normalized_title}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ProcessedStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, ProcessedEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if isinstance(value, dict):
                self._data[key] = ProcessedEntry.model_validate(value)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {k: v.model_dump(mode="json") for k, v in self._data.items()}
        self.path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    def is_processed(self, fingerprint: str) -> bool:
        return fingerprint in self._data

    def mark_processed(self, fingerprint: str, external_task_id: str | None = None) -> None:
        self._data[fingerprint] = ProcessedEntry(
            created_at=datetime.now(timezone.utc),
            external_task_id=external_task_id,
        )
