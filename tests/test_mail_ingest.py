import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from notes_interrogator.config import InputConfig
from notes_interrogator.ingest.mail import load_bundles_from_mail

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mail"


def _mail_config() -> InputConfig:
    return InputConfig(
        source="mail",
        timezone="America/New_York",
        lookback_hours=24,
        search_query="from:notes@example.test subject:Notes",
        search_command=["search-stub", "{query}"],
        get_command=["get-stub", "{message_id}"],
    )


def test_load_bundles_from_mail_filters_by_lookback() -> None:
    cfg = _mail_config()
    tz = ZoneInfo("America/New_York")
    search = [
        {
            "id": "msg-recent",
            "subject": "Notes: \"Team Sync\" Sep 30, 2026",
            "internalDateIso": (datetime.now(tz) - timedelta(hours=1)).isoformat(),
        },
        {
            "id": "msg-old",
            "subject": "Notes: \"Old\" Sep 20, 2026",
            "internalDateIso": (datetime.now(tz) - timedelta(hours=48)).isoformat(),
        },
    ]
    message = json.loads((FIXTURE_DIR / "message_detail.json").read_text())

    def fake_run(argv, env):  # type: ignore[no-untyped-def]
        if argv[0] == "search-stub":
            return search
        if argv[0] == "get-stub":
            return message
        raise AssertionError(argv)

    with patch("notes_interrogator.ingest.mail._run_json_command", side_effect=fake_run):
        bundles = load_bundles_from_mail(cfg)

    assert len(bundles) == 1
    assert bundles[0].conversation_id == "msg-recent"
    assert "Team Sync" in bundles[0].to_text()
