from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx

from notes_interrogator.config import LlmConfig, llm_api_key
from notes_interrogator.models import (
    ConversationBundle,
    ExtractedTask,
    ExtractionResult,
    TaskConfidence,
)


def _bundles_to_user_content(bundles: list[ConversationBundle], target: date) -> str:
    sections: list[str] = [f"Target date (local): {target.isoformat()}", ""]
    for bundle in bundles:
        sections.append(f"## Conversation {bundle.conversation_id}")
        sections.append(f"source_ids: {', '.join(bundle.source_ids)}")
        sections.append(bundle.to_text())
        sections.append("")
    return "\n".join(sections).strip()


def _truncate_bundles(
    bundles: list[ConversationBundle], max_chars: int
) -> list[ConversationBundle]:
    if max_chars <= 0:
        return bundles
    total = 0
    kept: list[ConversationBundle] = []
    for bundle in reversed(bundles):
        text_len = len(bundle.to_text())
        if kept and total + text_len > max_chars:
            continue
        if not kept and text_len > max_chars:
            trimmed = bundle.model_copy(deep=True)
            acc = 0
            new_messages = []
            for msg in reversed(trimmed.messages):
                if acc + len(msg.text) > max_chars:
                    break
                new_messages.insert(0, msg)
                acc += len(msg.text)
            trimmed.messages = new_messages
            kept.insert(0, trimmed)
            break
        kept.insert(0, bundle)
        total += text_len
    return kept or bundles[-1:]


def _parse_llm_json(content: str) -> dict:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def extract_tasks(
    bundles: list[ConversationBundle],
    target: date,
    cfg: LlmConfig,
    include_low_confidence: bool = False,
) -> list[ExtractedTask]:
    if not bundles:
        return []

    prompt_path = Path(cfg.prompt_path).expanduser()
    system_prompt = prompt_path.read_text(encoding="utf-8")
    selected = _truncate_bundles(bundles, cfg.max_input_chars)
    user_content = _bundles_to_user_content(selected, target)

    url = f"{cfg.base_url}/v1/chat/completions"
    payload = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {llm_api_key(cfg)}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    choices = body.get("choices") or []
    if not choices:
        raise ValueError("LLM response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("LLM response missing message content")

    parsed = _parse_llm_json(content)
    result = ExtractionResult.model_validate(parsed)
    tasks = result.tasks
    if not include_low_confidence:
        tasks = [t for t in tasks if t.confidence != TaskConfidence.LOW]
    return tasks
