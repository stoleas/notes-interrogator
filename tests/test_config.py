from pathlib import Path

import pytest
from pydantic import ValidationError

from notes_interrogator.config import load_config


def test_load_config_expands_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NOTES_INTERROGATOR_ACTIVITY_JSON", "/tmp/activity.json")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("TASKS_LIST_ID", "list-1")
    monkeypatch.setenv("TASKS_CLI", "/bin/echo")

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[input]
activity_json = "${NOTES_INTERROGATOR_ACTIVITY_JSON}"
timezone = "UTC"

[llm]
base_url = "${LLM_BASE_URL}"
model = "${LLM_MODEL}"
prompt_path = "/tmp/prompt.md"

[tasks]
list_id = "${TASKS_LIST_ID}"
create_command = ["${TASKS_CLI}", "tasks", "add", "{list_id}"]

[state]
path = "/tmp/processed.json"
""",
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.input.activity_json == "/tmp/activity.json"
    assert cfg.tasks.create_command[0] == "/bin/echo"


def test_missing_activity_json_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("NOTES_INTERROGATOR_ACTIVITY_JSON", raising=False)
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[input]
activity_json = "${NOTES_INTERROGATOR_ACTIVITY_JSON}"

[llm]
base_url = "https://api.example.test"
model = "m"
prompt_path = "/tmp/prompt.md"

[tasks]
list_id = "x"
create_command = ["echo"]

[state]
path = "/tmp/p.json"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(config_file)
