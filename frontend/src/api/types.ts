// Type contracts mirroring the backend case read-model
// (backend/app/services/demo/read_model.py). The UI never recomputes financial
// values — it renders what the deterministic backend already calculated.

export interface AttemptMetrics {
  total_attempts: number
  successful_attempts: number
  failed_attempts: number
  success_rate: number
  failure_rate: number
}

export interface WindowComparison {
  baseline: AttemptMetrics
  current: AttemptMetrics
  absolute_delta: number
  relative_delta: number
}

export interface AnomalyResult {
  metric: string
  method: string
  baseline: number
  baseline_mean: number
  baseline_std: number
  current: number
  absolute_delta: number
  relative_delta: number
  sample_size: number
  anomaly_score: number
  threshold: number
  is_anomalous: boolean
}

export interface TimeBucketStat {
  bucket: string
  attempt_count: number
  failure_count: number
  failure_rate: number
}

export interface MethodStat {
  method: string
  attempt_count: number
  failure_count: number
  failure_rate: number
  baseline_failure_rate: number
  delta: number
}

export interface CohortStat {
  cohort: string
  attempt_count: number
  failure_count: number
  failure_rate: number
  baseline_failure_rate: number
  delta: number
}

export interface ReasonStat {
  reason: string
  failure_count: number
  failure_rate: number
}

export interface MonetaryStat {
  currency: string
  total_amount_minor: number
  failed_amount_minor: number
}

export interface Symptom {
  title: string
  incident_type: string
  start_time: string | null
  end_time: string | null
  affected_dimension: string | null
  affected_value: string | null
  overall: WindowComparison
  anomaly: AnomalyResult
}

export interface HealthView {
  baseline_daily: TimeBucketStat[]
  temporal: TimeBucketStat[]
  payment_methods: MethodStat[]
  cohorts: CohortStat[]
  failure_reasons: ReasonStat[]
  monetary: MonetaryStat
}

export interface WorkerOutput {
  worker: string
  finding: string
  evidence_ids: string[]
  supports: string[]
  contradicts: string[]
  confidence: number
  anomaly_detected?: boolean
  peak_window?: string | null
  affected_methods?: string[]
  max_delta?: number
  affected_cohorts?: string[]
  returning_bias?: number | null
  dominant_reason?: string | null
  dominance_ratio?: number
  error?: string
}

export interface InvestigationView {
  investigation_id: string
  state: string
  anomaly_detected: boolean
  anomaly_score: number | null
  workers: WorkerOutput[]
}

export interface AlternativeHypothesis {
  hypothesis: string
  score: number
  reason: string
}

export interface EvidenceItem {
  id: string
  kind: string
  metric: string
  value: unknown
  unit: string | null
  baseline: unknown
  current: unknown
  delta: unknown
  window: string | null
  dimension: string | null
  source: string
}

export interface DiagnosisView {
  diagnosis_id: string
  incident_type: string
  leading_hypothesis: string
  confidence: number
  summary: string
  supporting_evidence_ids: string[]
  contradicting_evidence_ids: string[]
  alternative_hypotheses: AlternativeHypothesis[]
  recommended_action_type: string
  action_rationale: string
  uncertainties: string[]
  evidence: EvidenceItem[]
}

export interface PrescriptionTarget {
  payment_id: string
  payment_method: string
  failure_reason: string
  amount_minor: number
  currency: string
}

export interface PrescriptionView {
  action_id: string
  action_type: string
  status: string
  targets_count: number
  total_amount_minor: number
  currency: string
  rationale: string
  targets: PrescriptionTarget[]
}

export interface PolicyCheck {
  check: string
  status: 'PASS' | 'FAIL' | 'SKIP'
  actual: unknown
  limit: unknown
  message: string
}

export interface PolicyView {
  decision: string
  policy_version: string
  reasons: string[]
  action_snapshot_hash: string
  passed: boolean
  failed_checks: string[]
  checks: PolicyCheck[]
}

export interface ApprovalView {
  approval_id: string
  action_id: string
  status: string
  requested_at: string | null
  expires_at: string | null
  approved_at: string | null
  rejected_at: string | null
  decision_reason: string | null
  decided_by: string | null
  expired: boolean
}

export interface TreatmentView {
  execution_id: string
  action_id: string
  status: string
  provider: string
  provider_operation: string | null
  provider_reference: string | null
  links_count: number
  started_at: string | null
  completed_at: string | null
  error_code: string | null
  error_message: string | null
}

export interface TreatmentEffectiveness {
  intervention_outcome_id: string
  targets_total: number
  targets_recovered: number
  targets_pending: number
  targets_unrecovered: number
  currency: string
  amount_targeted_minor: number
  amount_recovered_minor: number
  amount_remaining_minor: number
  recovery_rate: number | null
  revenue_recovery_rate: number | null
  time_to_first_recovery_seconds: number | null
  time_to_last_recovery_seconds: number | null
  computed_at: string
}

export interface OutcomeView {
  outcome_id: string
  status: string
  targets_total: number
  targets_pending: number
  targets_succeeded: number
  targets_failed: number
  targets_expired: number
  amount_targeted_minor: number
  amount_recovered_minor: number
  conversion_rate: number | null
  currency: string
  finalized: boolean
  effectiveness: TreatmentEffectiveness
}

export interface StageView {
  key: string
  label: string
  complete: boolean
  status: string | null
  active: boolean
}

export interface TimelineEntry {
  stage: string
  status: string
  timestamp: string
  note: string | null
}

export interface CaseView {
  case_id: string
  environment: string
  started_at: string
  stages: StageView[]
  timeline: TimelineEntry[]
  symptom?: Symptom
  health?: HealthView
  investigation?: InvestigationView
  diagnosis?: DiagnosisView
  prescription?: PrescriptionView
  policy?: PolicyView
  approval?: ApprovalView
  treatment?: TreatmentView
  outcome?: OutcomeView
}
export interface ConsultationTimings {
  context_build_ms: number
  model_latency_ms: number
  speech_latency_ms: number
  total_latency_ms: number
}

export interface ConsultationResponse {
  consultation_id: string
  case_id: string
  question: string
  answer: string
  answer_type: string
  referenced_sections: string[]
  generated_at: string
  model: string
  timings: ConsultationTimings
}

export interface ConsultationRecord {
  consultation_id: string
  case_id: string
  question: string
  answer: string
  answer_type: string
  referenced_sections: string[]
  model: string
  created_at: string
}

export interface SpeechAudio {
  mime_type: string
  data_base64: string
  byte_size: number
  duration_ms: number | null
  provider: string
  voice: string | null
  consultation_id: string
  speech_latency_ms: number
}

export interface HealthStatus {
  status: string
  version: string
  environment: string
  razorpay_mode: string
  speech_provider: string
  consultation: string
  world_loaded: boolean
}
