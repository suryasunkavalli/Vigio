import React, { useState, useEffect, useRef } from 'react'
import UploadPanel from './components/UploadPanel'
import ProgressTracker from './components/ProgressTracker'
import BriefViewer from './components/BriefViewer'
import { pollStatus, getBrief } from './services/api'
import { AnalysisStatus, CaseIntelligenceBrief } from './types/brief'

type AppState = 'idle' | 'processing' | 'complete' | 'error'

export default function App() {
  const [state, setState] = useState<AppState>('idle')
  const [caseId, setCaseId] = useState<string | null>(null)
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [brief, setBrief] = useState<CaseIntelligenceBrief | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const handleCaseStarted = (id: string) => {
    setCaseId(id)
    setState('processing')
  }

  useEffect(() => {
    if (state !== 'processing' || !caseId) return

    pollRef.current = setInterval(async () => {
      try {
        const s = await pollStatus(caseId)
        setStatus(s)

        if (s.status === 'complete') {
          stopPolling()
          const b = await getBrief(caseId)
          setBrief(b)
          setState('complete')
        } else if (s.status === 'error') {
          stopPolling()
          setState('error')
        }
      } catch (e) {
        console.error('Poll error:', e)
      }
    }, 2000)

    return stopPolling
  }, [state, caseId])

  const handleReset = () => {
    stopPolling()
    setState('idle')
    setCaseId(null)
    setStatus(null)
    setBrief(null)
  }

  return (
    <div style={styles.app}>
      {/* Left panel */}
      <div style={styles.left}>
        <UploadPanel onCaseStarted={handleCaseStarted} />
        {state !== 'idle' && (
          <button onClick={handleReset} style={styles.resetBtn}>← New case</button>
        )}
      </div>

      {/* Right panel */}
      <div style={styles.right}>
        {state === 'idle' && (
          <div style={styles.placeholder}>
            <div style={styles.placeholderIcon}>🧬</div>
            <p style={styles.placeholderText}>Upload a case report PDF to generate a Case Intelligence Brief</p>
            <p style={styles.placeholderSub}>Three-layer intelligence: Regulatory · Clinical · Population</p>
          </div>
        )}

        {state === 'processing' && status && (
          <ProgressTracker status={status} />
        )}

        {state === 'complete' && brief && (
          <BriefViewer brief={brief} onConfirmed={() => {}} />
        )}

        {state === 'error' && (
          <div style={styles.errorState}>
            <p style={styles.errorTitle}>Analysis failed</p>
            <p style={styles.errorMsg}>{status?.error || 'Unknown error'}</p>
            <button onClick={handleReset} style={styles.retryBtn}>Try again</button>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: { display: 'flex', height: '100vh', overflow: 'hidden' },
  left: {
    width: 380, flexShrink: 0,
    borderRight: '1px solid #1e293b',
    display: 'flex', flexDirection: 'column',
    overflow: 'auto', background: '#0f1117'
  },
  right: {
    flex: 1, overflow: 'auto', background: '#0f172a',
    display: 'flex', flexDirection: 'column'
  },
  resetBtn: {
    margin: '0 32px 24px', background: 'transparent', border: '1px solid #334155',
    color: '#64748b', fontSize: 13, padding: '8px 16px', borderRadius: 6, cursor: 'pointer'
  },
  placeholder: {
    flex: 1, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', gap: 12, padding: 48
  },
  placeholderIcon: { fontSize: 48, marginBottom: 8 },
  placeholderText: { fontSize: 16, fontWeight: 500, color: '#475569', textAlign: 'center', maxWidth: 380 },
  placeholderSub: { fontSize: 13, color: '#334155', textAlign: 'center' },
  errorState: {
    flex: 1, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', gap: 12, padding: 48
  },
  errorTitle: { fontSize: 18, fontWeight: 600, color: '#ef4444' },
  errorMsg: { fontSize: 14, color: '#94a3b8', textAlign: 'center', maxWidth: 400 },
  retryBtn: {
    background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155',
    borderRadius: 6, padding: '8px 20px', fontSize: 14, cursor: 'pointer', marginTop: 8
  }
}
