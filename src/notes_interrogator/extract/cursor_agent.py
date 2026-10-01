from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from notes_interrogator.config import LlmConfig
from notes_interrogator.extract.llm import _bundles_to_user_content, _parse_llm_json, _truncate_bundles
from notes_interrogator.models import (
    ConversationBundle,
    ExtractedTask,
    ExtractionResult,
    TaskConfidence,
)


def _run_agent(prompt: str, cfg: LlmConfig) -> str:
    if not cfg.cursor_command:
        raise ValueError("llm.cursor_command is empty")
    cmd: list[str] = list(cfg.cursor_command)
    if cfg.cursor_model.strip():
        cmd.extend(["--model", cfg.cursor_model.strip()])
    cmd.append(prompt)

    cwd = cfg.cursor_workspace.strip() or None
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.cursor_timeout_seconds,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"Cursor agent timed out after {cfg.cursor_timeout_seconds}s"
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"Cursor agent exited {completed.returncode}"
            + (f": {detail[:500]}" if detail else "")
        )

    stdout = completed.stdout.strip()
    if not stdout:
        raise ValueError("Cursor agent produced empty stdout")

    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Cursor agent stdout is not JSON") from exc

    if envelope.get("is_error"):
        raise RuntimeError(f"Cursor agent error: {envelope.get('result') or envelope}")

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise ValueError("Cursor agent JSON missing result text")
    return result


def extract_tasks_cursor(
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
    prompt = f"{system_prompt}\n\n---\n\n{user_content}"

    content = _run_agent(prompt, cfg)
    parsed = _parse_llm_json(content)
    result = ExtractionResult.model_validate(parsed)
    tasks = result.tasks
    if not include_low_confidence:
        tasks = [t for t in tasks if t.confidence != TaskConfidence.LOW]
    return tasks
