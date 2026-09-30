from __future__ import annotations

from datetime import date

from notes_interrogator.config import InputConfig
from notes_interrogator.ingest.mail import load_bundles_from_mail
from notes_interrogator.ingest.takeout import load_bundles_for_date
from notes_interrogator.models import ConversationBundle


def load_bundles(cfg: InputConfig, target: date) -> list[ConversationBundle]:
    if cfg.source == "mail":
        return load_bundles_from_mail(cfg)
    return load_bundles_for_date(
        cfg.activity_json,
        target,
        cfg.timezone,
        cfg.conversation_id_pattern,
    )
