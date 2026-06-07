/**
 * Typed API client for the Bridge OS backend.
 *
 * Schemas mirror the Pydantic models in `backend/app/schemas/`. Keep them in sync.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

// --- Enums ------------------------------------------------------------------

export type BloodGroup =
  | "O+" | "O-" | "A+" | "A-" | "B+" | "B-" | "AB+" | "AB-"
  // Bombay (hh) and unknown — the dataset has 2 Bombay donors and ~2k
  // "unknown" donors (the Blood Warriors "Do not Know" guest-pool rows),
  // so the UI filters need to be able to select them.
  | "Bombay"
  | "unknown";

export type Language =
  | "en"
  | "hi"
  | "te"
  | "ta"
  | "mr"
  | "bn"
  | "kn"
  | "gu";

export type BridgeStatus = "active" | "paused" | "archived";
export type BridgeHealth = "stable" | "at_risk" | "critical";
export type MembershipStatus = "active" | "paused" | "exited";
export type MembershipRole = "primary" | "backup";

// --- Models -----------------------------------------------------------------

export interface DonorSummary {
  id: string;
  external_handle?: string | null;
  name: string;
  age: number;
  blood_group: BloodGroup;
  rh_negative: boolean;
  kell_negative: boolean;
  city: string;
  state: string;
  last_donation_date: string | null;
  total_donations: number;
  response_rate: number;
  is_active: boolean;
}

export interface PatientDetail {
  id: string;
  external_handle?: string | null;
  name: string;
  age: number;
  blood_group: BloodGroup;
  rh_negative: boolean;
  kell_negative: boolean;
  extended_phenotype: string | null;
  city: string;
  state: string;
  hospital: string;
  transfusion_cadence_days: number;
  last_transfusion_date: string | null;
  preferred_language: Language;
  active: boolean;
}

export interface MembershipDetail {
  id: string;
  role: MembershipRole;
  status: MembershipStatus;
  joined_at: string;
  notes: string | null;
  donor: DonorSummary;
}

export interface BridgeListItem {
  id: string;
  patient_id: string;
  patient_name: string;
  patient_age: number;
  blood_group: BloodGroup;
  city: string;
  state: string;
  hospital: string;
  status: BridgeStatus;

  active_donor_count: number;
  total_donor_count: number;
  health: BridgeHealth;

  last_transfusion_date: string | null;
  next_transfusion_date: string | null;
  days_until_transfusion: number | null;

  created_at: string;
}

export interface BridgeDetail extends BridgeListItem {
  name: string;
  patient: PatientDetail;
  members: MembershipDetail[];
}

export interface BridgesPage {
  items: BridgeListItem[];
  total: number;
  skip: number;
  limit: number;
}

// --- Donor list / detail (Phase 2) ------------------------------------------

export interface DonorListItem {
  id: string;
  external_handle?: string | null;
  name: string;
  age: number;
  blood_group: BloodGroup;
  rh_negative: boolean;
  kell_negative: boolean;
  city: string;
  state: string;
  preferred_language: Language;

  last_donation_date: string | null;
  days_since_donation: number | null;
  total_donations: number;
  response_rate: number;
  avg_response_hours: number;

  is_active: boolean;
  is_eligible_to_donate: boolean;
  bridge_count: number;
}

export interface DonorBridgeMembershipRef {
  membership_id: string;
  bridge_id: string;
  bridge_name: string;
  bridge_status: BridgeStatus;
  patient_id: string;
  patient_name: string;
  patient_age: number;
  patient_blood_group: BloodGroup;
  role: MembershipRole;
  status: MembershipStatus;
  joined_at: string;
}

export interface DonorDetail extends DonorListItem {
  phone: string;
  lat: number;
  lng: number;
  extended_phenotype: string | null;
  registered_at: string;
  memberships: DonorBridgeMembershipRef[];
}

export interface DonorsPage {
  items: DonorListItem[];
  total: number;
  skip: number;
  limit: number;
}

export type DonorSort =
  | "name"
  | "last_donation"
  | "response_rate"
  | "total_donations"
  | "age";

export interface DonorFilters {
  skip?: number;
  limit?: number;
  search?: string;
  blood_group?: BloodGroup;
  city?: string;
  is_active?: boolean;
  kell_negative?: boolean;
  sort?: DonorSort;
  order?: "asc" | "desc";
}

// --- Patient list / profile (Phase 3) ---------------------------------------

export interface PatientListItem {
  id: string;
  external_handle?: string | null;
  name: string;
  age: number;
  blood_group: BloodGroup;
  rh_negative: boolean;
  kell_negative: boolean;
  city: string;
  state: string;
  hospital: string;
  preferred_language: Language;

  transfusion_cadence_days: number;
  last_transfusion_date: string | null;
  next_transfusion_date: string | null;
  days_until_transfusion: number | null;

  active: boolean;
  has_bridge: boolean;
  bridge_health: BridgeHealth | null;
  active_donor_count: number;
}

export interface PatientBridgeRef {
  bridge_id: string;
  bridge_name: string;
  bridge_status: BridgeStatus;
  active_donor_count: number;
  total_donor_count: number;
  health: BridgeHealth;
  created_at: string;
}

export interface PatientProfile extends PatientListItem {
  extended_phenotype: string | null;
  lat: number;
  lng: number;
  registered_at: string;
  bridge: PatientBridgeRef | null;
  projected_transfusions: string[];
  /** G5: caregiver (parent/guardian/self) who receives patient-side WhatsApp updates. */
  caregiver_name?: string | null;
  caregiver_phone?: string | null;
  caregiver_relation?: "mother" | "father" | "guardian" | "self" | "spouse" | "sibling" | null;
}

export interface PatientsPage {
  items: PatientListItem[];
  total: number;
  skip: number;
  limit: number;
}

export type PatientSort = "name" | "age" | "last_transfusion";

export interface PatientFilters {
  skip?: number;
  limit?: number;
  search?: string;
  blood_group?: BloodGroup;
  city?: string;
  active?: boolean;
  has_bridge?: boolean;
  bridge_health?: BridgeHealth;
  sort?: PatientSort;
  order?: "asc" | "desc";
}

// --- Stability (Phase 4) ----------------------------------------------------

export type StabilityDirection = "increases_churn" | "decreases_churn";

export interface StabilityFactor {
  feature: string;
  label: string;
  direction: StabilityDirection;
  impact: number;
}

export interface DonorStability {
  donor_id: string;
  donor_name: string;
  churn_30d: number;
  churn_60d: number;
  churn_90d: number;
  top_factors: StabilityFactor[];
}

export interface BridgeStabilityAggregate {
  ml_health: BridgeHealth;
  avg_churn_90d: number;
  max_churn_90d: number;
  at_risk_donor_count: number;
  active_donor_count: number;
}

export interface BridgeStability {
  bridge_id: string;
  bridge_name: string;
  computed_at: string;
  model_version: string;
  aggregate: BridgeStabilityAggregate;
  members: DonorStability[];
}

// --- Schedule (Phase 5) -----------------------------------------------------

export type SolverStatus = "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "EMPTY";

export interface ScheduleSlot {
  sequence: number;
  transfusion_date: string;
  donor_id: string;
  donor_name: string;
  donor_blood_group: string;
}

