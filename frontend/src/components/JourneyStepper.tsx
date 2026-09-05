import type { StageView } from '../api/types'

const STAGE_META: Record<string, { num: number; label: string }> = {
  symptom: { num: 1, label: 'Symptom' },
  investigation: { num: 2, label: 'Investigation' },
  diagnosis: { num: 3, label: 'Diagnosis' },
  prescription: { num: 4, label: 'Prescription' },
  safety_check: { num: 5, label: 'Safety check' },
  approval: { num: 6, label: 'Approval' },
  treatment: { num: 7, label: 'Treatment' },
  outcome: { num: 8, label: 'Outcome' },
}

export function JourneyStepper({ stages }: { stages: StageView[] }) {
  return (
    <nav className="stepper" aria-label="Case journey">
      <h3 className="stepper__title">Case journey</h3>
      <ol className="stepper__list">
        {stages.map((stage) => {
          const meta = STAGE_META[stage.key] ?? { num: 0, label: stage.label }
          const cls =
            stage.active
              ? 'stepper__item stepper__item--active'
              : stage.complete
                ? 'stepper__item stepper__item--done'
                : 'stepper__item'
          const state = stage.active ? 'Active' : stage.complete ? 'Done' : 'Pending'
          return (
            <li key={stage.key} className={cls} title={stage.status ?? 'Not started'}>
              <span className="stepper__node" aria-hidden="true">
                {stage.complete ? '✓' : meta.num || '·'}
              </span>
              <span>
                {meta.num}. {meta.label}
              </span>
              <span className="stepper__status">{state}</span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}