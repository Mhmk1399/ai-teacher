"""Idempotent seeders — useful for first-run demos and for testing."""
from __future__ import annotations
import json
from pathlib import Path
from sqlalchemy.orm import Session

from core.config import settings
from core.models import Item


def load_sample_items(db: Session) -> int:
    """Load sample items from data/seeds/sample_items.json if present."""
    path: Path = settings.SEEDS_DIR / "sample_items.json"
    if not path.exists():
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    existing_codes = {row.code for row in db.query(Item).all() if row.code}
    added = 0
    for entry in data:
        code = entry.get("code")
        if code and code in existing_codes:
            continue
        item = Item(
            code=code,
            skill=entry["skill"],
            cefr_level=entry["cefr_level"],
            topic=entry["topic"],
            prompt=entry["prompt"],
            expected_patterns=entry.get("expected_patterns"),
            sample_response=entry.get("sample_response"),
            rubric=entry.get("rubric", {}),
            tags=entry.get("tags"),
            format=entry.get("format", "text"),
            created_by="seed",
        )
        db.add(item)
        added += 1
    db.commit()
    return added
