# notes-interrogator

Harness-agnostic CLI that reads Google Takeout **My Activity → Gemini Apps** JSON for a single day, extracts accountability tasks with a configurable OpenAI-compatible LLM, and creates tasks via a user-defined command (for example a Google Tasks CLI).

## Requirements

- Python 3.11+
- Takeout export: **My Activity** → **Gemini Apps**, activity records in **JSON**
- LLM HTTP API compatible with `POST /v1/chat/completions` and `response_format: json_object`
- External task CLI invoked through `tasks.create_command` in config

## Install

```bash
cd /path/to/notes-interrogator
uv sync --extra dev
uv pip install -e .
```

## Configuration

1. Copy the example config:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/notes-interrogator/prompts"
cp config.example.toml "${XDG_CONFIG_HOME:-$HOME/.config}/notes-interrogator/config.toml"
cp prompts/extract-tasks.example.md "${XDG_CONFIG_HOME:-$HOME/.config}/notes-interrogator/prompts/extract-tasks.md"
```

2. Set environment variables referenced in config (no secrets in the repo):

| Variable | Purpose |
|----------|---------|
| `NOTES_INTERROGATOR_ACTIVITY_JSON` | Path to `MyActivity.json` from Takeout |
| `LLM_BASE_URL` | API base URL (no trailing path) |
| `LLM_MODEL` | Model id |
| `LLM_API_KEY` | API key (name overridable via `llm.api_key_env`) |
| `TASKS_LIST_ID` | Target task list id |
| `TASKS_CLI` | Executable for task creation (first element of `create_command`) |
| `XDG_CONFIG_HOME` / `XDG_DATA_HOME` | Optional; used in path expansion |

3. Adjust `tasks.create_command` to match your Tasks CLI. Placeholders: `{list_id}`, `{title}`, `{notes}`, `{due}`.

4. Validate:

```bash
notes-interrogator validate-config
```

## Takeout export (manual)

1. Open [Google Takeout](https://takeout.google.com).
2. Deselect all, then select **My Activity**.
3. Open **All activity data included** → deselect all → enable **Gemini Apps** only.
4. Use **Multiple formats** → set activity records to **JSON**.
5. Create export, download, extract archive.
6. Point `NOTES_INTERROGATOR_ACTIVITY_JSON` at the JSON file (often under `Takeout/My Activity/Gemini Apps/`).

## Usage

```bash
# Preview normalized conversation bundles for a day
notes-interrogator ingest-preview --date 2026-09-30

# Extract tasks without creating anything
notes-interrogator run --dry-run --date today

# Extract and create tasks (idempotent per day/title/source)
notes-interrogator run --date today

# Machine-readable stdout for cron/agents
notes-interrogator run --date today --json
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Partial sink failure (some tasks created) |
| 2 | Config, ingest, LLM, or total sink failure |

### Idempotency

Processed tasks are tracked in `state.path` (default under XDG data). Re-running the same day skips fingerprints already synced. This does not scan existing tasks in the remote list.

### Dry run for sink

- CLI: `notes-interrogator run --dry-run` skips the sink entirely.
- Env: set `NOTES_INTERROGATOR_DRY_RUN=1` (name configurable) to log intended `create_command` without executing.

## Cron example

```cron
15 18 * * * NOTES_INTERROGATOR_ACTIVITY_JSON=/data/takeout/MyActivity.json LLM_API_KEY=... TASKS_CLI=/usr/local/bin/your-tasks-cli notes-interrogator run --date today --json >> /var/log/notes-interrogator.jsonl 2>> /var/log/notes-interrogator.err
```

Prefer a secrets manager or env file sourced by cron instead of inline keys.

## Development

```bash
uv run pytest
```

## License

Use and modify as needed for your environment.
