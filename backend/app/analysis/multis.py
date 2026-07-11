"""Sports multis built from the highest-hit-rate AFL/NRL player props. Picks the single
strongest prop from each of several different games (spreading legs across games keeps
same-game correlation out of it), combines the top few into a multi, and shows the legs
plus a rough combined estimate.

Honesty boundary: the combined number is the product of each leg's recent hit-rate — a
rough "all legs land" estimate that assumes independence and, crucially, is NOT a real
multi price, because we have no player-prop odds source (every AFL/NRL bookmaker checked
is behind commercial bot-defence). It's a strength indicator for stacking form, not a
priced bet. Multis are recomputed each run from the current props.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, ModelVersion, Player, Tip, UserBet

MODEL_VERSION_LABEL = "props-multi-v1"
MIN_LEG_HIT_RATE = 0.8
MULTI_SIZES = (4, 3)  # build a 4-leg and a 3-leg from the best available legs


def _get_or_create_model_version(db: Session) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.version_label == MODEL_VERSION_LABEL))
    if mv is None:
        mv = ModelVersion(
            vertical="multi",
            version_label=MODEL_VERSION_LABEL,
            description=(
                "Stacks the strongest player-prop legs (highest recent hit-rate, one per "
                "game to avoid same-game correlation) into a multi. Combined figure is the "
                "product of the legs' recent hit-rates — a rough 'all land' estimate, NOT a "
                "real multi price (no player-prop odds source available)."
            ),
        )
        db.add(mv)
        db.flush()
    return mv


def _leg_summary(db: Session, tip: Tip) -> dict:
    player = db.get(Player, tip.entity_id)
    line = f" {tip.line}" if tip.line is not None else ""
    return {
        "tip_id": tip.id,
        "player": player.name if player else "?",
        "team": getattr(player, "team", None),
        "market": f"{tip.market_type} {tip.recommended_side}{line}",
        "hit_rate": float(tip.confidence_score) if tip.confidence_score is not None else None,
        "event_id": tip.event_id,
    }


def generate_multis(db: Session) -> int:
    model_version = _get_or_create_model_version(db)

    # Multis are a derived aggregate — clear and rebuild from the current props.
    # Exclude any multi tip a user has already taken a bet on: user_bets.tip_id
    # has a real FK to tips.id, so deleting a referenced row would break this
    # rebuild (or the whole refresh job). Taken multis persist as a historical
    # record instead of being replaced every run.
    bet_tip_ids = select(UserBet.tip_id).where(UserBet.tip_id.isnot(None))
    db.query(Tip).filter(Tip.vertical == "multi", Tip.id.notin_(bet_tip_ids)).delete(
        synchronize_session=False
    )

    prop_tips = list(
        db.scalars(
            select(Tip)
            .where(Tip.vertical == "player_prop", Tip.confidence_score >= MIN_LEG_HIT_RATE)
            .order_by(Tip.confidence_score.desc())
        )
    )

    # One strongest leg per game, to keep legs from the same match out of one multi.
    best_per_game: dict[int, Tip] = {}
    for t in prop_tips:
        if t.event_id not in best_per_game:
            best_per_game[t.event_id] = t
    candidates = sorted(best_per_game.values(), key=lambda t: t.confidence_score, reverse=True)

    created = 0
    for size in MULTI_SIZES:
        if len(candidates) < size:
            continue
        legs = candidates[:size]
        combined = 1.0
        for t in legs:
            combined *= float(t.confidence_score)

        leg_summaries = [_leg_summary(db, t) for t in legs]
        leg_lines = "; ".join(
            f"{ls['player']}"
            + (f" ({ls['team']})" if ls["team"] else "")
            + f" {ls['market']} — {round(ls['hit_rate'] * 100)}%"
            for ls in leg_summaries
        )
        rationale = (
            f"{size}-leg multi from the strongest player props across {size} games: {leg_lines}. "
            f"Rough combined estimate ~{round(combined * 100)}% (product of recent hit-rates, "
            f"assumes independence — not a real multi price, no prop-odds source)."
        )

        db.add(
            Tip(
                vertical="multi",
                event_id=legs[0].event_id,
                entity_type="multi",
                entity_id=0,
                market_type="multi",
                line=None,
                recommended_side="multi",
                stat_basis={"legs": leg_summaries, "combined_estimate": round(combined, 4)},
                rationale_text=rationale,
                model_version_id=model_version.id,
                confidence_score=round(combined, 4),
            )
        )
        created += 1

    db.commit()
    return created
