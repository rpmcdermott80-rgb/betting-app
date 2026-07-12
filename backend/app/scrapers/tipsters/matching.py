"""Read-only entity/event matching for tipster picks. Deliberately never creates a
Horse/Greyhound/Player/Event — those tables are only ever populated by our own
primary-data scrapers. If a tipster's pick can't be confidently matched to something
we already know about, the pick is stored with entity_type/entity_id/event_id = null
and outcome = "unresolved" rather than guessing or fabricating a new record.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, EventParticipant, Greyhound, Horse, Venue

# Sponsor prefixes tipster sites often prepend to a venue name (e.g. "Ladbrokes
# Geelong") that our own Venue rows never carry.
_VENUE_PREFIXES = ("ladbrokes ", "tab ", "sportsbet ", "neds ")


def _normalize_venue(name: str) -> str:
    lowered = name.strip().lower()
    for prefix in _VENUE_PREFIXES:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :]
    return lowered.strip()


def find_venue(db: Session, name: str, vertical: str) -> Venue | None:
    target = _normalize_venue(name)
    candidates = list(db.scalars(select(Venue).where(Venue.vertical == vertical)))

    for venue in candidates:
        if _normalize_venue(venue.name) == target:
            return venue

    # Tipster sites often use a shorter/informal venue name than our own scrapers
    # store (e.g. "Randwick" vs "Royal Randwick", "Morphettville" vs "Morphettville
    # Parks") — fall back to a whole-word containment match. Real-world confirmed
    # 2026-07-11 against freehorseracingtipsaustralia.com.au.
    substring_matches = [
        venue
        for venue in candidates
        if target in _normalize_venue(venue.name) or _normalize_venue(venue.name) in target
    ]
    if len(substring_matches) == 1:
        return substring_matches[0]
    return None  # ambiguous (0 or 2+ matches) — don't guess


def find_event_for_race(
    db: Session, venue: Venue, sport: str, race_number: int, race_date: dt.date
) -> Event | None:
    return db.scalar(
        select(Event).where(
            Event.venue_id == venue.id,
            Event.sport == sport,
            Event.race_number == race_number,
            func.date(Event.start_time) == race_date,
        )
    )


def find_horse(db: Session, name: str) -> Horse | None:
    return db.scalar(select(Horse).where(func.lower(Horse.name) == name.strip().lower()))


def find_greyhound(db: Session, name: str) -> Greyhound | None:
    return db.scalar(select(Greyhound).where(func.lower(Greyhound.name) == name.strip().lower()))


def find_horse_by_barrier(db: Session, event: Event, barrier_or_number: int) -> Horse | None:
    """Some tipster sources (e.g. freehorseracingtipsaustralia.com.au) publish
    selections as runner/barrier numbers, not horse names — resolved against our
    own EventParticipant field for that race rather than name-matching."""
    participant = db.scalar(
        select(EventParticipant).where(
            EventParticipant.event_id == event.id,
            EventParticipant.entity_type == "horse",
            EventParticipant.barrier_or_number == barrier_or_number,
        )
    )
    if participant is None:
        return None
    return db.get(Horse, participant.entity_id)


def runner_is_in_race(db: Session, event: Event, entity_type: str, entity_id: int) -> bool:
    return (
        db.scalar(
            select(EventParticipant).where(
                EventParticipant.event_id == event.id,
                EventParticipant.entity_type == entity_type,
                EventParticipant.entity_id == entity_id,
            )
        )
        is not None
    )


# Common nicknames tipster prose uses instead of the official club name our own
# scrapers store on Player.team. Not exhaustive — anything not listed here just
# fails to resolve (pick stays "unresolved"), which is the safe default.
AFL_NICKNAMES = {
    "blues": "Carlton",
    "saints": "St Kilda",
    "dockers": "Fremantle",
    "swans": "Sydney",
    "eagles": "West Coast",
    "power": "Port Adelaide",
    "cats": "Geelong",
    "giants": "GWS",
    "hawks": "Hawthorn",
    "demons": "Melbourne",
    "tigers": "Richmond",
    "pies": "Collingwood",
    "magpies": "Collingwood",
    "bombers": "Essendon",
    "dons": "Essendon",
    "roos": "North Melbourne",
    "kangaroos": "North Melbourne",
    "bulldogs": "Western Bulldogs",
    "dogs": "Western Bulldogs",
    "crows": "Adelaide",
    "suns": "Gold Coast",
    "lions": "Brisbane Lions",
}

NRL_NICKNAMES = {
    "roosters": "Sydney Roosters",
    "rabbitohs": "South Sydney Rabbitohs",
    "souths": "South Sydney Rabbitohs",
    "storm": "Melbourne Storm",
    "broncos": "Brisbane Broncos",
    "panthers": "Penrith Panthers",
    "eels": "Parramatta Eels",
    "sharks": "Cronulla Sharks",
    "bulldogs": "Canterbury Bulldogs",
    "dragons": "St George Illawarra Dragons",
    "titans": "Gold Coast Titans",
    "cowboys": "North Queensland Cowboys",
    "knights": "Newcastle Knights",
    "raiders": "Canberra Raiders",
    "warriors": "New Zealand Warriors",
    "sea eagles": "Manly Sea Eagles",
    "manly": "Manly Sea Eagles",
    "tigers": "Wests Tigers",
    "dolphins": "Dolphins",
}


def resolve_team_name(raw: str, nickname_map: dict[str, str]) -> str:
    """A tipster's tipped-team mention might be the official name already (used
    directly in article titles) or a nickname (used in prose). Returns whichever
    matches; falls back to the raw text if neither resolves, and the caller is
    responsible for treating an unmatched name as unresolved."""
    key = raw.strip().lower()
    return nickname_map.get(key, raw.strip())


def team_names_match(x: str, y: str) -> bool:
    """Substring both ways since the same team gets styled differently across
    sources ("Geelong Cats" vs "Geelong", "Adelaide Crows" vs "Adelaide") — used
    both to find a match's Event (find_event_for_teams) and to check who actually
    won against a tipster's recommended_side (tipster_settle.py's
    _resolve_football). A real bug (2026-07-11): the latter used exact equality
    for a while, silently misclassifying real wins as losses whenever the two
    sources' naming styles differed — always route both checks through this one
    function so a fix here can't be missed in the other.

    Substring containment alone doesn't bridge every real naming gap though — an
    abbreviation like "GWS GIANTS" isn't a substring of the stored "Greater
    Western Sydney", and NRL's real club names have a middle-inserted regional
    qualifier a tipster's shorter form omits ("Cronulla Sharks" vs stored
    "Cronulla Sutherland Sharks", "Canterbury Bulldogs" vs "Canterbury Bankstown
    Bulldogs") — a missing middle word breaks substring matching even though it's
    unambiguously the same real club. See same_team() for the alias-aware check
    that's needed on top of this for those cases."""
    x, y = x.strip().lower(), y.strip().lower()
    return x in y or y in x


