import re

from app.scrapers.tipsters.kruzey_football import KruzeyFootballScraper
from app.scrapers.tipsters.matching import NRL_NICKNAMES


class KruzeyNRLScraper(KruzeyFootballScraper):
    source_name = "KRUZEY (NRL)"
    sport = "nrl"
    hub_url = "https://www.kruzey.com.au/nrl-tips/"
    link_re = re.compile(r'href="(https://www\.kruzey\.com\.au/nrl-tips/[\w/-]+/)"')
    # Round-path segment (or a special-event path like state-of-origin) is optional
    # and skipped; pages without a "<a>-vs-<b>-prediction-dd-mm-yy" tail (e.g. a
    # State of Origin preview) simply don't match and are skipped, not an error.
    slug_re = re.compile(
        r"/nrl-tips/(?:[\w-]+/)?([\w]+(?:-[\w]+)*?)-vs-([\w]+(?:-[\w]+)*?)-prediction-(\d{2})-(\d{2})-(\d{2})/?$"
    )
    nickname_map = NRL_NICKNAMES
