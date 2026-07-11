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
    sources ("Geelong Cats" vs "Geelong", "GWS GIANTS" vs "GWS", "Adelaide Crows"
    vs "Adelaide") — used both to find a match's Event (find_event_for_teams) and
    to check who actually won against a tipster's recommended_side
    (tipster_settle.py's _resolve_football). A real bug (2026-07-11): the latter
    used exact equality for a while, silently misclassifying real wins as losses
    whenever the two sources' naming styles differed — always route both checks
    through this one function so a fix here can't be missed in the other."""
    x, y = x.strip().lower(), y.strip().lower()
    return x in y or y in x


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
        if (team_names_match(team_a, home) and team_names_match(team_b, away)) or (
            team_names_match(team_a, away) and team_names_match(team_b, home)
        ):
            return db.get(Event, mr.event_id)
    return None
