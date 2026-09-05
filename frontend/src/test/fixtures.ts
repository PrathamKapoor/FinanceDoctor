import type {
  CaseView,
  DiagnosisView,
  HealthView,
  PolicyView,
  Symptom,
} from '../api/types'

// Deterministic fixture values mirroring the known Stage 1-5 seed=42 incident.
// These are the backend-calculated numbers; the UI renders them unchanged.

export const symptomFixture: Symptom = {
  title: 'PAYMENT HEALTH INCIDENT DETECTED',
  incident_type: 'PAYMENT_METHOD_FAILURE_SPIKE',
  start_time: '2026-07-31T14:37:00',
  end_time: '2026-07-31T17:37:00',
  affected_dimension: 'payment_method',
  affected_value: 'UPI',
  overall: {
    baseline: {
      total_attempts: 6057,
      successful_attempts: 5788,
      failed_attempts: 269,
      success_rate: 0.9546,
      failure_rate: 0.0454,
    },
    current: {
      total_attempts: 400,
      successful_attempts: 313,
      failed_attempts: 87,
      success_rate: 0.7825,
      failure_rate: 0.2175,
    },
    absolute_delta: 0.1721,
    relative_delta: 3.79,
  },
  anomaly: {
    metric: 'payment_failure_rate',
    method: 'z-score vs daily baseline distribution',
    baseline: 0.0454,
    baseline_mean: 0.0476,
    baseline_std: 0.016,
    current: 0.2175,
    absolute_delta: 0.1721,
    relative_delta: 3.79,
    sample_size: 400,
    anomaly_score: 10.854,
    threshold: 3.0,
    is_anomalous: true,
  },
}

export const healthFixture: HealthView = {
  baseline_daily: [
    { bucket: '2026-07-01', attempt_count: 200, failure_count: 9, failure_rate: 0.045 },
    { bucket: '2026-07-02', attempt_count: 200, failure_count: 10, failure_rate: 0.05 },
  ],
  temporal: [
    { bucket: '2026-07-31T14:00:00', attempt_count: 100, failure_count: 22, failure_rate: 0.22 },
  ],
  payment_methods: [
    { method: 'UPI', attempt_count: 204, failure_count: 78, failure_rate: 0.3824, baseline_failure_rate: 0.0336, delta: 0.3488 },
    { method: 'CARD', attempt_count: 124, failure_count: 8, failure_rate: 0.0645, baseline_failure_rate: 0.0614, delta: 0.0031 },
    { method: 'NETBANKING', attempt_count: 49, failure_count: 1, failure_rate: 0.0204, baseline_failure_rate: 0.0482, delta: -0.0278 },
    { method: 'WALLET', attempt_count: 23, failure_count: 0, failure_rate: 0.0, baseline_failure_rate: 0.0519, delta: -0.0519 },
  ],
  cohorts: [],
  failure_reasons: [{ reason: 'NETWORK_ERROR', failure_count: 72, failure_rate: 0.18 }],
  monetary: { currency: 'INR', total_amount_minor: 20000000, failed_amount_minor: 8700000 },
}

export const diagnosisFixture: DiagnosisView = {
  diagnosis_id: 'diag_001',
  incident_type: 'PAYMENT_METHOD_FAILURE_SPIKE',
  leading_hypothesis: 'PAYMENT_METHOD_DEGRADATION',
  confidence: 0.91,
  summary:
    'A statistically significant payment failure anomaly was detected (z=10.85). UPI failure rate spiked from 3.36% baseline to 38.24%.',
  supporting_evidence_ids: ['payment_method.UPI.failure_rate'],
  contradicting_evidence_ids: [],
  alternative_hypotheses: [
    { hypothesis: 'GENERAL_PAYMENT_FAILURE', score: 0.05, reason: 'Other methods near baseline' },
    { hypothesis: 'CUSTOMER_BEHAVIOR_CHANGE', score: 0.03, reason: 'Both cohorts affected' },
  ],
  recommended_action_type: 'CREATE_PAYMENT_LINK',
  action_rationale: 'Payment Link re-collection is the verified recovery action for failed payments.',
  uncertainties: ['Root cause of NETWORK_ERROR not definitively identified'],
  evidence: [
    {
      id: 'payment_method.UPI.failure_rate',
      kind: 'rate',
      metric: 'failure_rate',
      value: 0.3824,
      unit: 'ratio',
      baseline: 0.0336,
      current: 0.3824,
      delta: 0.3488,
      window: 'current',
      dimension: 'payment_method',
      source: 'deterministic',
    },
    {
      id: 'anomaly.payment_failure_rate',
      kind: 'anomaly',
      metric: 'payment_failure_rate',
      value: { anomaly_score: 10.854 },
      unit: null,
      baseline: 0.0454,
      current: 0.2175,
      delta: 0.1721,
      window: 'current',
      dimension: null,
      source: 'deterministic',
    },
  ],
}

