from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from notes_interrogator.config import TasksConfig
from notes_interrogator.models import ExtractedTask


@dataclass
class TaskCreateOutcome:
    task: ExtractedTask
    ok: bool
    error: str | None = None


@dataclass
class SinkResult:
    outcomes: list[TaskCreateOutcome] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    @property
    def errors(self) -> list[str]:
        return [f"{o.task.title}: {o.error}" for o in self.outcomes if not o.ok and o.error]


def _substitute(argv: list[str], task: ExtractedTask, list_id: str) -> list[str]:
    due = task.due.isoformat() if task.due else ""
    mapping = {
        "{list_id}": list_id,
        "{title}": task.title,
        "{notes}": task.notes,
        "{due}": due,
    }
    out: list[str] = []
    for part in argv:
        replaced = part
        for key, value in mapping.items():
            replaced = replaced.replace(key, value)
        out.append(replaced)
    return out


def _dry_run_active(cfg: TasksConfig) -> bool:
    val = os.environ.get(cfg.dry_run_env, "")
    return val.strip().lower() in ("1", "true", "yes")


def create_tasks(
    tasks: list[ExtractedTask],
    cfg: TasksConfig,
    dry_run: bool = False,
) -> SinkResult:
    outcomes: list[TaskCreateOutcome] = []
    env = {**os.environ, **cfg.create_command_env}
    skip_exec = dry_run or _dry_run_active(cfg)

    for task in tasks:
        argv = _substitute(cfg.create_command, task, cfg.list_id)
        if skip_exec:
            print(f"[dry-run] would run: {argv}", flush=True)
            outcomes.append(TaskCreateOutcome(task=task, ok=True))
            continue
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
        except OSError as exc:
            outcomes.append(TaskCreateOutcome(task=task, ok=False, error=str(exc)))
            continue
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
            outcomes.append(TaskCreateOutcome(task=task, ok=False, error=err))
            continue
        outcomes.append(TaskCreateOutcome(task=task, ok=True))
    return SinkResult(outcomes=outcomes)
