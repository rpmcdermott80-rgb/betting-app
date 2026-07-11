"""Manual bet-settlement runner. Usage: python -m app.settle_bets"""

from app.analysis.settle_bets import settle_pending_bets
from app.db import SessionLocal


def main():
    db = SessionLocal()
    try:
        print(f"settlement: {settle_pending_bets(db)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
