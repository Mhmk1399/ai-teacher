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


def load_competency_catalog(db: Session, catalog: str = "grammar") -> int:
    """Load a competency catalog from data/competency_catalogs/<catalog>_seed.json.

    Idempotent: validates each entry with Pydantic, upserts by code, then wires
    prerequisites once all codes exist. Returns the number of competencies seen.
    Imports are local so the existing assessment app never hard-depends on the
    competency package at import time.
    """
    from core.competency.repository import (
        CatalogError, link_prerequisites, upsert_competency,
    )
    from core.competency.schemas import CompetencyDefinitionIn

    path: Path = settings.DATA_DIR / "competency_catalogs" / f"{catalog}_seed.json"
    if not path.exists():
        return 0

    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc.get("competencies", [])

    prereq_map: dict[str, list[str]] = {}
    for entry in entries:
        prereqs = entry.get("prerequisites", []) or []
        data = CompetencyDefinitionIn.model_validate(entry)
        upsert_competency(db, data, created_by="seed")
        if prereqs:
            prereq_map[data.code] = prereqs

    for code, prereqs in prereq_map.items():
        try:
            link_prerequisites(db, code, prereqs)
        except CatalogError:
            # A broken reference in seed data should be visible, not silent.
            raise

    return len(entries)