export interface DonorLoad {
  donor_id: string;
  donor_name: string;
  assignment_count: number;
}

export interface BridgeSchedule {
  bridge_id: string;
  bridge_name: string;
  horizon_days: number;
  transfusion_cadence_days: number;
  solved_at: string;
  solve_time_ms: number;
  solver_status: SolverStatus;
  objective_value: number;
  message: string;
  slots: ScheduleSlot[];
  donor_load: DonorLoad[];
}

// --- Recommendations + Recruit (Phase 6) ------------------------------------

export type Urgency = "critical" | "high" | "medium";

export interface CandidateRationale {
  factor: string;
  value: number;
  description: string;
}

export interface RecruitmentCandidate {
  donor: DonorSummary;
  composite_score: number;
  distance_km: number;
  predicted_churn_90d: number;
  days_until_eligible: number;
  rationale: CandidateRationale[];
}

export interface WeakDonor {
  membership_id: string;
  donor_id: string;
  donor_name: string;
  role: string;
  churn_90d: number;
  top_factors: StabilityFactor[];
}

export interface BridgeRecommendation {
  bridge_id: string;
  bridge_name: string;
  patient_id: string;
  patient_name: string;
  patient_age: number;
  patient_blood_group: BloodGroup;
  patient_hospital: string;
  patient_city: string;
  bridge_health_stub: BridgeHealth;
  active_donor_count: number;
  urgency: Urgency;
  weak_donors: WeakDonor[];
  candidates: RecruitmentCandidate[];
}

export interface RecommendationsInbox {
  items: BridgeRecommendation[];
  total: number;
}

export interface RecruitRequest {
  candidate_donor_id: string;
  replace_donor_id?: string | null;
  language?:
    | "en"
    | "hi"
    | "te"
    | "ta"
    | "mr"
    | "bn"
    | "kn"
    | "gu"
    | null;
  notes?: string | null;
}

export interface RecruitResponse {
  bridge_id: string;
  added_membership_id: string;
  added_donor_id: string;
  added_donor_name: string;
  /** G1: recruits start "pending" — donor must reply YES on WhatsApp to flip to active. */
  status: "pending" | "active";
  waiting_for_donor_reply: boolean;
  message_sid: string | null;
  message_language:
    | "en"
    | "hi"
    | "te"
    | "ta"
    | "mr"
    | "bn"
    | "kn"
    | "gu"
    | null;
  replace_donor_id: string | null;
  new_active_donor_count: number;
  message: string;
}

export interface PendingRecruit {
  membership_id: string;
  bridge_id: string;
  candidate_donor_id: string;
  candidate_donor_name: string;
  candidate_donor_phone: string;
  candidate_donor_language: string;
  replaces_donor_id: string | null;
  replaces_donor_name: string | null;
  invite_message_sid: string | null;
  invite_language: string | null;
  joined_at: string;
}

export interface PendingAction {
  kind: "recruit";
  membership_id: string;
  bridge_id: string;
  bridge_name: string;
  patient_name: string;
  replaces_donor_name: string | null;
  invite_sent_at: string | null;
}

// --- Response feedback (G2) -------------------------------------------------

export type ResponseEventKind = "reply" | "no_reply";

export interface ResponseEvent {
  kind: ResponseEventKind;
  prior_response_rate: number;
  new_response_rate: number;
  prior_avg_hours: number | null;
  new_avg_hours: number | null;
  hours_to_response: number | null;
  at: string | null;
}

export interface ResponseHistory {
  donor_id: string;
  donor_name: string;
  current_response_rate: number;
  current_avg_response_hours: number;
  events: ResponseEvent[];
  days: number;
}

// --- Schedule history (G3) --------------------------------------------------

export interface ScheduleResolveEvent {
  id: string;
  before_status: string | null;
  after_status: string;
  before_objective: number | null;
  after_objective: number | null;
  before_slot_count: number | null;
  after_slot_count: number | null;
  triggered_by: string;
  solve_time_ms: number | null;
  notes: string | null;
  at: string | null;
}

export interface ScheduleHistory {
  bridge_id: string;
  events: ScheduleResolveEvent[];
}

// --- Swap state machine (G6) ------------------------------------------------

export type SwapStatus =
  | "proposed"
  | "accepted"
  | "rejected"
  | "expired"
  | "cancelled";

export interface SwapRequest {
  id: string;
  from_donor_id: string;
  from_donor_name: string;
  to_donor_id: string;
  to_donor_name: string;
  from_slot_date: string;
  to_slot_date: string;
  status: SwapStatus;
  expires_at: string | null;
  created_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
}

export interface SwapRequestsList {
  bridge_id: string;
  swaps: SwapRequest[];
}

// --- Analytics (Phase 7) ----------------------------------------------------

export interface HealthCounts {
  stable: number;
  at_risk: number;
  critical: number;
}

export interface BloodGroupBreakdown {
  blood_group: BloodGroup;
  count: number;
}

export interface CityBreakdown {
  city: string;
  state: string;
  count: number;
}

export interface DonorPoolStats {
  total: number;
  active: number;
  eligible_now: number;
  kell_negative: number;
  by_blood_group: BloodGroupBreakdown[];
}

export interface CohortStatsOut {
  total_bridges: number;
  avg_active_donors: number;
  avg_cohort_size: number;
  total_active_memberships: number;
  stub_health: HealthCounts;
  ml_health: HealthCounts;
}

export interface StabilityModelMetrics {
  trained_at: string;
  n_samples: number;
  seed: number;
  auc_30d: number;
  auc_60d: number;
  auc_90d: number;
  train_auc_30d: number;
  train_auc_60d: number;
  train_auc_90d: number;
  brier_90d: number;
}

export interface AnalyticsResponse {
  generated_at: string;
  total_patients: number;
  total_donors: number;
  donor_pool: DonorPoolStats;
  cohort_stats: CohortStatsOut;
  patients_by_city: CityBreakdown[];
  stability_model: StabilityModelMetrics | null;
  stability_compute_time_ms: number;
}

// --- Integrations (Phase 8) -------------------------------------------------

export type IntegrationStatusValue =
  | "mocked"
  | "connected"
  | "not_configured"
  | "error";

export interface IntegrationStatus {
  key: string;
  name: string;
  description: string;
  status: IntegrationStatusValue;
  last_sync: string | null;
  sample_count: number | null;
  docs_url: string | null;
  phase: string;
}

export interface IntegrationsStatusList {
  items: IntegrationStatus[];
  generated_at: string;
}

export interface BloodBankStock {
  name: string;
  city: string;
  state: string;
  lat: number;
  lng: number;
  phone: string;
  inventory: Record<string, number>;
  last_updated: string;
}

export interface ERaktKoshInventoryResponse {
  source: string;
  status: IntegrationStatusValue;
  fetched_at: string;
  city_filter: string | null;
  blood_group_filter: string | null;
  blood_banks: BloodBankStock[];
}

export interface RegisteredRareDonor {
  registry_id: string;
  name_initials: string;
  blood_group: string;
  kell_negative: boolean;
  extended_phenotype: string;
  city: string;
  registered_year: number;
}

