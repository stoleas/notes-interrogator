from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from notes_interrogator.config import InputConfig
from notes_interrogator.models import (
    ActivityMessage,
    ConversationBundle,
    ParseQuality,
)


def _substitute(argv: list[str], mapping: dict[str, str]) -> list[str]:
    out: list[str] = []
    for part in argv:
        replaced = part
        for key, value in mapping.items():
            replaced = replaced.replace(key, value)
        out.append(replaced)
    return out


def _run_json_command(argv: list[str], env: dict[str, str]) -> object:
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(err)
    return json.loads(proc.stdout)


def _parse_internal_time(raw: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _message_body(payload: dict) -> str:
    body = payload.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    message = payload.get("message")
    if isinstance(message, dict):
        snippet = message.get("snippet")
        if isinstance(snippet, str) and snippet.strip():
            return snippet.strip()
    return ""


def load_bundles_from_mail(cfg: InputConfig) -> list[ConversationBundle]:
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    cutoff = now - timedelta(hours=cfg.lookback_hours)
    env = {**os.environ, **cfg.command_env}

    search_argv = _substitute(
        cfg.search_command,
        {"{query}": cfg.search_query},
    )
    search_hits = _run_json_command(search_argv, env)
    if not isinstance(search_hits, list):
        raise ValueError("mail search command must return a JSON array")

    bundles: list[ConversationBundle] = []
    for hit in search_hits:
        if not isinstance(hit, dict):
            continue
        message_id = hit.get("id")
        if not isinstance(message_id, str) or not message_id:
            continue
        internal = hit.get("internalDateIso") or hit.get("date")
        if isinstance(internal, str):
            try:
                when = _parse_internal_time(internal, tz)
            except ValueError:
                when = now
        else:
            when = now
        if when < cutoff:
            continue

        subject = hit.get("subject")
        subject_line = subject if isinstance(subject, str) else ""

        get_argv = _substitute(cfg.get_command, {"{message_id}": message_id})
        detail = _run_json_command(get_argv, env)
        if not isinstance(detail, dict):
            raise ValueError(f"mail get command must return JSON object for {message_id}")

        body = _message_body(detail)
        text = f"Subject: {subject_line}\n\n{body}".strip()
        if not text:
            continue

        bundles.append(
            ConversationBundle(
                conversation_id=message_id,
                messages=[
                    ActivityMessage(
                        role="assistant",
                        text=text,
                        time=when,
                        source_id=message_id,
                    )
                ],
                source_ids=[message_id],
                time_range=(when, when),
                parse_quality=ParseQuality.HIGH,
            )
        )

    bundles.sort(key=lambda b: b.time_range[0])
    return bundles
