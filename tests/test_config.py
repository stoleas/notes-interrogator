import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from notes_interrogator.config import _load_env_file, load_config


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
source = "takeout"
activity_json = "${NOTES_INTERROGATOR_ACTIVITY_JSON}"
timezone = "UTC"

[llm]
provider = "http"
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


def test_env_file_sets_missing_vars(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    env_file = tmp_path / "env"
    env_file.write_text("LLM_BASE_URL=https://from-env.test\n", encoding="utf-8")
    _load_env_file(env_file)
    assert os.environ.get("LLM_BASE_URL") == "https://from-env.test"


def test_cursor_agent_provider_without_http_fields(tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[input]
source = "takeout"
activity_json = "/tmp/activity.json"
timezone = "UTC"

[llm]
provider = "cursor_agent"
prompt_path = "/tmp/prompt.md"
cursor_command = ["/usr/bin/agent", "--print"]

[tasks]
list_id = "list-1"
create_command = ["echo", "add"]

[state]
path = "/tmp/processed.json"
""",
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.llm.provider == "cursor_agent"


def test_env_file_does_not_override_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://existing.test")
    env_file = tmp_path / "env"
    env_file.write_text("LLM_BASE_URL=https://from-env.test\n", encoding="utf-8")
    _load_env_file(env_file)
    assert os.environ.get("LLM_BASE_URL") == "https://existing.test"


def test_missing_activity_json_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("NOTES_INTERROGATOR_ACTIVITY_JSON", raising=False)
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[input]
source = "takeout"
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
