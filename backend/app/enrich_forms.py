"""Manual runner for the form enrichers. Usage: python -m app.enrich_forms [horse|greyhound|all]"""

import sys

from app.db import SessionLocal
from app.enrich import greyhound_form, horse_form


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    db = SessionLocal()
    try:
        if which in ("horse", "all"):
            print("horse form:", horse_form.run(db))
        if which in ("greyhound", "all"):
            print("greyhound form:", greyhound_form.run(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
