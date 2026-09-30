from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from notes_interrogator.models import (
    ActivityMessage,
    ConversationBundle,
    ParseQuality,
)


def _record_id(record: dict, index: int) -> str:
    for key in ("id", "headerUniqueId"):
        if record.get(key):
            return str(record[key])
    payload = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(f"{index}:{payload}".encode()).hexdigest()[:16]


def _parse_time(raw: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def _conversation_id(title_url: str | None, pattern: str) -> str:
    if not title_url:
        return "unknown"
    match = re.search(pattern, title_url)
    if match:
        return match.group(1)
    return hashlib.sha256(title_url.encode()).hexdigest()[:16]


def _parse_json_text(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value.strip()
    if isinstance(parsed, str):
        return parsed.strip()
    if isinstance(parsed, dict):
        for key in ("text", "message", "content", "prompt", "query"):
            if key in parsed and isinstance(parsed[key], str):
                return parsed[key].strip()
        if "parts" in parsed and isinstance(parsed["parts"], list):
            parts: list[str] = []
            for part in parsed["parts"]:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            if parts:
                return "\n".join(parts).strip()
    return json.dumps(parsed, ensure_ascii=False)


def _messages_from_details(
    details: list[dict], when: datetime, source_id: str
) -> list[ActivityMessage]:
    messages: list[ActivityMessage] = []
    by_name: dict[str, str] = {}
    for item in details:
        name = str(item.get("name", "")).lower()
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            by_name[name] = value.strip()

    prompt_keys = ("prompt", "query", "user prompt", "your prompt")
    response_keys = ("response", "answer", "model response", "assistant response")

    for key in prompt_keys:
        if key in by_name:
            messages.append(
                ActivityMessage(role="user", text=by_name[key], time=when, source_id=source_id)
            )
            break
    for key in response_keys:
        if key in by_name:
            messages.append(
                ActivityMessage(
                    role="assistant", text=by_name[key], time=when, source_id=source_id
                )
            )
            break

    if not messages:
        chunks = [f"{k}: {v}" for k, v in by_name.items()]
        if chunks:
            messages.append(
                ActivityMessage(
                    role="unknown", text="\n".join(chunks), time=when, source_id=source_id
                )
            )
    return messages


def _messages_from_user_interactions(
    interactions: list[dict], when: datetime, source_id: str
) -> list[ActivityMessage]:
    messages: list[ActivityMessage] = []
    for item in interactions:
        ui = item.get("userInteraction") or item
        req = ui.get("request")
        resp = ui.get("response")
        if isinstance(req, str) and req.strip():
            messages.append(
                ActivityMessage(
                    role="user",
                    text=_parse_json_text(req),
                    time=when,
                    source_id=source_id,
                )
            )
        if isinstance(resp, str) and resp.strip():
            messages.append(
                ActivityMessage(
                    role="assistant",
                    text=_parse_json_text(resp),
                    time=when,
                    source_id=source_id,
                )
            )
    return messages


def _normalize_record(
    record: dict, index: int, tz: ZoneInfo, conv_pattern: str
) -> tuple[str, datetime, list[ActivityMessage], ParseQuality, str] | None:
    raw_time = record.get("time")
    if not isinstance(raw_time, str):
        return None
    when = _parse_time(raw_time, tz)
    source_id = _record_id(record, index)
    conv_id = _conversation_id(
        record.get("titleUrl") if isinstance(record.get("titleUrl"), str) else None,
        conv_pattern,
    )

    messages: list[ActivityMessage] = []
    quality = ParseQuality.HIGH

    details = record.get("details")
    if isinstance(details, list) and details:
        messages.extend(_messages_from_details(details, when, source_id))

    interactions = record.get("userInteractions")
    if isinstance(interactions, list) and interactions:
        messages.extend(_messages_from_user_interactions(interactions, when, source_id))

    if not messages:
        fallback_parts: list[str] = []
        for key in ("title", "subtitle", "description"):
            val = record.get(key)
            if isinstance(val, str) and val.strip():
                fallback_parts.append(val.strip())
        if fallback_parts:
            messages.append(
                ActivityMessage(
                    role="unknown",
                    text="\n".join(fallback_parts),
                    time=when,
                    source_id=source_id,
                )
            )
            quality = ParseQuality.LOW
        else:
            return None

    if quality != ParseQuality.LOW and any(m.role == "unknown" for m in messages):
        quality = ParseQuality.MEDIUM

    return conv_id, when, messages, quality, source_id


def load_bundles_for_date(
    activity_json_path: str | Path,
    target: date,
    timezone: str,
    conversation_id_pattern: str,
) -> list[ConversationBundle]:
    path = Path(activity_json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Takeout activity JSON must be a top-level array")

    tz = ZoneInfo(timezone)
    grouped: dict[str, list[ActivityMessage]] = {}
    qualities: dict[str, ParseQuality] = {}
    source_map: dict[str, list[str]] = {}

    for index, record in enumerate(data):
        if not isinstance(record, dict):
            continue
        normalized = _normalize_record(record, index, tz, conversation_id_pattern)
        if normalized is None:
            continue
        conv_id, when, messages, quality, source_id = normalized
        if when.date() != target:
            continue
        grouped.setdefault(conv_id, []).extend(messages)
        source_map.setdefault(conv_id, []).append(source_id)
        prev = qualities.get(conv_id, ParseQuality.HIGH)
        if quality == ParseQuality.LOW or (
            prev == ParseQuality.HIGH and quality == ParseQuality.MEDIUM
        ):
            qualities[conv_id] = quality
        elif prev == ParseQuality.HIGH:
            qualities[conv_id] = quality

    bundles: list[ConversationBundle] = []
    for conv_id, messages in grouped.items():
        messages.sort(key=lambda m: m.time)
        if not messages:
            continue
        bundles.append(
            ConversationBundle(
                conversation_id=conv_id,
                messages=messages,
                source_ids=sorted(set(source_map.get(conv_id, []))),
                time_range=(messages[0].time, messages[-1].time),
                parse_quality=qualities.get(conv_id, ParseQuality.MEDIUM),
            )
        )
    bundles.sort(key=lambda b: b.time_range[0])
    return bundles
