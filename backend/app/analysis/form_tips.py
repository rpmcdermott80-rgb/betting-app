"""Form-based ranking for racing (horses and greyhounds). For each upcoming (scheduled)
race, ranks the runners by a transparent form score from their real past starts (in
form_starts) plus recent trials, then tips the standout — with a rationale stating the
actual factual basis.

Honesty boundary: a heuristic ranking of real form, NOT a statistically validated
predictive model with a proven edge over the market. That needs a large historical
dataset + time-based backtest (Phase E, months away). The model description and each
rationale say so; confidence_score is a factual recent-placing rate, not a win
probability.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, EventParticipant, FormStart, Greyhound, Horse, ModelVersion, Tip


@dataclass(frozen=True)
class FormConfig:
    sport: str
    vertical: str
    entity_type: str  # horse | greyhound
    entity_model: type
    model_version_label: str
    trial_word: str  # "trial/jump-out" | "barrier trial"
    min_real_starts: int
    recent_window: int
    min_score_to_tip: float = 0.45
    min_field_scored: int = 4
    min_field_fraction: float = 0.5
    recency_decay: float = 0.85


HORSE = FormConfig(
    sport="horse_racing",
    vertical="horse_racing",
    entity_type="horse",
    entity_model=Horse,
    model_version_label="horse-form-ranking-v1",
    trial_word="trial/jump-out",
    min_real_starts=3,
    recent_window=6,
)

GREYHOUND = FormConfig(
    sport="greyhound",
    vertical="greyhound",
    entity_type="greyhound",
    entity_model=Greyhound,
    model_version_label="greyhound-form-ranking-v1",
    trial_word="barrier trial",
    min_real_starts=3,
    recent_window=5,
)


def _placing_value(finish: int | None) -> float:
    if finish is None:
        return 0.0
    return {1: 1.0, 2: 0.6, 3: 0.4}.get(finish, 0.15 if finish <= 6 else 0.0)


def _ordinal(n: int | None) -> str:
    if n is None:
        return "unplaced"
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _get_or_create_model_version(db: Session, cfg: FormConfig) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.version_label == cfg.model_version_label))
    if mv is None:
        mv = ModelVersion(
            vertical=cfg.vertical,
            version_label=cfg.model_version_label,
            description=(
                f"Ranks each scheduled {cfg.entity_type} race's runners by a recency-weighted "
                f"score of their real recent finishing positions (from form_starts), with a "
                f"small signal from recent {cfg.trial_word}s. Heuristic form analysis of real "
                f"past runs — NOT a backtested model proven to beat the market price."
            ),
        )
        db.add(mv)
        db.flush()
    return mv


def _score_runner(db: Session, cfg: FormConfig, entity_id: int) -> dict | None:
    starts = list(
        db.scalars(
            select(FormStart)
            .where(FormStart.entity_type == cfg.entity_type, FormStart.entity_id == entity_id)
            .order_by(FormStart.race_date.desc())
        )
    )
    real = [s for s in starts if not s.is_trial and not s.is_jumpout]
    trials = [s for s in starts if s.is_trial or s.is_jumpout]
    if len(real) < cfg.min_real_starts:
        return None

    recent = real[: cfg.recent_window]
    weights = [cfg.recency_decay**i for i in range(len(recent))]
    score = sum(w * _placing_value(s.finish_position) for w, s in zip(weights, recent)) / sum(weights)

    wins = sum(1 for s in recent if s.finish_position == 1)
    places = sum(1 for s in recent if s.finish_position and s.finish_position <= 3)

    trial_note = ""
    if trials and trials[0].finish_position and trials[0].finish_position <= 2:
        score += 0.05
        trial_note = f" Placed {_ordinal(trials[0].finish_position)} in a recent {cfg.trial_word}."

    return {
        "score": score,
        "wins": wins,
        "places": places,
        "n": len(recent),
        "most_recent_finish": recent[0].finish_position,
        "most_recent_venue": recent[0].venue,
        "most_recent_date": recent[0].race_date.date().isoformat(),
        "trial_note": trial_note,
        "place_rate": round(places / len(recent), 2),
    }


def generate_tips(db: Session, cfg: FormConfig) -> int:
    model_version = _get_or_create_model_version(db, cfg)
    tips_created = 0

    scheduled = list(db.scalars(select(Event).where(Event.sport == cfg.sport, Event.status == "scheduled")))

    for event in scheduled:
        participants = list(
            db.scalars(
                select(EventParticipant).where(
                    EventParticipant.event_id == event.id,
                    EventParticipant.entity_type == cfg.entity_type,
                    EventParticipant.scratched.is_(False),
                )
            )
        )

        ranked = []
        for p in participants:
            scored = _score_runner(db, cfg, p.entity_id)
            if scored is not None:
                ranked.append((p.entity_id, scored))

        if len(ranked) < cfg.min_field_scored or len(ranked) < cfg.min_field_fraction * len(participants):
            continue
        ranked.sort(key=lambda x: x[1]["score"], reverse=True)
        top_id, top = ranked[0]
        if top["score"] < cfg.min_score_to_tip:
            continue

        if db.scalar(
            select(Tip).where(
                Tip.event_id == event.id,
                Tip.entity_type == cfg.entity_type,
                Tip.entity_id == top_id,
                Tip.model_version_id == model_version.id,
            )
        ) is not None:
            continue

        entity = db.get(cfg.entity_model, top_id)
        venue_str = f" at {top['most_recent_venue']}" if top["most_recent_venue"] else ""
        rationale = (
            f"{entity.name}: {top['wins']} win(s) and {top['places']} placing(s) from last "
            f"{top['n']} starts (most recent: {_ordinal(top['most_recent_finish'])}{venue_str}, "
            f"{top['most_recent_date']}).{top['trial_note']} Top of {len(ranked)} ranked runners "
            f"on our form analysis. Heuristic ranking of real past runs — not a validated edge "
            f"over the market price."
        )

        db.add(
            Tip(
                vertical=cfg.vertical,
                event_id=event.id,
                entity_type=cfg.entity_type,
                entity_id=top_id,
                market_type="win",
                line=None,
                recommended_side="win",
                stat_basis=top,
                rationale_text=rationale,
                model_version_id=model_version.id,
                # The form score (0-1) is the ranking metric, so highest-first sorting
                # surfaces the strongest form. Shown as a "form rating %". The factual
                # place_rate stays in stat_basis. This is a form strength indicator,
                # not a win probability.
                confidence_score=round(min(top["score"], 1.0), 3),
            )
        )
        tips_created += 1

    db.commit()
    return tips_created


def generate_all(db: Session) -> dict:
    return {"horse": generate_tips(db, HORSE), "greyhound": generate_tips(db, GREYHOUND)}