export interface ICMRLookupResponse {
  source: string;
  status: IntegrationStatusValue;
  fetched_at: string;
  filters: Record<string, string>;
  registered_donors: RegisteredRareDonor[];
}

// --- Simulator (Phase 9) ----------------------------------------------------

export interface CohortMemberState {
  donor_id: string;
  donor_name: string;
  blood_group: string;
  churn_30d: number;
  churn_60d: number;
  churn_90d: number;
}

export interface ScenarioState {
  active_donor_count: number;
  cohort: CohortMemberState[];
  avg_churn_90d: number;
  max_churn_90d: number;
  at_risk_count: number;
  schedule_status: SolverStatus;
  schedule_slots_count: number;
  schedule_objective: number;
  schedule_solve_time_ms: number;
  weak_donors: WeakDonor[];
  top_candidates: RecruitmentCandidate[];
}

export interface ScenarioDelta {
  cohort_size_change: number;
  avg_churn_change: number;
  at_risk_change: number;
  schedule_slots_change: number;
  schedule_objective_change: number;
}

export interface ScenarioRequest {
  ejected_donor_ids: string[];
}

export interface ScenarioOutcome {
  bridge_id: string;
  bridge_name: string;
  today: string;
  requested: ScenarioRequest;
  baseline: ScenarioState;
  scenario: ScenarioState;
  delta: ScenarioDelta;
}


// --- WhatsApp (Phase 10) ----------------------------------------------------

export type MessageDirection = "inbound" | "outbound";
export type MessageStatus =
  | "queued"
  | "sent"
  | "delivered"
  | "read"
  | "received"
  | "failed"
  | "mocked";

export interface DonorSummaryRef {
  id: string;
  name: string;
  blood_group: BloodGroup;
  phone: string;
  preferred_language: string;
  city: string;
}

export interface WhatsAppMessage {
  id: string;
  donor_id: string | null;
  bridge_id: string | null;
  direction: MessageDirection;
  from_number: string;
  to_number: string;
  body: string;
  status: MessageStatus;
  twilio_sid: string | null;
  template_key: string | null;
  /** G4: ISO language code the template was rendered in (or null for raw inbound). */
  language: string | null;
  created_at: string;
}

export interface CaregiverRef {
  patient_id: string;
  patient_name: string;
  patient_blood_group: BloodGroup;
  caregiver_name: string;
  caregiver_relation: string | null;
  caregiver_phone: string;
}

export interface ConversationSummary {
  /** G5: discriminator. "donor" rows have `donor` populated; "caregiver" rows have `caregiver`. */
  kind: "donor" | "caregiver";
  donor: DonorSummaryRef | null;
  caregiver: CaregiverRef | null;
  last_message: WhatsAppMessage;
  message_count: number;
}

export interface ConversationsList {
  conversations: ConversationSummary[];
  total: number;
}

export interface ConversationThread {
  donor: DonorSummaryRef;
  messages: WhatsAppMessage[];
}

export interface CaregiverConversationThread {
  caregiver: CaregiverRef;
  messages: WhatsAppMessage[];
}

export interface NotifyCaregiverRequest {
  template_key:
    | "recruit_success_caregiver"
    | "bridge_covered_caregiver"
    | "transfusion_confirmed_caregiver";
  language?: AgentLanguage | null;
  added_donor_name?: string | null;
}

export interface NotifyCaregiverResponse {
  patient_id: string;
  template_key: string;
  language_used: AgentLanguage | null;
  fallback_used: boolean;
  message_id: string | null;
  message_sid: string | null;
  body: string | null;
}

export interface SendMessageRequest {
  donor_id: string;
  body?: string | null;
  template_key?: string | null;
  bridge_id?: string | null;
  /** G4: pick a specific language for the template render. */
  language?: AgentLanguage | null;
}

export interface SendMessageResponse {
  message: WhatsAppMessage;
  is_live_twilio: boolean;
  language_used?: AgentLanguage | null;
  fallback_used?: boolean;
}

export interface TwilioStatusInfo {
  is_live: boolean;
  from_number: string;
  sandbox_join_instructions: string;
}

export interface MessageTemplate {
  key: string;
  label: string;
  requires_bridge: boolean;
  /** G4: hand-authored bodies per ISO language code (en, hi, te, ta, mr, bn, kn, gu). */
  bodies: Record<string, string>;
  supported_languages: string[];
}

// --- Care Agent (Phase 11) --------------------------------------------------

export type AgentLanguage = "en" | "hi" | "te" | "ta" | "mr" | "bn" | "kn" | "gu";
export type AgentProvider = "bedrock" | "anthropic" | "mock";
export type AgentRole = "user" | "assistant" | "system";

export interface AgentStatus {
  is_live: boolean;
  provider: AgentProvider;
  model: string;
  supported_languages: AgentLanguage[];
  // Multi-model routing — populated when provider === "bedrock"
  multi_model?: boolean;
  chat_model?: string | null;
  intent_model?: string | null;
  embedding_model?: string | null;
}

export interface AgentContextSource {
  kind: string;
  label: string;
  detail: string | null;
}

export interface AgentMessage {
  id: string;
  session_id: string;
  role: AgentRole;
  content: string;
  donor_id: string | null;
  bridge_id: string | null;
  patient_id: string | null;
  language: string;
  provider: string | null;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  task: string | null;
  created_at: string;
}

export interface AgentChatRequest {
  query: string;
  session_id?: string | null;
  donor_id?: string | null;
  bridge_id?: string | null;
  patient_id?: string | null;
  language?: AgentLanguage;
}

export interface RetrievedMemory {
  id: string;
  kind: string;
  entity_id: string | null;
  summary: string;
  score: number;
}

export interface CohortMemory {
  id: string;
  kind: string;
  entity_id: string | null;
  summary: string;
  embedding_provider: string;
  embedding_dim: number;
  created_at: string;
}

export interface AgentChatResponse {
  session_id: string;
  user_message: AgentMessage;
  assistant_message: AgentMessage;
  sources: AgentContextSource[];
  provider: AgentProvider;
  model: string;
  is_live: boolean;
  language: AgentLanguage;
  detected_language: AgentLanguage | null;
  retrieved_memories: RetrievedMemory[];
  task?: string | null;
}

export interface AgentSessionSummary {
  session_id: string;
  first_message_at: string;
  last_message_at: string;
  message_count: number;
  last_user_query: string;
  language: string;
}

// --- Real-data ML predictions (Module Integration) -------------------------

export type ChurnClass =
  | "active"
  | "inactive_not_donated_1y"
  | "inactive_limited_despite_calls";

export interface ChurnTopFactor {
  feature: string;
  global_importance: number;
  value: number;
}

export interface ChurnPrediction {
  donor_id: string;
  donor_name: string;
  model_winner: string;
  model_metrics: {
    binary_auc?: number;
    macro_f1?: number;
    weighted_f1?: number;
    cv_macro_f1_mean?: number;
    cv_macro_f1_std?: number;
    per_class_auc?: Record<string, number>;
    [k: string]: unknown;
  };
  p_active: number;
  p_not_donated_1y: number;
  p_limited_despite_calls: number;
  predicted_class: ChurnClass;
  predicted_label: string;
  recommended_action: string;
  top_factors: ChurnTopFactor[];
}

