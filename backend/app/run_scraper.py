"""Manual scraper runner, until Phase D adds scheduling/an API trigger.
Usage: python -m app.run_scraper <scraper_name> [--limit N]
"""

import argparse

from app.db import SessionLocal
from app.scrapers.afltables import AFLTablesScraper
from app.scrapers.betfair import BetfairGreyhoundScraper
from app.scrapers.racing_com import RacingComScraper
from app.scrapers.racing_queensland import RacingQueenslandScraper
from app.scrapers.rugbyleagueproject import RugbyLeagueProjectScraper
from app.scrapers.tipsters.alphr_football import AlphrAFLScraper, AlphrNRLScraper
from app.scrapers.tipsters.free_horse_racing_tips import FreeHorseRacingTipsScraper
from app.scrapers.tipsters.kruzey_afl import KruzeyAFLScraper
from app.scrapers.tipsters.kruzey_horse import KruzeyHorseScraper
from app.scrapers.tipsters.kruzey_nrl import KruzeyNRLScraper

SCRAPERS = {
    "afltables": AFLTablesScraper,
    "rlp": RugbyLeagueProjectScraper,
    "racing_com": RacingComScraper,
    "betfair": BetfairGreyhoundScraper,
    "racing_qld": RacingQueenslandScraper,
    "kruzey_horse": KruzeyHorseScraper,
    "kruzey_afl": KruzeyAFLScraper,
    "kruzey_nrl": KruzeyNRLScraper,
    "free_horse_tips": FreeHorseRacingTipsScraper,
    "alphr_afl": AlphrAFLScraper,
    "alphr_nrl": AlphrNRLScraper,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scraper", choices=SCRAPERS.keys())
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        scraper = SCRAPERS[args.scraper]()
        result = scraper.run(db, limit=args.limit)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
