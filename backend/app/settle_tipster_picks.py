"""Manual tipster-pick settlement runner. Usage: python -m app.settle_tipster_picks"""

from app.analysis.tipster_settle import settle_pending_picks
from app.db import SessionLocal


def main():
    db = SessionLocal()
    try:
        print(f"tipster settlement: {settle_pending_picks(db)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
