import datetime as dt

from pydantic import BaseModel, ConfigDict


class TipOut(BaseModel):
    id: int
    vertical: str
    event_id: int
    entity_type: str
    entity_id: int
    entity_name: str | None
    entity_team: str | None
    market_type: str
    line: float | None
    recommended_side: str
    rationale_text: str | None
    confidence_score: float | None
    venue_name: str | None
    race_number: int | None
    start_time: dt.datetime | None
    stat_basis: dict | None
    generated_at: dt.datetime
    result_status: str = "pending"  # pending | won | lost — real outcome, once the race has run
    finish_position: int | None = None


class UserBetIn(BaseModel):
    tip_id: int | None = None
    stake: float
    odds_taken: float
    notes: str | None = None


class UserBetOut(BaseModel):
    id: int
    tip_id: int | None
    placed_at: dt.datetime
    stake: float
    odds_taken: float
    outcome: str
    settled_at: dt.datetime | None
    notes: str | None
    tip_label: str | None = None
    tip_vertical: str | None = None
    auto_settleable: bool = False


class UserBetSettle(BaseModel):
    outcome: str  # win | loss | void


class ChecklistItemIn(BaseModel):
    label: str
    sort_order: int = 0


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    sort_order: int


class SourceHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_name: str
    vertical: str
    status: str
    last_success_at: dt.datetime | None
    last_attempt_at: dt.datetime | None
    consecutive_failures: int


class RefreshRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: dt.datetime
    finished_at: dt.datetime | None
    status: str
    summary: dict | None


class RefreshTriggerOut(BaseModel):
    status: str  # started | already_running
    run_id: int


class TipsterSourceStats(BaseModel):
    source_name: str
    settled_wins: int
    settled_losses: int
    win_rate: float | None  # OUR verified rate from settled picks — never the tipster's own claim


class TipsterPickOut(BaseModel):
    id: int
    sport: str
    source_name: str
    published_at: dt.datetime
    raw_selection_text: str
    entity_name: str | None
    event_context: str | None  # e.g. "bet365 Hamilton · Race 2" or "Carlton vs Hawthorn"
    market_type: str | None
    line: float | None
    recommended_side: str | None
    outcome: str  # pending | win | loss | void | unresolved
    resolved_at: dt.datetime | None


class TipsterTipsOut(BaseModel):
    sources: list[TipsterSourceStats]
    picks: list[TipsterPickOut]
