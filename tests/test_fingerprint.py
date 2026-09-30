from datetime import date

from notes_interrogator.models import ExtractedTask, TaskConfidence
from notes_interrogator.state.store import ProcessedStore, task_fingerprint


def test_fingerprint_stable_for_same_inputs(tmp_path) -> None:
    task = ExtractedTask(
        title="Email the team",
        notes="from notes",
        confidence=TaskConfidence.HIGH,
        source_ids=["a", "b"],
    )
    fp1 = task_fingerprint(date(2026, 9, 30), task)
    fp2 = task_fingerprint(date(2026, 9, 30), task)
    assert fp1 == fp2


def test_processed_store_roundtrip(tmp_path) -> None:
    path = tmp_path / "processed.json"
    store = ProcessedStore(path)
    store.mark_processed("abc123")
    store.save()

    reloaded = ProcessedStore(path)
    assert reloaded.is_processed("abc123")
