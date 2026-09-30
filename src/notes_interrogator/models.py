from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ParseQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActivityMessage(BaseModel):
    role: Literal["user", "assistant", "unknown"]
    text: str
    time: datetime
    source_id: str


class ConversationBundle(BaseModel):
    conversation_id: str
    messages: list[ActivityMessage]
    source_ids: list[str]
    time_range: tuple[datetime, datetime]
    parse_quality: ParseQuality = ParseQuality.HIGH

    def to_text(self) -> str:
        lines: list[str] = []
        for msg in self.messages:
            lines.append(f"[{msg.role}] {msg.text}")
        return "\n\n".join(lines)


class TaskConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractedTask(BaseModel):
    title: str = Field(..., max_length=1024)
    notes: str = ""
    due: date | None = None
    confidence: TaskConfidence = TaskConfidence.MEDIUM
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()

    @field_validator("due", mode="before")
    @classmethod
    def parse_due(cls, v: object) -> date | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if cleaned.lower() in ("null", "none", "n/a"):
                return None
            if len(cleaned) >= 10:
                try:
                    return date.fromisoformat(cleaned[:10])
                except ValueError:
                    return None
        return v if isinstance(v, date) else None


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = Field(default_factory=list)


class RunReport(BaseModel):
    date: str
    bundles: int = 0
    extracted: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    tasks: list[ExtractedTask] | None = None

    def to_json_dict(self, include_tasks: bool) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude_none=True)
        if not include_tasks:
            data.pop("tasks", None)
        return data


class ProcessedEntry(BaseModel):
    created_at: datetime
    external_task_id: str | None = None
