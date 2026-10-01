from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import tomllib
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.environ.get(name, "")

    return _ENV_PATTERN.sub(repl, value)


def _expand_value(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env(value)
    if isinstance(value, list):
        return [_expand_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_value(v) for k, v in value.items()}
    return value


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "notes-interrogator" / "config.toml"
    return Path.home() / ".config" / "notes-interrogator" / "config.toml"


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from path into os.environ (does not override existing)."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def _load_config_env(config_path: Path) -> None:
    _load_env_file(config_path.parent / "env")


class InputConfig(BaseModel):
    source: Literal["takeout", "mail"] = "mail"
    timezone: str = "UTC"
    activity_json: str = ""
    conversation_id_pattern: str = r"/app/(?:c|chat)/([^/?#]+)"
    lookback_hours: int = 24
    search_query: str = ""
    search_command: list[str] = Field(default_factory=list)
    get_command: list[str] = Field(default_factory=list)
    command_env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_fields(self) -> InputConfig:
        if self.source == "takeout":
            if not self.activity_json.strip():
                raise ValueError("input.activity_json is empty for takeout source")
        if self.source == "mail":
            if not self.search_query.strip():
                raise ValueError("input.search_query is empty for mail source")
            if not self.search_command:
                raise ValueError("input.search_command is required for mail source")
            if not self.get_command:
                raise ValueError("input.get_command is required for mail source")
            if "{query}" not in " ".join(self.search_command):
                raise ValueError("input.search_command must include {query}")
            if "{message_id}" not in " ".join(self.get_command):
                raise ValueError("input.get_command must include {message_id}")
        return self


class RunConfig(BaseModel):
    default_date: str = "today"


class LlmConfig(BaseModel):
    provider: Literal["http", "cursor_agent"] = "http"
    base_url: str = ""
    model: str = ""
    api_key_env: str = "LLM_API_KEY"
    prompt_path: str
    temperature: float = 0.2
    max_input_chars: int = 120_000
    cursor_command: list[str] = Field(default_factory=list)
    cursor_model: str = ""
    cursor_workspace: str = ""
    cursor_timeout_seconds: float = 900.0

    @model_validator(mode="after")
    def provider_fields(self) -> LlmConfig:
        if not self.prompt_path.strip():
            raise ValueError("llm.prompt_path must not be empty")
        if self.provider == "http":
            if not self.base_url.strip():
                raise ValueError("llm.base_url must not be empty")
            if not self.model.strip():
                raise ValueError("llm.model must not be empty")
            self.base_url = self.base_url.rstrip("/")
        elif self.provider == "cursor_agent":
            if not self.cursor_command:
                raise ValueError("llm.cursor_command is required for cursor_agent provider")
        return self


class TasksConfig(BaseModel):
    list_id: str
    create_command: list[str]
    create_command_env: dict[str, str] = Field(default_factory=dict)
    dry_run_env: str = "NOTES_INTERROGATOR_DRY_RUN"

    @field_validator("list_id")
    @classmethod
    def list_id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tasks.list_id is empty")
        return v

    @field_validator("create_command")
    @classmethod
    def create_command_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("tasks.create_command must not be empty")
        return v


class StateConfig(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def path_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("state.path is empty")
        return v


class AppConfig(BaseModel):
    input: InputConfig
    run: RunConfig = Field(default_factory=RunConfig)
    llm: LlmConfig
    tasks: TasksConfig
    state: StateConfig


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    _load_config_env(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config.example.toml and set env vars."
        )
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    expanded = _expand_value(raw)
    return AppConfig.model_validate(expanded)


def resolve_state_path(cfg: StateConfig) -> Path:
    return Path(cfg.path).expanduser()


def llm_api_key(cfg: LlmConfig) -> str:
    key = os.environ.get(cfg.api_key_env, "")
    if not key:
        raise ValueError(f"LLM API key env var {cfg.api_key_env} is not set")
    return key
