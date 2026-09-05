import type { HealthView } from '../api/types'
import { formatRatio } from '../lib/format'
import { Stat } from './Stat'

// A lightweight, dependency-free SVG that explains the anomaly: the healthy
// 30-day baseline daily failure-rate distribution vs. the current window, plus
// per-method current-vs-baseline comparison. Values come straight from the
// deterministic analytics engine.

const W = 720
const H = 200
const PAD = { top: 16, right: 12, bottom: 30, left: 44 }

function BaselineChart({ health }: { health: HealthView }) {
  const days = health.baseline_daily
  if (!days.length) return null
  const max = Math.max(...days.map((d) => d.failure_rate), 0.1)
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const barW = innerW / days.length

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Baseline daily failure rate chart">
      <g className="chart__axes">
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = PAD.top + innerH - frac * innerH
          const val = max * frac
          return (
            <g key={frac}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="#e2e8f0" strokeWidth="1" />
              <text x={PAD.left - 6} y={y + 3} textAnchor="end" fontSize="9" fill="#94a3b8">
                {(val * 100).toFixed(1)}%
              </text>
            </g>
          )
        })}
      </g>
      {days.map((d, i) => {
        const h = (d.failure_rate / max) * innerH
        const x = PAD.left + i * barW
        const y = PAD.top + innerH - h
        return (
          <rect
            key={d.bucket}
            x={x + 1}
            y={y}
            width={Math.max(barW - 2, 1)}
            height={h}
            fill="#cbd5e1"
            rx="1"
          />
        )
      })}
      <text x={W / 2} y={H - 8} textAnchor="middle" fontSize="10" fill="#94a3b8">
        30-day baseline, daily failure rate
      </text>
    </svg>
  )
}

function MethodComparison({ health }: { health: HealthView }) {
  const methods = health.payment_methods
  if (!methods.length) return null
  const max = Math.max(
    ...methods.map((m) => Math.max(m.failure_rate, m.baseline_failure_rate)),
    0.1,
  )
  const innerW = W - PAD.left - PAD.right
  const groupW = innerW / methods.length
  const innerH = H - PAD.top - PAD.bottom

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Payment method failure rate comparison">
      {[0, 0.5, 1].map((frac) => {
        const y = PAD.top + innerH - frac * innerH
        const val = max * frac
        return (
          <g key={frac}>
            <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="#e2e8f0" strokeWidth="1" />
            <text x={PAD.left - 6} y={y + 3} textAnchor="end" fontSize="9" fill="#94a3b8">
              {(val * 100).toFixed(0)}%
            </text>
          </g>
        )
      })}
      {methods.map((m, i) => {
        const cx = PAD.left + i * groupW + groupW / 2
        const barW = Math.min(groupW * 0.28, 34)
        const baseH = (m.baseline_failure_rate / max) * innerH
        const curH = (m.failure_rate / max) * innerH
        const baseY = PAD.top + innerH - baseH
        const curY = PAD.top + innerH - curH
        const isAffected = m.delta > 0.1
        return (
          <g key={m.method}>
            <rect
              x={cx - barW - 2}
              y={baseY}
              width={barW}
              height={baseH}
              fill="#94a3b8"
              rx="1"
            />
            <rect
              x={cx + 2}
              y={curY}
              width={barW}
              height={curH}
              fill={isAffected ? '#dc2626' : '#0f766e'}
              rx="1"
            />
            <text x={cx} y={H - 12} textAnchor="middle" fontSize="10" fill="#475569">
              {m.method}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export function HealthChart({ health }: { health: HealthView }) {
  const summary = health.payment_methods.filter((m) => m.attempt_count > 0)
  return (
    <div className="chart">
      <div className="card__kicker" style={{ marginBottom: 4 }}>
        Baseline → current variation
      </div>
      <BaselineChart health={health} />
      <div style={{ height: 16 }} />
      <MethodComparison health={health} />
      <div className="chart__legend">
        <span>
          <span className="legendDot" style={{ background: '#94a3b8' }} />
          Baseline rate
        </span>
        <span>
          <span className="legendDot" style={{ background: '#dc2626' }} />
          Current rate (anomalous)
        </span>
        <span>
          <span className="legendDot" style={{ background: '#0f766e' }} />
          Current rate (normal)
        </span>
      </div>
      <div className="statGrid statGrid--4" style={{ marginTop: 16 }}>
        {summary.map((m) => (
          <Stat
            key={m.method}
            label={m.method}
            value={formatRatio(m.failure_rate)}
            hint={`baseline ${formatRatio(m.baseline_failure_rate)}`}
            tone={m.delta > 0.1 ? 'danger' : 'neutral'}
          />
        ))}
      </div>
    </div>
  )
}