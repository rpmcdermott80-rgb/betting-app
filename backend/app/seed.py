"""Seeds the sources table (and a matching source_health row) from SOURCE_REGISTRY.
Idempotent — safe to run on every deploy. Run with: python -m app.seed
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Source, SourceHealth
from app.sources import SOURCE_REGISTRY


def run() -> None:
    db = SessionLocal()
    try:
        for entry in SOURCE_REGISTRY:
            existing = db.scalar(select(Source).where(Source.name == entry["name"]))
            if existing:
                for key, value in entry.items():
                    setattr(existing, key, value)
                continue
            source = Source(**entry)
            db.add(source)
            db.flush()  # get source.id before creating the health row
            db.add(SourceHealth(source_id=source.id, status="unknown"))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