export interface SurvivalTopFactor {
  feature: string;
  global_importance: number;
  value: number;
}

export interface SurvivalPrediction {
  donor_id: string;
  donor_name: string;
  model_winner: string;
  model_metrics: {
    c_index?: number;
    c_index_train?: number;
    n_events?: number;
    n_censored?: number;
    median_survival_days?: number | null;
    inference_us_per_prediction?: number;
  };
  risk_score: number;
  median_survival_days: number | null;
  p_survive_90d: number;
  p_survive_180d: number;
  p_survive_365d: number;
  top_factors: SurvivalTopFactor[];
}

export interface MlModelMetrics {
  churn: {
    loaded: boolean;
    winner: string | null;
    metrics: ChurnPrediction["model_metrics"] | null;
    feature_names: string[] | null;
  };
  survival: {
    loaded: boolean;
    winner: string | null;
    metrics: SurvivalPrediction["model_metrics"] | null;
    feature_names: string[] | null;
  };
}

export interface MlBakeoffRow {
  name: string;
  // Churn fields:
  cv_macro_f1_mean?: number;
  cv_macro_f1_std?: number;
  test_macro_f1?: number;
  test_weighted_f1?: number;
  test_binary_auc?: number;
  test_per_class_auc?: Record<string, number>;
  train_time_ms?: number;
  inference_time_us?: number;
  // Survival fields:
  c_index_train?: number;
  c_index_test?: number;
  failed?: boolean;
  error?: string;
}

export interface MlBakeoffReport {
  model_name: "churn" | "survival";
  winner: string | null;
  n_algorithms_tested: number;
  rows: MlBakeoffRow[];
}

export interface SystemClock {
  today: string;
  wall_clock: string;
  is_anchored: boolean;
  days_anchored_back: number;
  label: string;
}

// --- Alert Allocator types ---

export interface OutreachCycleSummary {
  cycle_at: string;
  open_slots: number;
  waves_created: number;
  pings_planned: number;
  critical_slots: number;
  high_slots: number;
  medium_slots: number;
  fully_covered_slots: number;
  shortfall_slots: number;
  dry_run: boolean;
}

export interface OutreachAllocationBatch {
  donor_id: string;
  donor_name: string;
  blood_group: string;
  city: string;
  preferred_language: string;
}

export interface OutreachAllocation {
  patient_id: string;
  patient_name: string;
  slot_date: string;
  urgency: "critical" | "high" | "medium" | "planned";
  gap_days: number;
  target_p_accept: number;
  realised_p_accept: number;
  fully_covered: boolean;
  pool_size: number;
  batch_size: number;
  batch: OutreachAllocationBatch[];
}

export interface OutreachCycleResponse {
  summary: OutreachCycleSummary;
  allocations: OutreachAllocation[];
}

export interface OutreachWaveSummary {
  id: string;
  patient_id: string;
  bridge_id: string | null;
  slot_date: string;
  tier: string;
  urgency: string;
  status: string;
  target_p_accept: number;
  realised_p_accept: number;
  gap_days_at_creation: number;
  pool_size_at_creation: number;
  triggered_by: string;
  created_at: string | null;
  expires_at: string | null;
  resolved_at: string | null;
  resolved_by_donor_id: string | null;
}

export interface OutreachWaveList {
  items: OutreachWaveSummary[];
  total: number;
}

export interface OutreachPingRow {
  id: string;
  donor_id: string;
  channel: "whatsapp" | "phone";
  response: "pending" | "accepted" | "declined" | "no_reply" | "cancelled";
  sent_at: string | null;
  expires_at: string | null;
  response_at: string | null;
  composite_score: number;
  adjusted_response_rate: number;
  language: string | null;
}

export interface OutreachWaveDetail extends OutreachWaveSummary {
  pings: OutreachPingRow[];
}

export interface OutreachActionResult {
  [key: string]: unknown;
}

export interface CommitAllocationDiagnostic {
  patient_id: string;
  wave_id?: string;
  donor_count?: number;
  realised_p_accept?: number;
  skipped_reason?: string;
  dropped?: string[];
}

export interface CommitAllocationsResponse {
  created_count: number;
  created_wave_ids: string[];
  diagnostics: CommitAllocationDiagnostic[];
}

export interface OutreachAnalytics {
  lookback_days: number;
  waves: {
    total: number;
    active: number;
    accepted: number;
    expired: number;
    by_tier: Record<string, number>;
  };
  pings: {
    total: number;
    accepted: number;
    declined: number;
    no_reply: number;
    pending: number;
    pings_per_acceptance: number;
    avg_minutes_to_accept_by_urgency: Record<string, number>;
  };
  donor_fatigue: Record<string, number>;
  manual_queue: {
    open: number;
    outcomes: Record<string, number>;
  };
  emergency: {
    total: number;
    active: number;
    recent: Array<{
      id: string;
      patient_id: string;
      triggered_at: string;
      triggered_by: string;
      hospital_name: string | null;
      reach_window_min: number;
      pool_size_at_trigger: number;
      status: string;
    }>;
  };
}

export interface EmergencyTriggerResponse {
  event_id: string;
  wave_id: string | null;
  reachable_count: number;
  pool_size_before_filter: number;
  deadline_at: string;
  reach_window_min: number;
  status: "active" | "resolved" | "expired";
}

export interface DonorPoolInsights {
  n_scored: number;
  predicted_class_counts: Partial<Record<ChurnClass, number>>;
  p_active_mean: number;
  high_risk_count: number;
  low_risk_count: number;
  survival_365d_median: number;
  survival_365d_p25: number;
  survival_365d_p75: number;
  needs_reminder_count: number;
  stop_calling_count: number;
  churn_winner: string;
  survival_winner: string;
}

// --- Client -----------------------------------------------------------------

class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Attach the Cognito ID token to every request when one exists.
 *
 * We dynamic-import `@/lib/cognito` only in the browser so the api module
 * stays safe to import from server-rendered code paths (amazon-cognito-
 * identity-js touches `window.localStorage` at construction time).
 *
 * Endpoints that don't require auth still work — they just receive a
 * request without the Authorization header.
 */
