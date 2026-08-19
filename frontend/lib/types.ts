export type SignalLevel = "WATCH" | "EARLY" | "HIGH-CONVICTION" | "AVOID" | "EXIT_DANGER";
export type Confidence = "low" | "medium" | "high";
export type Chain = "solana" | "base" | "ethereum" | "bnb";

export interface UserOut {
  id: string;
  email: string;
  display_name: string;
  role: "member" | "admin";
  status: "active" | "disabled" | "deleted";
  created_at: string;
}

export interface TokenOut {
  id: string;
  chain: Chain;
  address: string;
  name: string | null;
  symbol: string | null;
  dex: string | null;
  first_seen_at: string;
}

export type DataStatus = "verified" | "cached" | "demo" | "unavailable" | "failed";

export interface TokenMetricOut {
  timestamp: string;
  price: number | null;
  market_cap: number | null;
  liquidity: number | null;
  volume: number | null;
  holder_count: number | null;
  data_status: DataStatus;
}

export interface SignalAlertOut {
  id: string;
  token_id: string;
  signal_type: SignalLevel;
  score: number;
  confidence: Confidence;
  payload_json: {
    reasons_summary?: string;
    risk_summary?: string;
    invalidation_summary?: string;
    data_source?: string;
    data_status?: DataStatus;
  };
  detected_at: string;
}

export interface InviteOut {
  id: string;
  recipient_label: string | null;
  recipient_email: string | null;
  max_uses: number;
  use_count: number;
  is_used: boolean;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface InviteCreateResponse {
  id: string;
  code: string;
  registration_url: string;
  max_uses: number;
  expires_at: string | null;
}

export interface PreferencesOut {
  alert_threshold: number;
  selected_chains: string[];
  watchlists: Record<string, unknown>;
  discord_preferences: Record<string, unknown>;
  updated_at: string;
}

export interface PaperTradeOut {
  id: string;
  token_id: string;
  status: "open" | "closed" | "expired";
  entry_price: number;
  entry_time: string;
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  realized_return_pct: number | null;
}

export interface DiscordIntegrationOut {
  id: string;
  name: string;
  channel_label: string | null;
  enabled: boolean;
  minimum_score: number;
  allowed_chains: string[];
  alert_types: string[];
}

// The seven Discord alert types (app/core/discord_alert_types.py) - a
// different dimension from a signal's classification (WATCH/EARLY/etc):
// this describes what *kind* of Discord message it is, several of which
// (SECURITY_RISK, SCANNER_FAILURE) aren't tied to a scored signal at all.
export type DiscordAlertType =
  | "SIGNAL_DETECTED"
  | "SECURITY_RISK"
  | "LIQUIDITY_WARNING"
  | "DEPLOYER_SELLING"
  | "MOMENTUM_FAILURE"
  | "MOMENTUM_RECOVERY"
  | "SCANNER_FAILURE";

export interface DiscordAlertConfigOut {
  all_signals_enabled: boolean;
  min_score: number;
  cooldown_minutes: number;
  all_alert_types: DiscordAlertType[];
  implemented_alert_types: DiscordAlertType[];
}

export type DataQuality = "VERIFIED" | "DEMO" | "ESTIMATED" | "UNAVAILABLE";

export interface ProviderStatus {
  name: string;
  enabled: boolean;
  mode: "live" | "mock" | "disabled";
}

export interface DataSourceStatusOut {
  provider_mode: string;
  cache_ttl_seconds: number;
  request_timeout_seconds: number;
  max_retries: number;
  providers: ProviderStatus[];
}

export interface ValidationErrorOut {
  row: number;
  field: string;
  message: string;
}

export interface ValidationReportOut {
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  duplicate_rows: number;
  errors: ValidationErrorOut[];
  warnings: ValidationErrorOut[];
}

export interface DatasetOut {
  id: string;
  name: string;
  data_quality: DataQuality;
  status: string;
  row_count: number;
  valid_row_count: number;
  error_row_count: number;
  duplicate_row_count: number;
  created_at: string;
  imported_at: string | null;
}

export interface DatasetQualityOut {
  dataset_id: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  missing_field_counts: Record<string, number>;
  suspicious_value_count: number;
  verified_rows: number;
  demo_rows: number;
  estimated_rows: number;
  unavailable_rows: number;
  earliest_snapshot: string | null;
  latest_snapshot: string | null;
  distinct_tokens: number;
  outcome_distribution: Record<string, number>;
  sources: string[];
  data_freshness_hours: number | null;
  validation_status: "clean" | "has_errors" | "has_warnings_only";
}

export interface CaseResultOut {
  label: string;
  outcome: string;
  would_have_alerted: boolean;
  earliest_alert_minutes_before_move: number | null;
}

export interface BacktestResultOut {
  summary: {
    total_cases: number;
    total_runners: number;
    total_non_runners: number;
    model: { recall: number | null; false_positive_count: number };
    baseline: { recall: number | null; false_positive_count: number };
  };
  cases: CaseResultOut[];
}
