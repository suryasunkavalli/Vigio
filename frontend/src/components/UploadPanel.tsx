import React, { useState, useRef } from 'react'
import { uploadPDF, startAnalysis } from '../services/api'

interface Props {
  onCaseStarted: (caseId: string) => void
}

export default function UploadPanel({ onCaseStarted }: Props) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF file')
      return
    }
    setError(null)
    setUploading(true)
    try {
      const { case_id } = await uploadPDF(file)
      await startAnalysis(case_id)
      onCaseStarted(case_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.logo}>Verix</span>
        <span style={styles.tagline}>Case Intelligence Platform</span>
      </div>

      <div
        style={{ ...styles.dropzone, ...(dragging ? styles.dropzoneActive : {}) }}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept=".pdf" hidden onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
        {uploading ? (
          <div style={styles.uploadingState}>
            <div style={styles.spinner} />
            <p>Uploading and starting analysis...</p>
          </div>
        ) : (
          <>
            <div style={styles.uploadIcon}>📄</div>
            <p style={styles.dropText}>Drop case report PDF here</p>
            <p style={styles.dropSub}>or click to browse</p>
          </>
        )}
      </div>

      {error && <div style={styles.error}>{error}</div>}

      <div style={styles.info}>
        <h3 style={styles.infoTitle}>What happens next</h3>
        <div style={styles.steps}>
          {[
            ['1', 'PDF text extraction'],
            ['2', 'ICH E2A entity extraction'],
            ['3', 'Regulatory intelligence (Layer 1)'],
            ['4', 'Clinical intelligence — PubMed (Layer 2)'],
            ['5', 'Population intelligence — FAERS (Layer 3)'],
            ['6', 'Case Intelligence Brief synthesis'],
          ].map(([n, label]) => (
            <div key={n} style={styles.step}>
              <span style={styles.stepNum}>{n}</span>
              <span style={styles.stepLabel}>{label}</span>
            </div>
          ))}
        </div>
        <p style={styles.disclaimer}>
          <strong>Intelligence ≠ Determination.</strong> Verix builds the evidentiary brief.
          A human reviewer makes the regulatory determination.
        </p>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { display: 'flex', flexDirection: 'column', gap: 24, height: '100%', padding: 32 },
  header: { display: 'flex', flexDirection: 'column', gap: 4 },
  logo: { fontSize: 28, fontWeight: 700, color: '#60a5fa', letterSpacing: '-0.5px' },
  tagline: { fontSize: 13, color: '#64748b', letterSpacing: '0.5px', textTransform: 'uppercase' },
  dropzone: {
    border: '2px dashed #334155', borderRadius: 12, padding: 48,
    textAlign: 'center', cursor: 'pointer', transition: 'all 0.2s',
    background: '#1e293b',
  },
  dropzoneActive: { borderColor: '#60a5fa', background: '#1e3a5f' },
  uploadIcon: { fontSize: 40, marginBottom: 12 },
  dropText: { fontSize: 16, fontWeight: 500, color: '#e2e8f0', marginBottom: 4 },
  dropSub: { fontSize: 13, color: '#64748b' },
  uploadingState: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 },
  spinner: {
    width: 32, height: 32, border: '3px solid #334155',
    borderTop: '3px solid #60a5fa', borderRadius: '50%',
    animation: 'spin 1s linear infinite'
  },
  error: { background: '#450a0a', border: '1px solid #ef4444', borderRadius: 8, padding: '12px 16px', color: '#fca5a5', fontSize: 14 },
  info: { background: '#1e293b', borderRadius: 12, padding: 24 },
  infoTitle: { fontSize: 13, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 16 },
  steps: { display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 },
  step: { display: 'flex', alignItems: 'center', gap: 12 },
  stepNum: {
    width: 22, height: 22, borderRadius: '50%', background: '#1d4ed8',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 11, fontWeight: 700, flexShrink: 0
  },
  stepLabel: { fontSize: 13, color: '#94a3b8' },
  disclaimer: { fontSize: 12, color: '#475569', lineHeight: 1.6, borderTop: '1px solid #334155', paddingTop: 16 }
}
