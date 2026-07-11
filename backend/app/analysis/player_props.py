"""Player prop stat-threshold analysis — the v1 "our own modelling" approach the plan
validated as achievable now (unlike horse/greyhound win models, which need far more
historical depth before they're trustworthy). For each player/stat, find the highest
threshold that still clears a strong hit-rate over their recent games, and surface it
with the real numbers behind it — never a market-price claim, since we have no player
prop odds source (every AFL/NRL bookmaker checked had dedicated bot defense).

This is a snapshot of recent form, not a prediction for a specific upcoming game — we
don't have upcoming AFL/NRL fixtures wired up (afltables/rugbyleagueproject.org are
historical-results sources), so each tip is anchored to the player's most recent
logged game rather than a future one.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, ModelVersion, Player, PlayerGameLog, Tip

THRESHOLDS = {
    "disposals": [35, 32, 30, 28, 25, 22, 20, 18, 15],
    "goals": [4, 3, 2, 1],
    "tries": [3, 2, 1],
}
MIN_GAMES = 5
MAX_RECENT_GAMES = 20
MIN_HIT_RATE = 0.7
MODEL_VERSION_LABEL = "stat-threshold-v1"


def _get_or_create_model_version(db: Session) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.version_label == MODEL_VERSION_LABEL))
    if mv is None:
        mv = ModelVersion(
            vertical="player_prop",
            version_label=MODEL_VERSION_LABEL,
            description=(
                "Picks the highest stat threshold that still clears a "
                f"{MIN_HIT_RATE:.0%} hit-rate over a player's last up to "
                f"{MAX_RECENT_GAMES} logged games (min {MIN_GAMES} games required). "
                "Purely descriptive of real game logs — not compared against a "
                "market price, since no player prop odds source is available."
            ),
        )
        db.add(mv)
        db.flush()
    return mv


def generate_tips(db: Session) -> int:
    model_version = _get_or_create_model_version(db)
    tips_created = 0

    for player in db.query(Player).all():
        for stat_type, thresholds in THRESHOLDS.items():
            logs = (
                db.query(PlayerGameLog)
                .join(Event, PlayerGameLog.event_id == Event.id)
                .filter(PlayerGameLog.player_id == player.id, PlayerGameLog.stat_type == stat_type)
                .order_by(Event.start_time.desc())
                .limit(MAX_RECENT_GAMES)
                .all()
            )
            if len(logs) < MIN_GAMES:
                continue

            values = [float(log.stat_value) for log in logs]
            n = len(values)
            chosen = None
            for threshold in thresholds:
                hits = sum(1 for v in values if v >= threshold)
                rate = hits / n
                if rate >= MIN_HIT_RATE:
                    chosen = (threshold, hits, rate)
                    break
            if chosen is None:
                continue
            threshold, hits, rate = chosen

            most_recent_event_id = logs[0].event_id
            existing = (
                db.query(Tip)
                .filter(
                    Tip.entity_type == "player",
                    Tip.entity_id == player.id,
                    Tip.market_type == stat_type,
                    Tip.model_version_id == model_version.id,
                    Tip.event_id == most_recent_event_id,
                )
                .first()
            )
            if existing is not None:
                continue  # already generated for this snapshot

            event = db.get(Event, most_recent_event_id)
            rationale = (
                f"{player.name} has hit {threshold}+ {stat_type} in {hits} of their last {n} games "
                f"({rate:.0%}). Most recent logged game: {event.start_time.date()}. "
                "Recent-form snapshot, not tied to a specific upcoming fixture or market price."
            )

            db.add(
                Tip(
                    vertical="player_prop",
                    event_id=most_recent_event_id,
                    entity_type="player",
                    entity_id=player.id,
                    market_type=stat_type,
                    line=threshold,
                    recommended_side="over",
                    stat_basis={"hits": hits, "games": n, "hit_rate": rate, "recent_values": values},
                    rationale_text=rationale,
                    model_version_id=model_version.id,
                    confidence_score=rate,
                )
            )
            tips_created += 1

    db.commit()
    return tips_created
