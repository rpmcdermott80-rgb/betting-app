"""Manual tip-generation runner. Usage: python -m app.generate_tips"""

from app.analysis import form_tips
from app.analysis.multis import generate_multis
from app.analysis.player_props import generate_tips as generate_player_prop_tips
from app.db import SessionLocal


def main():
    db = SessionLocal()
    try:
        print(f"player prop tips: {generate_player_prop_tips(db)}")
        print(f"form tips: {form_tips.generate_all(db)}")
        print(f"multis: {generate_multis(db)}")  # after props — multis are built from them
    finally:
        db.close()


if __name__ == "__main__":
    main()
