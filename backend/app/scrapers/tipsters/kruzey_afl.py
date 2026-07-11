import re

from app.scrapers.tipsters.kruzey_football import KruzeyFootballScraper
from app.scrapers.tipsters.matching import AFL_NICKNAMES


class KruzeyAFLScraper(KruzeyFootballScraper):
    source_name = "KRUZEY (AFL)"
    sport = "afl"
    hub_url = "https://www.kruzey.com.au/afl-tips/"
    link_re = re.compile(r'href="(https://www\.kruzey\.com\.au/afl-tips/[\w-]+-prediction-\d{2}-\d{2}-\d{2}/)"')
    slug_re = re.compile(r"/afl-tips/([\w]+(?:-[\w]+)*?)-vs-([\w]+(?:-[\w]+)*?)-prediction-(\d{2})-(\d{2})-(\d{2})/?$")
    nickname_map = AFL_NICKNAMES