async function _maybeAuthHeader(): Promise<Record<string, string>> {
  if (typeof window === "undefined") return {};
  try {
    const { getIdTokenForRequest } = await import("./cognito");
    const token = await getIdTokenForRequest();
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeader = await _maybeAuthHeader();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(text || res.statusText, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async listBridges(opts: { skip?: number; limit?: number } = {}): Promise<BridgesPage> {
    const params = new URLSearchParams();
    if (opts.skip !== undefined) params.set("skip", String(opts.skip));
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<BridgesPage>(`/bridges${qs ? `?${qs}` : ""}`);
  },

  async getBridge(id: string): Promise<BridgeDetail> {
    return request<BridgeDetail>(`/bridges/${id}`);
  },

  async listDonors(filters: DonorFilters = {}): Promise<DonorsPage> {
    const params = new URLSearchParams();
    if (filters.skip !== undefined) params.set("skip", String(filters.skip));
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.search) params.set("search", filters.search);
    if (filters.blood_group) params.set("blood_group", filters.blood_group);
    if (filters.city) params.set("city", filters.city);
    if (filters.is_active !== undefined) params.set("is_active", String(filters.is_active));
    if (filters.kell_negative !== undefined)
      params.set("kell_negative", String(filters.kell_negative));
    if (filters.sort) params.set("sort", filters.sort);
    if (filters.order) params.set("order", filters.order);
    const qs = params.toString();
    return request<DonorsPage>(`/donors${qs ? `?${qs}` : ""}`);
  },

  async getDonor(id: string): Promise<DonorDetail> {
    return request<DonorDetail>(`/donors/${id}`);
  },

  async listPatients(filters: PatientFilters = {}): Promise<PatientsPage> {
    const params = new URLSearchParams();
    if (filters.skip !== undefined) params.set("skip", String(filters.skip));
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.search) params.set("search", filters.search);
    if (filters.blood_group) params.set("blood_group", filters.blood_group);
    if (filters.city) params.set("city", filters.city);
    if (filters.active !== undefined) params.set("active", String(filters.active));
    if (filters.has_bridge !== undefined) params.set("has_bridge", String(filters.has_bridge));
    if (filters.bridge_health) params.set("bridge_health", filters.bridge_health);
    if (filters.sort) params.set("sort", filters.sort);
    if (filters.order) params.set("order", filters.order);
    const qs = params.toString();
    return request<PatientsPage>(`/patients${qs ? `?${qs}` : ""}`);
  },

  async getPatient(id: string): Promise<PatientProfile> {
    return request<PatientProfile>(`/patients/${id}`);
  },

  async getBridgeStability(id: string): Promise<BridgeStability> {
    return request<BridgeStability>(`/bridges/${id}/stability`);
  },

  // --- Real-data ML predictions (Module Integration) ---

  async getChurnPrediction(donorId: string): Promise<ChurnPrediction> {
    return request<ChurnPrediction>(`/donors/${donorId}/churn-prediction`);
  },

  async getDonorSurvival(donorId: string): Promise<SurvivalPrediction> {
    return request<SurvivalPrediction>(`/donors/${donorId}/survival`);
  },

  async getMlModelMetrics(): Promise<MlModelMetrics> {
    return request<MlModelMetrics>(`/ml/model-metrics`);
  },

  async getMlBakeoff(
    modelName: "churn" | "survival",
  ): Promise<MlBakeoffReport> {
    return request<MlBakeoffReport>(`/ml/bakeoff/${modelName}`);
  },

  async getSystemClock(): Promise<SystemClock> {
    return request<SystemClock>(`/system/clock`);
  },

  async getDonorPoolInsights(): Promise<DonorPoolInsights> {
    return request<DonorPoolInsights>(`/ml/donor-pool-insights`);
  },

  // --- Alert Allocator (fully automated — no manual phone queue) ---
  async runOutreachCycle(opts: { dryRun?: boolean; horizonDays?: number } = {}): Promise<OutreachCycleResponse> {
    const qs = new URLSearchParams();
    if (opts.dryRun !== undefined) qs.set("dry_run", String(opts.dryRun));
    if (opts.horizonDays) qs.set("horizon_days", String(opts.horizonDays));
    return request<OutreachCycleResponse>(
      `/outreach/run-cycle?${qs}`,
      { method: "POST" },
    );
  },

  async listOutreachWaves(opts: { status?: string; limit?: number } = {}): Promise<OutreachWaveList> {
    const qs = new URLSearchParams();
    if (opts.status) qs.set("status", opts.status);
    if (opts.limit) qs.set("limit", String(opts.limit));
    return request<OutreachWaveList>(`/outreach/waves?${qs}`);
  },

  async getOutreachWave(waveId: string): Promise<OutreachWaveDetail> {
    return request<OutreachWaveDetail>(`/outreach/waves/${waveId}`);
  },

  async dispatchWave(waveId: string, overrideQuietHours: boolean = false): Promise<OutreachActionResult> {
    return request<OutreachActionResult>(
      `/outreach/waves/${waveId}/dispatch?override_quiet_hours=${overrideQuietHours}`,
      { method: "POST" },
    );
  },

  async promoteWaveToManual(waveId: string): Promise<OutreachActionResult> {
    return request<OutreachActionResult>(
      `/outreach/waves/${waveId}/promote-to-manual`,
      { method: "POST" },
    );
  },

  async forceIncludeDonor(waveId: string, donorId: string): Promise<OutreachActionResult> {
    return request<OutreachActionResult>(
      `/outreach/waves/${waveId}/force-include?donor_id=${donorId}`,
      { method: "POST" },
    );
  },

  async forceExcludeDonor(waveId: string, donorId: string): Promise<OutreachActionResult> {
    return request<OutreachActionResult>(
      `/outreach/waves/${waveId}/force-exclude?donor_id=${donorId}`,
      { method: "POST" },
    );
  },

  async expireAndSweep(autoEscalate: boolean = true): Promise<OutreachActionResult> {
    return request<OutreachActionResult>(
      `/outreach/expire-and-sweep?auto_escalate=${autoEscalate}`,
      { method: "POST" },
    );
  },

  async cancelOutreachAcceptance(donorId: string, waveId?: string): Promise<OutreachActionResult> {
    const qs = new URLSearchParams({ donor_id: donorId });
    if (waveId) qs.set("wave_id", waveId);
    return request<OutreachActionResult>(
      `/outreach/cancel-acceptance?${qs}`,
      { method: "POST" },
    );
  },

  async commitAllocations(
    selections: Array<{
      patient_id: string;
      slot_date: string;
      donor_ids: string[];
    }>,
    triggered_by: string = "coordinator_manual",
  ): Promise<CommitAllocationsResponse> {
    return request<CommitAllocationsResponse>(`/outreach/commit-allocations`, {
      method: "POST",
      body: JSON.stringify({ selections, triggered_by }),
    });
  },

  async getOutreachAnalytics(lookbackDays: number = 30): Promise<OutreachAnalytics> {
    return request<OutreachAnalytics>(
      `/outreach/analytics?lookback_days=${lookbackDays}`,
    );
  },

  async triggerEmergency(opts: {
    patientId: string;
    coordinatorName: string;
    deadlineIso: string;
    justification: string;
    hospitalLat?: number;
    hospitalLng?: number;
    hospitalName?: string;
  }): Promise<EmergencyTriggerResponse> {
    return request<EmergencyTriggerResponse>(`/outreach/emergency`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: opts.patientId,
        coordinator_name: opts.coordinatorName,
        transfusion_deadline_at: opts.deadlineIso,
        justification: opts.justification,
        hospital_lat: opts.hospitalLat,
        hospital_lng: opts.hospitalLng,
        hospital_name: opts.hospitalName,
      }),
    });
  },

  async getBridgeSchedule(
    id: string,
    opts: { horizonDays?: number } = {},
  ): Promise<BridgeSchedule> {
    const params = new URLSearchParams();
    if (opts.horizonDays) params.set("horizon_days", String(opts.horizonDays));
    const qs = params.toString();
    return request<BridgeSchedule>(`/bridges/${id}/schedule${qs ? `?${qs}` : ""}`);
  },

  async resolveBridgeSchedule(id: string): Promise<BridgeSchedule> {
    return request<BridgeSchedule>(`/bridges/${id}/schedule/resolve`, { method: "POST" });
  },

  async listRecommendations(opts: {
    onlyWeak?: boolean;
    topKPerBridge?: number;
    atRiskThreshold?: number;
  } = {}): Promise<RecommendationsInbox> {
    const params = new URLSearchParams();
    if (opts.onlyWeak !== undefined) params.set("only_weak", String(opts.onlyWeak));
    if (opts.topKPerBridge !== undefined)
      params.set("top_k_per_bridge", String(opts.topKPerBridge));
    if (opts.atRiskThreshold !== undefined)
      params.set("at_risk_threshold", String(opts.atRiskThreshold));
    const qs = params.toString();
    return request<RecommendationsInbox>(`/recommendations${qs ? `?${qs}` : ""}`);
  },

  async getBridgeRecommendations(
    bridgeId: string,
    opts: { topK?: number; atRiskThreshold?: number } = {},
  ): Promise<BridgeRecommendation> {
    const params = new URLSearchParams();
    if (opts.topK !== undefined) params.set("top_k", String(opts.topK));
    if (opts.atRiskThreshold !== undefined)
      params.set("at_risk_threshold", String(opts.atRiskThreshold));
    const qs = params.toString();
    return request<BridgeRecommendation>(
      `/bridges/${bridgeId}/recommendations${qs ? `?${qs}` : ""}`,
    );
  },

  async recruit(bridgeId: string, payload: RecruitRequest): Promise<RecruitResponse> {
    return request<RecruitResponse>(`/bridges/${bridgeId}/recruit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async listPendingRecruits(bridgeId: string): Promise<PendingRecruit[]> {
    return request<PendingRecruit[]>(`/bridges/${bridgeId}/pending-recruits`);
  },

  async listPendingActions(donorId: string): Promise<PendingAction[]> {
    return request<PendingAction[]>(`/donors/${donorId}/pending-actions`);
  },

  async getResponseHistory(donorId: string, days = 30): Promise<ResponseHistory> {
    return request<ResponseHistory>(`/donors/${donorId}/response-history?days=${days}`);
  },

  async getScheduleHistory(bridgeId: string, limit = 5): Promise<ScheduleHistory> {
    return request<ScheduleHistory>(`/bridges/${bridgeId}/schedule-history?limit=${limit}`);
  },

  async getSwapRequests(bridgeId: string, limit = 20): Promise<SwapRequestsList> {
    return request<SwapRequestsList>(`/bridges/${bridgeId}/swap-requests?limit=${limit}`);
  },

  async getAnalytics(): Promise<AnalyticsResponse> {
    return request<AnalyticsResponse>(`/analytics`);
  },

  async getIntegrations(): Promise<IntegrationsStatusList> {
    return request<IntegrationsStatusList>(`/integrations`);
  },

  async getERaktKoshInventory(
    opts: { city?: string; bloodGroup?: string } = {},
  ): Promise<ERaktKoshInventoryResponse> {
    const params = new URLSearchParams();
    if (opts.city) params.set("city", opts.city);
    if (opts.bloodGroup) params.set("blood_group", opts.bloodGroup);
    const qs = params.toString();
    return request<ERaktKoshInventoryResponse>(
      `/integrations/eraktkosh/inventory${qs ? `?${qs}` : ""}`,
    );
  },

  async lookupICMR(
    opts: { bloodGroup?: string; kellNegative?: boolean; city?: string } = {},
  ): Promise<ICMRLookupResponse> {
    const params = new URLSearchParams();
    if (opts.bloodGroup) params.set("blood_group", opts.bloodGroup);
    if (opts.kellNegative !== undefined)
      params.set("kell_negative", String(opts.kellNegative));
    if (opts.city) params.set("city", opts.city);
    const qs = params.toString();
    return request<ICMRLookupResponse>(
      `/integrations/icmr-rdri/lookup${qs ? `?${qs}` : ""}`,
    );
  },

  async runScenario(
    bridgeId: string,
    ejectedDonorIds: string[],
  ): Promise<ScenarioOutcome> {
    return request<ScenarioOutcome>(
      `/simulator/bridges/${bridgeId}/scenario`,
      {
        method: "POST",
        body: JSON.stringify({ ejected_donor_ids: ejectedDonorIds }),
      },
    );
  },

  async getWhatsAppStatus(): Promise<TwilioStatusInfo> {
    return request<TwilioStatusInfo>(`/whatsapp/status`);
  },

  async listWhatsAppTemplates(): Promise<MessageTemplate[]> {
    return request<MessageTemplate[]>(`/whatsapp/templates`);
  },

  async listWhatsAppConversations(): Promise<ConversationsList> {
    return request<ConversationsList>(`/whatsapp/conversations`);
  },

  async getWhatsAppThread(donorId: string): Promise<ConversationThread> {
    return request<ConversationThread>(`/whatsapp/conversations/${donorId}`);
  },

  async sendWhatsApp(payload: SendMessageRequest): Promise<SendMessageResponse> {
    return request<SendMessageResponse>(`/whatsapp/send`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getCaregiverThread(patientId: string): Promise<CaregiverConversationThread> {
    return request<CaregiverConversationThread>(
      `/whatsapp/conversations/caregiver/${patientId}`,
    );
  },

  async notifyCaregiver(
    patientId: string,
    payload: NotifyCaregiverRequest,
  ): Promise<NotifyCaregiverResponse> {
    return request<NotifyCaregiverResponse>(
      `/patients/${patientId}/notify-caregiver`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },

  async getAgentStatus(): Promise<AgentStatus> {
    return request<AgentStatus>(`/agent/status`);
  },

  async chatWithAgent(payload: AgentChatRequest): Promise<AgentChatResponse> {
    return request<AgentChatResponse>(`/agent/chat`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async listAgentSessions(limit = 20): Promise<AgentSessionSummary[]> {
    return request<AgentSessionSummary[]>(`/agent/sessions?limit=${limit}`);
  },

  async getAgentSession(sessionId: string): Promise<AgentMessage[]> {
    return request<AgentMessage[]>(`/agent/sessions/${sessionId}`);
  },

  async listCohortMemories(opts: { entityId?: string; limit?: number } = {}): Promise<CohortMemory[]> {
    const params = new URLSearchParams();
    if (opts.entityId) params.set("entity_id", opts.entityId);
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<CohortMemory[]>(`/agent/memories${qs ? `?${qs}` : ""}`);
  },

  // ----- Automation Engine (Phase A) -----

  async getSchedulerStatus(): Promise<SchedulerStatus> {
    return request<SchedulerStatus>(`/system/scheduler/status`);
  },

  async listSchedulerJobs(): Promise<JobState[]> {
    return request<JobState[]>(`/system/scheduler/jobs`);
  },

  async getSchedulerJob(name: string, recentRuns = 10): Promise<JobDetail> {
    return request<JobDetail>(
      `/system/scheduler/jobs/${encodeURIComponent(name)}?recent_runs=${recentRuns}`,
    );
  },

  async updateSchedulerJob(
    name: string,
    body: { cron_override?: string | null; clear_override?: boolean },
  ): Promise<JobState> {
    return request<JobState>(
      `/system/scheduler/jobs/${encodeURIComponent(name)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },

  async pauseSchedulerJob(name: string): Promise<JobState> {
    return request<JobState>(
      `/system/scheduler/jobs/${encodeURIComponent(name)}/pause`,
      { method: "POST" },
    );
  },

  async resumeSchedulerJob(name: string): Promise<JobState> {
    return request<JobState>(
      `/system/scheduler/jobs/${encodeURIComponent(name)}/resume`,
      { method: "POST" },
    );
  },

  async triggerSchedulerJob(name: string): Promise<TriggerResult> {
    return request<TriggerResult>(
      `/system/scheduler/jobs/${encodeURIComponent(name)}/trigger`,
      { method: "POST" },
    );
  },

  async listSchedulerRuns(
    opts: {
      job?: string;
      status?: string;
      sinceHours?: number;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<RunsPage> {
    const params = new URLSearchParams();
    if (opts.job) params.set("job", opts.job);
    if (opts.status) params.set("status", opts.status);
    if (opts.sinceHours !== undefined) params.set("since_hours", String(opts.sinceHours));
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts.offset !== undefined) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<RunsPage>(`/system/scheduler/runs${qs ? `?${qs}` : ""}`);
  },

  async getSchedulerRun(id: string): Promise<RunDetail> {
    return request<RunDetail>(`/system/scheduler/runs/${id}`);
  },

  async pruneSchedulerRuns(olderThanDays: number): Promise<{ deleted: number }> {
    return request<{ deleted: number }>(
      `/system/scheduler/runs?older_than_days=${olderThanDays}`,
      { method: "DELETE" },
    );
  },

  async setSchedulerDemoMode(enabled: boolean): Promise<SchedulerStatus> {
    return request<SchedulerStatus>(`/system/scheduler/demo-mode`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  async getSchedulerMetrics(windowHours = 24): Promise<SchedulerMetrics> {
    return request<SchedulerMetrics>(
      `/system/scheduler/metrics?window_hours=${windowHours}`,
    );
  },

  async getSchedulerHealth(): Promise<SchedulerHealth> {
    return request<SchedulerHealth>(`/system/scheduler/health`);
  },

  // ----- Admin demo: one-click multi-channel fan-out -----

  async getDemoContacts(): Promise<DemoContacts> {
    return request<DemoContacts>(`/admin/demo/contacts`);
  },

  async fireAllDemoChannels(): Promise<FireAllResponse> {
    // Header-secret guard mirrors /admin/test/*. Lives in NEXT_PUBLIC so it
    // ships in the bundle — same trust model as the demo itself (one-click,
    // unauthenticated). Rotate the backend secret to disable instantly.
    const secret = process.env.NEXT_PUBLIC_DEMO_SECRET ?? "";
    return request<FireAllResponse>(`/admin/demo/fire-all`, {
      method: "POST",
      headers: { "X-Admin-Test-Secret": secret },
    });
  },

  // ----- Phase B: per-ping follow-ups -----

  async getPingFollowUps(pingId: string): Promise<PingFollowUps> {
    return request<PingFollowUps>(`/outreach/pings/${pingId}/follow-ups`);
  },

  async triggerPingNudge(pingId: string): Promise<PingNudgeResult> {
    return request<PingNudgeResult>(
      `/outreach/pings/${pingId}/follow-ups/nudge`,
      { method: "POST" },
    );
  },

  // ----- Phase C: Reply classifier audit + analytics -----

  async listReplyClassifications(
    opts: {
      donorId?: string;
      intent?: string;
      confidenceGte?: number;
      fromDate?: string;
      includeDeleted?: boolean;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<ReplyClassificationsPage> {
    const p = new URLSearchParams();
    if (opts.donorId) p.set("donor_id", opts.donorId);
    if (opts.intent) p.set("intent", opts.intent);
    if (opts.confidenceGte !== undefined) p.set("confidence_gte", String(opts.confidenceGte));
    if (opts.fromDate) p.set("from_date", opts.fromDate);
    if (opts.includeDeleted) p.set("include_deleted", "true");
    if (opts.limit !== undefined) p.set("limit", String(opts.limit));
    if (opts.offset !== undefined) p.set("offset", String(opts.offset));
    const qs = p.toString();
    return request<ReplyClassificationsPage>(
      `/reply-classifications${qs ? `?${qs}` : ""}`,
    );
  },

  async getReplyClassification(id: string): Promise<ReplyClassificationDetail> {
    return request<ReplyClassificationDetail>(`/reply-classifications/${id}`);
  },

  async listReplyClassificationsForDonor(
    donorId: string, limit = 50,
  ): Promise<ReplyClassificationsPage> {
    return request<ReplyClassificationsPage>(
      `/reply-classifications/by-donor/${donorId}?limit=${limit}`,
    );
  },

  async submitReplyClassificationFeedback(
    id: string,
    body: { corrected_intent: string | null; note?: string | null },
  ): Promise<ReplyClassificationDetail> {
    return request<ReplyClassificationDetail>(
      `/reply-classifications/${id}/feedback`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async softDeleteReplyClassification(id: string): Promise<{ id: string; deleted_at: string }> {
    return request<{ id: string; deleted_at: string }>(
      `/reply-classifications/${id}`,
      { method: "DELETE" },
    );
  },

  async getReplyIntentDistribution(windowDays = 30): Promise<IntentDistribution> {
    return request<IntentDistribution>(
      `/reply-classifications/distribution?window_days=${windowDays}`,
    );
  },

  async getReplyConfidenceHistogram(windowDays = 30): Promise<ConfidenceBucket[]> {
    return request<ConfidenceBucket[]>(
      `/reply-classifications/confidence-histogram?window_days=${windowDays}`,
    );
  },

  // ----- Phase E2: SES email channel -----

  async listEmails(opts: {
    recipient?: string;
    template_key?: string;
    status?: string;
    since_hours?: number;
    limit?: number;
    offset?: number;
  } = {}): Promise<EmailMessagesPage> {
    const p = new URLSearchParams();
    if (opts.recipient) p.set("recipient", opts.recipient);
    if (opts.template_key) p.set("template_key", opts.template_key);
    if (opts.status) p.set("status", opts.status);
    if (opts.since_hours !== undefined) p.set("since_hours", String(opts.since_hours));
    if (opts.limit !== undefined) p.set("limit", String(opts.limit));
    if (opts.offset !== undefined) p.set("offset", String(opts.offset));
    const qs = p.toString();
    return request<EmailMessagesPage>(`/emails${qs ? `?${qs}` : ""}`);
  },

  async getEmail(id: string): Promise<EmailMessageOut> {
    return request<EmailMessageOut>(`/emails/${id}`);
  },

  async getEmailDistribution(windowDays = 30): Promise<EmailDistribution> {
    return request<EmailDistribution>(
      `/emails/distribution?window_days=${windowDays}`,
    );
  },

  async sendTestEmail(body: { recipient: string; subject?: string; body?: string }): Promise<TestEmailResponse> {
    return request<TestEmailResponse>(`/emails/test`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ----- Phase E3: SQS dispatch queue -----

  async getDispatchQueueStatus(): Promise<DispatchQueueStatus> {
    return request<DispatchQueueStatus>(`/system/dispatch-queue/status`);
  },

  async listDispatchMessages(limit = 10): Promise<DispatchMessageOut[]> {
    return request<DispatchMessageOut[]>(
      `/system/dispatch-queue/messages?limit=${limit}`,
    );
  },

  async listDispatchDLQ(limit = 10): Promise<DispatchMessageOut[]> {
    return request<DispatchMessageOut[]>(
      `/system/dispatch-queue/dlq?limit=${limit}`,
    );
  },

  async replayDispatchDLQ(): Promise<{ replayed: number; failed: number }> {
    return request<{ replayed: number; failed: number }>(
      `/system/dispatch-queue/replay-dlq`,
      { method: "POST" },
    );
  },

  // ----- Phase E4: SNS event bus -----

  async getEventsDispatcherStatus(): Promise<EventsDispatcherStatus> {
    return request<EventsDispatcherStatus>(`/system/events/status`);
  },

  async listRecentEvents(limit = 20, topic?: string): Promise<EventOut[]> {
    const p = new URLSearchParams();
    p.set("limit", String(limit));
    if (topic) p.set("topic", topic);
    return request<EventOut[]>(`/system/events/recent?${p.toString()}`);
  },

  async listEventTopics(): Promise<TopicWithSubscribers[]> {
    return request<TopicWithSubscribers[]>(`/system/events/topics`);
  },
};

export interface TopicWithSubscribers {
  topic: string;
  subscribers: string[];
}

export interface EventOut {
  message_id: string;
  topic_name: string;
  body: Record<string, unknown>;
  published_at: string;
  is_mock: boolean;
}

export interface EventsDispatcherStatus {
  running: boolean;
  delivered: number;
  failed: number;
  last_tick_at: string | null;
  topics: TopicWithSubscribers[];
}

export interface DispatchQueueStatus {
  primary_depth: number;
  in_flight: number;
  dlq_depth: number;
  mode: string;
  error: string | null;
  worker_running: boolean;
  worker_received: number;
  worker_sent: number;
  worker_duplicates_skipped: number;
  worker_failed: number;
  worker_last_drained_at: string | null;
  worker_started_at: string | null;
}

export interface DispatchMessageOut {
  message_id: string;
  body: Record<string, unknown>;
  is_mock: boolean;
  queue_name: string;
  approximate_receive_count: number;
}

// ----- Phase E2 types -----

export interface EmailMessageOut {
  id: string;
  direction: string;
  recipient_email: string;
  from_email: string;
  subject: string;
  body: string;
  template_key: string | null;
  language: string | null;
  ses_message_id: string | null;
  status: string;
  is_mock: boolean;
  error_message: string | null;
  donor_id: string | null;
  caregiver_for_patient_id: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface EmailMessagesPage {
  items: EmailMessageOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmailTemplateCount {
  template_key: string;
  sent: number;
  failed: number;
  mocked: number;
  skipped: number;
}

export interface EmailDistribution {
  window_days: number;
  total: number;
  sent: number;
  failed: number;
  mocked: number;
  by_template: EmailTemplateCount[];
}

export interface TestEmailResponse {
  message_id: string;
  is_mock: boolean;
  status: string;
  persisted_id: string;
}

// ----- Reply classifier types -----

export interface ReplyClassificationOut {
  id: string;
  donor_id: string;
  message_id: string | null;
  text_excerpt: string;
  language: string | null;
  intent: string;
  confidence: number;
  extracted_date: string | null;
  extracted_reason: string | null;
  model_used: string | null;
  used_fallback: boolean;
  classified_at: string;
  operator_corrected_intent: string | null;
  operator_feedback_note: string | null;
  feedback_at: string | null;
}

export interface ReplyClassificationDetail extends ReplyClassificationOut {
  raw_response: string | null;
}

export interface ReplyClassificationsPage {
  items: ReplyClassificationOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface IntentCount {
  intent: string;
  count: number;
}

export interface IntentDistribution {
  window_days: number;
  total: number;
  counts: IntentCount[];
  avg_confidence: number;
  fallback_rate: number;
  top_reschedule_reasons: string[];
}

export interface ConfidenceBucket {
  low: number;
  high: number;
  count: number;
}

export interface PingFollowUps {
  ping_id: string;
  wave_id: string;
  donor_id: string;
  response: string;
  sent_at: string | null;
  response_at: string | null;
  nudge: { count: number; last_sent_at: string | null };
  reminder: { sent_at: string | null };
  thank_you: { sent_at: string | null };
}

export interface PingNudgeResult {
  ping_id: string;
  sent: boolean;
  nudge_count: number;
  last_nudge_at: string | null;
}

// ----- Automation Engine types -----

export interface JobState {
  name: string;
  description: string;
  enabled: boolean;
  cron_default: string;
  cron_demo: string;
  cron_override: string | null;
  effective_cron: string;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface RunSummary {
  id: string;
  job_name: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: "success" | "failed" | "skipped";
  items_processed: number;
  error_message: string | null;
}

export interface RunDetail extends RunSummary {
  payload: Record<string, unknown> | null;
}

export interface RunsPage {
  items: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobDetail extends JobState {
  recent_runs: RunSummary[];
}

export interface SchedulerStatus {
  running: boolean;
  demo_mode: boolean;
  job_count: number;
  enabled_count: number;
  last_tick_at: string | null;
  failures_24h: number;
  jobs: JobState[];
}

export interface TriggerResult {
  job_name: string;
  triggered: boolean;
  detail: string | null;
}

export interface JobMetric {
  job_name: string;
  success: number;
  failed: number;
  skipped: number;
  items_processed_total: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
}

export interface SchedulerMetrics {
  window_hours: number;
  overall: { success: number; failed: number; skipped: number; items_processed_total: number };
  by_job: JobMetric[];
}

export interface SchedulerHealth {
  healthy: boolean;
  issues: string[];
  last_tick_at: string | null;
  failure_streaks: Record<string, number>;
}

// ----- Admin demo (one-click multi-channel fan-out) -----------------------

export type DemoChannelKey = "voice" | "whatsapp" | "sms" | "email";

export interface ChannelResult {
  channel: DemoChannelKey;
  ok: boolean;
  is_mock: boolean;
  sid_or_message_id: string | null;
  status: string | null;
  error: string | null;
  duration_ms: number;
}

export interface DemoContext {
  phone: string;
  email: string;
  donor_id: string;
  donor_name: string;
  patient_id: string;
  patient_name: string;
  ping_id: string;
}

export interface OutreachCopy {
  source: string; // "bedrock" | "anthropic" | "mock" | "template_fallback"
  model: string;
  voice_question: string;
  whatsapp_body: string;
  sms_body: string;
  email_subject: string;
  email_body: string;
  tokens_in: number | null;
  tokens_out: number | null;
}

export interface FireAllResponse {
  fired_at: string;
  total_duration_ms: number;
  context: DemoContext;
  copy: OutreachCopy;
  channels: ChannelResult[];
}

export interface DemoContacts {
  phone: string;
  email: string;
}

export { ApiError };