# rugbyleagueproject.org prepends a round-sponsor name to the HOME team specifically
# for themed rounds (e.g. "Magic Round Cronulla Sutherland Sharks") — a real NRL
# game, just needs this stripped before any team-name comparison. Deliberately a
# maintained allowlist rather than a generic "strip leading words" heuristic: an
# unrecognized prefix should fail to match rather than risk silently accepting
# something that isn't really a themed-round NRL game (e.g. "Betfred World Club
# Challenge Hull Kingston Rovers" and "Magic WKND Wigan Warriors" are real Super
# League fixtures our own scraper picked up alongside real NRL ones — see
# rugbyleagueproject.py's NRL_CLUBS allowlist for where those get rejected outright).
_NRL_ROUND_PREFIXES = (
    "anzac round ",
    "beanie for brain cancer round ",
    "magic round ",
    "multicultural round ",
)


def strip_nrl_round_prefix(name: str) -> str:
    lowered = name.strip().lower()
    for prefix in _NRL_ROUND_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix) :]
    return lowered


def _build_alias_map(variants_by_canonical: dict[str, list[str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for canonical, variants in variants_by_canonical.items():
        for v in variants:
            aliases[v] = canonical
    return aliases


# Canonical club identity -> every spelling/abbreviation this project has actually
# seen, from either our own scrapers' stored team names or a tipster site's prose.
# Kept separate per sport so short nicknames that collide across codes ("Tigers",
# "Bulldogs") never cross-match the wrong sport.
_AFL_CLUB_VARIANTS = {
    "adelaide": ["adelaide", "adelaide crows", "crows"],
    "brisbane lions": ["brisbane lions", "brisbane", "lions"],
    "carlton": ["carlton", "carlton blues"],
    "collingwood": ["collingwood", "collingwood magpies", "magpies", "pies"],
    "essendon": ["essendon", "essendon bombers", "bombers", "dons"],
    "fremantle": ["fremantle", "fremantle dockers", "dockers"],
    "geelong": ["geelong", "geelong cats"],
    "gold coast": ["gold coast", "gold coast suns"],
    "greater western sydney": ["greater western sydney", "gws", "gws giants"],
    "hawthorn": ["hawthorn", "hawthorn hawks"],
    "melbourne": ["melbourne", "melbourne demons", "demons"],
    "north melbourne": ["north melbourne", "north melbourne kangaroos", "kangaroos", "roos"],
    "port adelaide": ["port adelaide", "port adelaide power"],
    "richmond": ["richmond", "richmond tigers"],
    "st kilda": ["st kilda", "st kilda saints"],
    "sydney": ["sydney", "sydney swans", "swans"],
    "west coast": ["west coast", "west coast eagles"],
    "western bulldogs": ["western bulldogs", "bulldogs", "dogs"],
}
AFL_TEAM_ALIASES = _build_alias_map(_AFL_CLUB_VARIANTS)

# The 17 real 2026 NRL premiership clubs, keyed by the exact form our own scraper
# stores (after round-prefix stripping) — same list rugbyleagueproject.py's
# NRL_CLUBS allowlist uses to reject non-NRL matches at scrape time.
_NRL_CLUB_VARIANTS = {
    "brisbane broncos": ["brisbane broncos", "broncos"],
    "canberra raiders": ["canberra raiders", "raiders"],
    "canterbury bankstown bulldogs": ["canterbury bankstown bulldogs", "canterbury bulldogs", "bulldogs"],
    "cronulla sutherland sharks": ["cronulla sutherland sharks", "cronulla sharks", "sharks"],
    "dolphins": ["dolphins"],
    "gold coast titans": ["gold coast titans", "titans"],
    "manly warringah sea eagles": ["manly warringah sea eagles", "manly sea eagles", "manly", "sea eagles"],
    "melbourne storm": ["melbourne storm", "storm"],
    "newcastle knights": ["newcastle knights", "knights"],
    "north queensland cowboys": ["north queensland cowboys", "cowboys"],
    "parramatta eels": ["parramatta eels", "eels"],
    "penrith panthers": ["penrith panthers", "panthers"],
    "south sydney rabbitohs": ["south sydney rabbitohs", "rabbitohs", "souths"],
    "st george illawarra dragons": ["st george illawarra dragons", "st george dragons", "dragons"],
    "sydney roosters": ["sydney roosters", "roosters"],
    "warriors": ["warriors", "new zealand warriors"],
    "wests tigers": ["wests tigers", "tigers"],
}
NRL_TEAM_ALIASES = _build_alias_map(_NRL_CLUB_VARIANTS)

# The 17 real 2026 NRL premiership clubs, canonical form only — used by
# rugbyleagueproject.py to reject matches involving anything else (Queensland Cup
# feeder clubs, Super League clubs, State of Origin/All Stars representative
# sides, one-off exhibitions) that the scraper's discovery otherwise picks up
# alongside genuine NRL fixtures.
NRL_CLUBS = frozenset(_NRL_CLUB_VARIANTS.keys())


def same_team(x: str, y: str, sport: str) -> bool:
    """Alias-aware team match: strips NRL's round-sponsor prefixes, resolves both
    sides to a canonical club identity via the alias maps above, and compares
    those — catching abbreviation (GWS GIANTS vs Greater Western Sydney) and
    middle-inserted-qualifier (Cronulla Sharks vs Cronulla Sutherland Sharks)
    mismatches that plain substring containment can't bridge.

    Once EITHER side is a recognized club spelling, that alias resolution is
    trusted over a raw substring guess rather than falling back to it — a short
    nickname like "Warriors" (NZ Warriors) is a literal substring of an
    unrelated club's full name in another competition ("Wigan Warriors", Super
    League), so once one side is confidently identified, substring containment
    must not be allowed to override that. Only falls back to team_names_match
    when NEITHER side is recognized at all."""
    aliases = NRL_TEAM_ALIASES if sport == "nrl" else AFL_TEAM_ALIASES if sport == "afl" else {}
    x_norm = strip_nrl_round_prefix(x) if sport == "nrl" else x.strip().lower()
    y_norm = strip_nrl_round_prefix(y) if sport == "nrl" else y.strip().lower()
    x_canon = aliases.get(x_norm)
    y_canon = aliases.get(y_norm)
    if x_canon is not None or y_canon is not None:
        return x_canon is not None and y_canon is not None and x_canon == y_canon
    return team_names_match(x, y)


def find_event_for_teams(
    db: Session, sport: str, team_a: str, team_b: str, around: dt.date, window_days: int = 4
) -> Event | None:
    """Matches on team names appearing in the same MatchResult row (final score's
    home/away team strings, which come from the same boxscore pages our own
    scrapers already parsed) within a loose date window around the article date."""
    from app.models import MatchResult

    lo = around - dt.timedelta(days=window_days)
    hi = around + dt.timedelta(days=window_days)
    candidates = db.scalars(
        select(MatchResult)
        .join(Event, MatchResult.event_id == Event.id)
        .where(Event.sport == sport, func.date(Event.start_time) >= lo, func.date(Event.start_time) <= hi)
    )
    for mr in candidates:
        home, away = mr.home_team, mr.away_team
        # Checked in both team-order pairings since we don't know which of
        # team_a/team_b is home vs away.
        if (same_team(team_a, home, sport) and same_team(team_b, away, sport)) or (
            same_team(team_a, away, sport) and same_team(team_b, home, sport)
        ):
            return db.get(Event, mr.event_id)
    return None
