from datetime import date
from pathlib import Path

from notes_interrogator.ingest.takeout import load_bundles_for_date

FIXTURE = Path(__file__).parent / "fixtures" / "takeout" / "sample_activity.json"


def test_load_bundles_filters_by_date_and_groups_conversation() -> None:
    bundles = load_bundles_for_date(
        FIXTURE,
        date(2026, 9, 30),
        "UTC",
        r"/app/(?:c|chat)/([^/?#]+)",
    )
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.conversation_id == "conv-abc-123"
    assert len(bundle.messages) >= 3
    assert len(bundle.source_ids) == 2


def test_excludes_other_days() -> None:
    bundles = load_bundles_for_date(
        FIXTURE,
        date(2026, 9, 29),
        "UTC",
        r"/app/(?:c|chat)/([^/?#]+)",
    )
    assert len(bundles) == 1
    assert bundles[0].conversation_id == "conv-other-999"
