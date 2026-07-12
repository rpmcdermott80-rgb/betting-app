export interface Tip {
  id: number;
  vertical: string;
  event_id: number;
  entity_type: string;
  entity_id: number;
  entity_name: string | null;
  entity_team: string | null;
  sport: string | null;
  market_type: string;
  line: number | null;
  recommended_side: string;
  rationale_text: string | null;
  confidence_score: number | null;
  venue_name: string | null;
  race_number: number | null;
  start_time: string | null;
  stat_basis: Record<string, unknown> | null;
  generated_at: string;
  result_status: "pending" | "won" | "lost";
  finish_position: number | null;
}

export interface UserBet {
  id: number;
  tip_id: number | null;
  placed_at: string;
  stake: number;
  odds_taken: number;
  outcome: "pending" | "win" | "loss" | "void";
  settled_at: string | null;
  notes: string | null;
  tip_label: string | null;
  tip_vertical: string | null;
  auto_settleable: boolean;
}

export interface ChecklistItem {
  id: number;
  label: string;
  sort_order: number;
}

export interface SourceHealth {
  source_name: string;
  vertical: string;
  status: "healthy" | "degraded" | "blocked" | "unknown";
  last_success_at: string | null;
  last_attempt_at: string | null;
  consecutive_failures: number;
}

export interface RefreshRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "failed";
  summary: Record<string, unknown> | null;
}

export interface RefreshTrigger {
  status: "started" | "already_running";
  run_id: number;
}

export interface TipsterSourceStats {
  source_name: string;
  settled_wins: number;
  settled_losses: number;
  win_rate: number | null;
}

export interface TipsterPick {
  id: number;
  sport: string;
  source_name: string;
  published_at: string;
  raw_selection_text: string;
  entity_name: string | null;
  event_context: string | null;
  market_type: string | null;
  line: number | null;
  recommended_side: string | null;
  outcome: "pending" | "win" | "loss" | "void" | "unresolved";
  resolved_at: string | null;
}

export interface TipsterTips {
  sources: TipsterSourceStats[];
  picks: TipsterPick[];
}
