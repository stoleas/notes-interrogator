from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from notes_interrogator.config import AppConfig, default_config_path, load_config, resolve_state_path
from notes_interrogator.extract.llm import extract_tasks
from notes_interrogator.ingest.loader import load_bundles
from notes_interrogator.models import RunReport
from notes_interrogator.sink.exec import create_tasks
from notes_interrogator.state.store import ProcessedStore, task_fingerprint


def _parse_target_date(value: str, tz_name: str) -> date:
    if value == "today":
        return datetime.now(ZoneInfo(tz_name)).date()
    return date.fromisoformat(value)


def _resolve_config(path: str | None) -> AppConfig:
    config_path = Path(path) if path else None
    return load_config(config_path)


def _emit_json(data: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(data, indent=2), flush=True)


def cmd_validate_config(args: argparse.Namespace) -> int:
    try:
        cfg = _resolve_config(args.config)
    except (FileNotFoundError, ValidationError, ValueError) as exc:
        print(f"Config invalid: {exc}", file=sys.stderr)
        return 2
    _emit_json({"ok": True, "config": cfg.model_dump()}, args.json)
    if not args.json:
        print("Configuration is valid.", file=sys.stderr)
    return 0


def cmd_ingest_preview(args: argparse.Namespace) -> int:
    try:
        cfg = _resolve_config(args.config)
        target = _parse_target_date(args.date or cfg.run.default_date, cfg.input.timezone)
        bundles = load_bundles(cfg.input, target)
    except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
        print(f"ingest-preview failed: {exc}", file=sys.stderr)
        return 2

    payload = {
        "date": target.isoformat(),
        "source": cfg.input.source,
        "lookback_hours": cfg.input.lookback_hours if cfg.input.source == "mail" else None,
        "bundles": len(bundles),
        "conversations": [
            {
                "conversation_id": b.conversation_id,
                "source_ids": b.source_ids,
                "parse_quality": b.parse_quality.value,
                "message_count": len(b.messages),
                "text": b.to_text(),
            }
            for b in bundles
        ],
    }
    _emit_json(payload, args.json)
    if not args.json:
        print(json.dumps(payload, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        cfg = _resolve_config(args.config)
        target = _parse_target_date(args.date or cfg.run.default_date, cfg.input.timezone)
        bundles = load_bundles(cfg.input, target)
        tasks = extract_tasks(
            bundles,
            target,
            cfg.llm,
            include_low_confidence=args.include_low_confidence,
        )
    except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 2

    report = RunReport(
        date=target.isoformat(),
        bundles=len(bundles),
        extracted=len(tasks),
        tasks=tasks if args.dry_run or args.json else None,
    )

    if args.dry_run:
        _emit_json(report.to_json_dict(include_tasks=True), args.json)
        if not args.json:
            print(json.dumps(report.to_json_dict(include_tasks=True), indent=2))
        return 0

    store = ProcessedStore(resolve_state_path(cfg.state))
    pending: list = []
    skipped = 0
    for task in tasks:
        fp = task_fingerprint(target, task)
        if store.is_processed(fp):
            skipped += 1
            continue
        pending.append((fp, task))

    sink_result = create_tasks([t for _, t in pending], cfg.tasks, dry_run=False)
    created = 0
    errors = list(sink_result.errors)
    for (fp, task), outcome in zip(pending, sink_result.outcomes):
        if outcome.ok:
            store.mark_processed(fp)
            created += 1
    store.save()

    report.created = created
    report.skipped = skipped
    report.errors = errors

    _emit_json(report.to_json_dict(include_tasks=False), args.json)
    if not args.json:
        print(json.dumps(report.to_json_dict(include_tasks=False), indent=2))

    if errors and created > 0:
        return 1
    if errors and created == 0:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notes-interrogator")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help=f"Config path (default: {default_config_path()})")
    common.add_argument("--json", action="store_true", help="Emit JSON on stdout")

    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate-config", parents=[common], help="Validate configuration"
    )
    validate.set_defaults(func=cmd_validate_config)

    preview = sub.add_parser(
        "ingest-preview", parents=[common], help="Show conversation bundles for a date"
    )
    preview.add_argument("--date", help="YYYY-MM-DD or today")
    preview.set_defaults(func=cmd_ingest_preview)

    run = sub.add_parser("run", parents=[common], help="Extract tasks and sync to configured sink")
    run.add_argument("--date", help="YYYY-MM-DD or today")
    run.add_argument("--dry-run", action="store_true", help="Extract only; do not create tasks")
    run.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include low-confidence extracted tasks",
    )
    run.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