export const passingPolicyFixture: PolicyView = {
  decision: 'HUMAN_APPROVAL_REQUIRED',
  policy_version: '1.0',
  reasons: ['All policy checks passed. Human approval required for financial write.'],
  action_snapshot_hash: 'sha256:abc123',
  passed: true,
  failed_checks: [],
  checks: [
    { check: 'authorization', status: 'PASS', actual: 'CREATE_PAYMENT_LINK', limit: 'CREATE_PAYMENT_LINK', message: 'Action is authorized.' },
    { check: 'eligibility', status: 'PASS', actual: 78, limit: 78, message: 'All targets are eligible.' },
    { check: 'action_integrity', status: 'PASS', actual: 'abc123', limit: null, message: 'Snapshot is immutable.' },
  ],
}

export const rejectedPolicyFixture: PolicyView = {
  decision: 'REJECTED',
  policy_version: '1.0',
  reasons: ['amount_limit: exceeds configured limit'],
  action_snapshot_hash: 'sha256:abc123',
  passed: false,
  failed_checks: ['amount_limit'],
  checks: [
    { check: 'authorization', status: 'PASS', actual: 'CREATE_PAYMENT_LINK', limit: 'CREATE_PAYMENT_LINK', message: 'Action is authorized.' },
    { check: 'amount_limit', status: 'FAIL', actual: 99999999, limit: 50000000, message: 'Recovery amount exceeds limit.' },
  ],
}

export function makeCaseView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    case_id: 'case_test',
    environment: 'demo',
    started_at: '2026-08-01T00:00:00',
    stages: [],
    timeline: [],
    symptom: symptomFixture,
    health: healthFixture,
    investigation: {
      investigation_id: 'inv_test',
      state: 'DIAGNOSIS_COMPLETE',
      anomaly_detected: true,
      anomaly_score: 10.854,
      workers: [
        {
          worker: 'payment_method',
          finding: 'UPI failure rate spiked to 0.3824 (baseline 0.0336).',
          evidence_ids: ['payment_method.UPI.failure_rate'],
          supports: ['PAYMENT_METHOD_DEGRADATION'],
          contradicts: ['GENERAL_PAYMENT_FAILURE'],
          confidence: 0.97,
          affected_methods: ['UPI'],
          max_delta: 0.3488,
        },
        {
          worker: 'temporal',
          finding: 'Spike concentrated in a 3-hour window.',
          evidence_ids: ['temporal.anomaly'],
          supports: ['TEMPORAL_SPIKE'],
          contradicts: [],
          confidence: 0.95,
          anomaly_detected: true,
        },
      ],
    },
    diagnosis: diagnosisFixture,
    prescription: {
      action_id: 'act_test',
      action_type: 'CREATE_PAYMENT_LINK',
      status: 'POLICY_EVALUATED',
      targets_count: 78,
      total_amount_minor: 8700000,
      currency: 'INR',
      rationale: 'Payment Link re-collection is the verified recovery action.',
      targets: [
        { payment_id: 'pay_1', payment_method: 'UPI', failure_reason: 'NETWORK_ERROR', amount_minor: 50000, currency: 'INR' },
      ],
    },
    policy: passingPolicyFixture,
    ...overrides,
  }
}