import json
from datetime import date, datetime, timezone
from unittest.mock import patch

from notes_interrogator.config import LlmConfig
from notes_interrogator.extract.cursor_agent import extract_tasks_cursor
from notes_interrogator.models import ActivityMessage, ConversationBundle, ParseQuality


def _bundle() -> ConversationBundle:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    return ConversationBundle(
        conversation_id="conv-1",
        messages=[
            ActivityMessage(
                role="user",
                text="I will send the deck by Friday.",
                time=now,
                source_id="msg-1",
            )
        ],
        source_ids=["msg-1"],
        time_range=(now, now),
        parse_quality=ParseQuality.HIGH,
    )


def test_extract_tasks_cursor_parses_agent_json(tmp_path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Extract tasks.", encoding="utf-8")
    cfg = LlmConfig(
        provider="cursor_agent",
        prompt_path=str(prompt),
        cursor_command=["/bin/echo"],
    )
    agent_out = {
        "type": "result",
        "is_error": False,
        "result": json.dumps(
            {
                "tasks": [
                    {
                        "title": "Send the deck",
                        "notes": "Due Friday",
                        "due": "2026-10-03",
                        "confidence": "high",
                        "source_ids": ["msg-1"],
                    }
                ]
            }
        ),
    }

    with patch(
        "notes_interrogator.extract.cursor_agent.subprocess.run",
    ) as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = json.dumps(agent_out)
        run_mock.return_value.stderr = ""
        tasks = extract_tasks_cursor([_bundle()], date(2026, 9, 30), cfg)

    assert len(tasks) == 1
    assert tasks[0].title == "Send the deck"
