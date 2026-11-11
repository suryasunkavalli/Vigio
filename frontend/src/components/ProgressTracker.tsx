import React from 'react'
import { AnalysisStatus } from '../types/brief'

interface Props {
  status: AnalysisStatus
}

export default function ProgressTracker({ status }: Props) {
  const pct = status.progress

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.label}>Analyzing case...</span>
        <span style={styles.pct}>{pct}%</span>
      </div>
      <div style={styles.bar}>
        <div style={{ ...styles.fill, width: `${pct}%` }} />
      </div>
      <p style={styles.step}>{status.current_step}</p>

      {status.status === 'error' && (
        <div style={styles.error}>
          <strong>Analysis failed</strong><br />
          {status.error}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { padding: 32, display: 'flex', flexDirection: 'column', gap: 16 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  label: { fontSize: 14, fontWeight: 600, color: '#e2e8f0' },
  pct: { fontSize: 14, fontWeight: 700, color: '#60a5fa' },
  bar: { height: 6, background: '#1e293b', borderRadius: 3, overflow: 'hidden' },
  fill: { height: '100%', background: 'linear-gradient(90deg, #1d4ed8, #60a5fa)', borderRadius: 3, transition: 'width 0.4s ease' },
  step: { fontSize: 13, color: '#64748b' },
  error: { background: '#450a0a', border: '1px solid #ef4444', borderRadius: 8, padding: 16, color: '#fca5a5', fontSize: 13 }
}
