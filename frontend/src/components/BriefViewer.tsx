import React, { useState } from 'react'
import { CaseIntelligenceBrief } from '../types/brief'
import { confirmBrief, exportUrl } from '../services/api'

interface Props {
  brief: CaseIntelligenceBrief
  onConfirmed: () => void
}

const TRIGGER_COLOR: Record<string, string> = {
  '7-Day (Fatal/Life-Threatening Unexpected)': '#dc2626',
  '15-Day (Serious Unexpected)': '#d97706',
  'Periodic (Expected or Non-Serious)': '#16a34a',
  'Not Applicable': '#64748b',
}

const ACTION_COLOR: Record<string, string> = {
  'Submit 7-Day Expedited Report': '#dc2626',
  'Submit 15-Day Expedited Report': '#d97706',
  'Include in Periodic Safety Report': '#16a34a',
  'Obtain Follow-Up Information': '#7c3aed',
  'No Regulatory Action Required': '#64748b',
  'Senior Medical Review Required': '#0284c7',
}

export default function BriefViewer({ brief, onConfirmed }: Props) {
  const [tab, setTab] = useState<'summary' | 'regulatory' | 'clinical' | 'population' | 'confirm'>('summary')
  const [reviewerName, setReviewerName] = useState('')
  const [decision, setDecision] = useState('')
  const [causality, setCausality] = useState('')
  const [notes, setNotes] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(!!brief.human_confirmation?.confirmed_at)

  const { entities: e, regulatory: r, clinical: c, population: p } = brief
  const triggerColor = TRIGGER_COLOR[r.reporting_trigger] || '#64748b'
  const actionColor = ACTION_COLOR[brief.recommended_action] || '#64748b'

  const handleConfirm = async () => {
    if (!reviewerName || !decision) return
    setConfirming(true)
    try {
      await confirmBrief(brief.case_id, reviewerName, decision, causality || undefined, notes)
      setConfirmed(true)
      onConfirmed()
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.briefHeader}>
        <div>
          <p style={styles.briefMeta}>Case Intelligence Brief · {brief.case_id.slice(0, 8).toUpperCase()}</p>
          <p style={styles.briefFile}>{brief.source_pdf_filename}</p>
        </div>
        <div style={styles.triggerBadge(triggerColor)}>
          {r.reporting_trigger}
        </div>
      </div>

      {/* Recommended action banner */}
      <div style={styles.actionBanner(actionColor)}>
        <div>
          <p style={styles.actionLabel}>AI Recommended Action</p>
          <p style={styles.actionText}>{brief.recommended_action}</p>
        </div>
        <div style={styles.actionNote}>
          Intelligence ≠ Determination<br />
          <span style={{ fontWeight: 400 }}>Human review required</span>
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {(['summary', 'regulatory', 'clinical', 'population', 'confirm'] as const).map(t => (
          <button key={t} style={{ ...styles.tab, ...(tab === t ? styles.tabActive : {}) }} onClick={() => setTab(t)}>
            {t === 'confirm' ? (confirmed ? '✓ Confirmed' : 'Confirm') : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={styles.content}>

        {tab === 'summary' && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Executive Summary</h3>
            <p style={styles.para}>{brief.executive_summary}</p>

            <h3 style={styles.sectionTitle}>ICH E2A Four Elements</h3>
            <div style={styles.grid2}>
              {[
                ['Patient', e.patient || '—'],
                ['Reporter', e.reporter ? `${e.reporter} (${e.reporter_type})` : '—'],
                ['Suspect Product', e.suspect_product || '—'],
                ['Adverse Event', e.adverse_event || '—'],
              ].map(([label, val]) => (
                <div key={label} style={styles.card}>
                  <p style={styles.cardLabel}>{label}</p>
                  <p style={styles.cardVal}>{val}</p>
                </div>
              ))}
            </div>
            <div style={{ ...styles.validBadge, background: e.four_element_valid ? '#14532d' : '#450a0a', color: e.four_element_valid ? '#86efac' : '#fca5a5' }}>
              {e.four_element_valid ? '✓ Four-element valid' : `✗ Incomplete — missing: ${e.missing_elements.join(', ')}`}
            </div>

            {brief.key_uncertainties.length > 0 && (
              <>
                <h3 style={styles.sectionTitle}>Key Uncertainties</h3>
                <ul style={styles.list}>
                  {brief.key_uncertainties.map((u, i) => <li key={i} style={styles.listItem}>{u}</li>)}
                </ul>
              </>
            )}

            <div style={styles.exportRow}>
              <a href={exportUrl(brief.case_id, 'json')} target="_blank" rel="noreferrer" style={styles.exportBtn}>Export JSON</a>
              <a href={exportUrl(brief.case_id, 'e2b')} target="_blank" rel="noreferrer" style={styles.exportBtn}>Export E2B Stub</a>
            </div>
          </div>
        )}

        {tab === 'regulatory' && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Layer 1 — Regulatory Intelligence</h3>
            <div style={styles.grid2}>
              {[
                ['Validity', r.validity_status],
                ['Seriousness', r.seriousness],
                ['Expectedness', r.expectedness],
                ['Reporting Trigger', r.reporting_trigger],
              ].map(([label, val]) => (
                <div key={label} style={styles.card}>
                  <p style={styles.cardLabel}>{label}</p>
                  <p style={styles.cardVal}>{val}</p>
                </div>
              ))}
            </div>
            {r.seriousness_criteria_met.length > 0 && (
              <><h3 style={styles.sectionTitle}>21 CFR 312.32 Criteria Met</h3>
                <ul style={styles.list}>{r.seriousness_criteria_met.map((c, i) => <li key={i} style={styles.listItem}>{c}</li>)}</ul></>
            )}
            <h3 style={styles.sectionTitle}>Reporting Trigger Rationale</h3>
            <p style={styles.para}>{r.reporting_trigger_rationale}</p>
            {r.expectedness_basis && (
              <><h3 style={styles.sectionTitle}>Expectedness Basis</h3><p style={styles.para}>{r.expectedness_basis}</p></>
            )}
            {r.day_zero && (
              <><h3 style={styles.sectionTitle}>Day Zero (ICH E2A)</h3><p style={styles.mono}>{r.day_zero}</p></>
            )}
            {r.regulatory_notes && (
              <><h3 style={styles.sectionTitle}>Regulatory Notes</h3><p style={styles.para}>{r.regulatory_notes}</p></>
            )}
            <h3 style={styles.sectionTitle}>Citations</h3>
            <ul style={styles.list}>{r.citations.map((c, i) => <li key={i} style={styles.listItem}>{c}</li>)}</ul>
          </div>
        )}

        {tab === 'clinical' && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Layer 2 — Clinical Intelligence</h3>
            <div style={styles.card}>
              <p style={styles.cardLabel}>Clinical Plausibility</p>
              <p style={styles.cardVal}>{c.clinical_plausibility || 'Unknown'}</p>
            </div>
            <h3 style={styles.sectionTitle}>Mechanistic Summary</h3>
            <p style={styles.para}>{c.mechanistic_summary}</p>
            {c.label_cross_reference && (
              <><h3 style={styles.sectionTitle}>Label Cross-Reference</h3><p style={styles.para}>{c.label_cross_reference}</p></>
            )}
            {c.pubmed_references.length > 0 && (
              <>
                <h3 style={styles.sectionTitle}>PubMed References ({c.pubmed_references.length})</h3>
                {c.pubmed_references.map(ref => (
                  <div key={ref.pmid} style={styles.refCard}>
                    <a href={ref.url} target="_blank" rel="noreferrer" style={styles.refTitle}>{ref.title}</a>
                    <p style={styles.refMeta}>{ref.authors} · {ref.journal} · {ref.year} · PMID {ref.pmid}</p>
                    <p style={styles.refNote}>{ref.relevance_summary}</p>
                  </div>
                ))}
              </>
            )}
            {c.pubmed_references.length === 0 && (
              <p style={styles.dimText}>No PubMed articles found for this drug-event pair.</p>
            )}
          </div>
        )}

        {tab === 'population' && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Layer 3 — Population Intelligence</h3>
            {p.faers_signal && (
              <div style={styles.grid2}>
                {[
                  ['Drug', p.faers_signal.drug_name],
                  ['Event', p.faers_signal.event_term],
                  ['FAERS Reports', p.faers_signal.report_count.toLocaleString()],
                  ['Signal Strength', p.faers_signal.signal_strength],
                  ['ROR', p.faers_signal.reporting_odds_ratio?.toFixed(2) || 'N/A'],
                  ['Data Source', p.faers_signal.data_source],
                ].map(([label, val]) => (
                  <div key={label} style={styles.card}>
                    <p style={styles.cardLabel}>{label}</p>
                    <p style={styles.cardVal}>{val}</p>
                  </div>
                ))}
              </div>
            )}
            <h3 style={styles.sectionTitle}>Signal Summary</h3>
            <p style={styles.para}>{p.signal_summary}</p>
            {p.background_context && (
              <><h3 style={styles.sectionTitle}>Background Context</h3><p style={styles.para}>{p.background_context}</p></>
            )}
            {p.population_notes && (
              <><h3 style={styles.sectionTitle}>Population Notes</h3><p style={styles.para}>{p.population_notes}</p></>
            )}
            <p style={styles.disclaimer}>FAERS data is voluntary and subject to reporting bias. ROR does not establish causality.</p>
          </div>
        )}

        {tab === 'confirm' && (
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Human Regulatory Determination</h3>
            <p style={styles.para}>
              The AI has built the evidentiary brief above. You, as the qualified pharmacovigilance reviewer,
              make the regulatory determination. Your decision and rationale become part of the permanent audit trail.
            </p>
            {confirmed ? (
              <div style={styles.confirmedBox}>
                <p style={styles.confirmedTitle}>✓ Determination Recorded</p>
                <p><strong>Reviewer:</strong> {brief.human_confirmation.reviewer_name}</p>
                <p><strong>Decision:</strong> {brief.human_confirmation.reviewer_decision}</p>
                {brief.human_confirmation.reviewer_notes && <p><strong>Notes:</strong> {brief.human_confirmation.reviewer_notes}</p>}
                <p style={styles.dimText}>Confirmed at: {brief.human_confirmation.confirmed_at}</p>
              </div>
            ) : (
              <div style={styles.confirmForm}>
                <label style={styles.label}>Reviewer Name *</label>
                <input style={styles.input} value={reviewerName} onChange={e => setReviewerName(e.target.value)} placeholder="Full name" />
                <label style={styles.label}>Regulatory Decision *</label>
                <select style={styles.input} value={decision} onChange={e => setDecision(e.target.value)}>
                  <option value="">Select decision...</option>
                  <option>Submit 7-Day Expedited Report</option>
                  <option>Submit 15-Day Expedited Report</option>
                  <option>Include in Periodic Safety Report</option>
                  <option>Obtain Follow-Up Information</option>
                  <option>No Regulatory Action Required</option>
                  <option>Senior Medical Review Required</option>
                </select>
                <label style={styles.label}>WHO-UMC Causality</label>
                <select style={styles.input} value={causality} onChange={e => setCausality(e.target.value)}>
                  <option value="">Not assessed</option>
                  <option>Certain</option>
                  <option>Probable / Likely</option>
                  <option>Possible</option>
                  <option>Unlikely</option>
                  <option>Conditional / Unclassified</option>
                  <option>Unassessable / Unclassifiable</option>
                </select>
                <label style={styles.label}>Notes / Rationale</label>
                <textarea style={{ ...styles.input, height: 80, resize: 'vertical' }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Any notes, overrides, or rationale for deviation from AI recommendation..." />
                <button
                  style={{ ...styles.confirmBtn, opacity: (!reviewerName || !decision || confirming) ? 0.5 : 1 }}
                  onClick={handleConfirm}
                  disabled={!reviewerName || !decision || confirming}
                >
                  {confirming ? 'Recording...' : 'Record Determination'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, unknown> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' },
  briefHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '20px 24px 0' },
  briefMeta: { fontSize: 12, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 } as React.CSSProperties,
  briefFile: { fontSize: 14, fontWeight: 500, color: '#e2e8f0' } as React.CSSProperties,
  triggerBadge: (color: string) => ({
    background: `${color}22`, border: `1px solid ${color}66`, color,
    fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 6
  }),
  actionBanner: (color: string) => ({
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    background: `${color}18`, borderLeft: `3px solid ${color}`,
    margin: '16px 24px 0', padding: '12px 16px', borderRadius: '0 8px 8px 0'
  }),
  actionLabel: { fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 } as React.CSSProperties,
  actionText: { fontSize: 15, fontWeight: 700, color: '#e2e8f0' } as React.CSSProperties,
  actionNote: { fontSize: 11, fontWeight: 600, color: '#f59e0b', textAlign: 'right', lineHeight: 1.6 } as React.CSSProperties,
  tabs: { display: 'flex', padding: '12px 24px 0', gap: 4, borderBottom: '1px solid #1e293b' },
  tab: { background: 'transparent', border: 'none', color: '#64748b', fontSize: 13, padding: '8px 14px', cursor: 'pointer', borderRadius: '6px 6px 0 0' } as React.CSSProperties,
  tabActive: { background: '#1e293b', color: '#e2e8f0', fontWeight: 600 } as React.CSSProperties,
  content: { flex: 1, overflow: 'auto', padding: 24 },
  section: { display: 'flex', flexDirection: 'column', gap: 16 } as React.CSSProperties,
  sectionTitle: { fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: 8 } as React.CSSProperties,
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 } as React.CSSProperties,
  card: { background: '#1e293b', borderRadius: 8, padding: '10px 14px' } as React.CSSProperties,
  cardLabel: { fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 4 } as React.CSSProperties,
  cardVal: { fontSize: 14, fontWeight: 500, color: '#e2e8f0' } as React.CSSProperties,
  validBadge: { padding: '8px 12px', borderRadius: 6, fontSize: 13, fontWeight: 500 } as React.CSSProperties,
  para: { fontSize: 14, color: '#94a3b8', lineHeight: 1.7 } as React.CSSProperties,
  mono: { fontSize: 13, fontFamily: 'monospace', color: '#94a3b8' } as React.CSSProperties,
  list: { paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6 } as React.CSSProperties,
  listItem: { fontSize: 13, color: '#94a3b8', lineHeight: 1.6 } as React.CSSProperties,
  dimText: { fontSize: 12, color: '#475569' } as React.CSSProperties,
  exportRow: { display: 'flex', gap: 8, marginTop: 8 } as React.CSSProperties,
  exportBtn: { background: '#1e293b', color: '#60a5fa', border: '1px solid #334155', borderRadius: 6, padding: '6px 14px', fontSize: 13, textDecoration: 'none', cursor: 'pointer' } as React.CSSProperties,
  refCard: { background: '#1e293b', borderRadius: 8, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 4 } as React.CSSProperties,
  refTitle: { fontSize: 13, fontWeight: 500, color: '#60a5fa', textDecoration: 'none', lineHeight: 1.4 } as React.CSSProperties,
  refMeta: { fontSize: 11, color: '#64748b' } as React.CSSProperties,
  refNote: { fontSize: 12, color: '#94a3b8', lineHeight: 1.5 } as React.CSSProperties,
  disclaimer: { fontSize: 11, color: '#475569', fontStyle: 'italic' } as React.CSSProperties,
  confirmedBox: { background: '#14532d22', border: '1px solid #14532d', borderRadius: 8, padding: 20, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14, color: '#94a3b8' } as React.CSSProperties,
  confirmedTitle: { fontSize: 16, fontWeight: 700, color: '#86efac', marginBottom: 8 } as React.CSSProperties,
  confirmForm: { display: 'flex', flexDirection: 'column', gap: 12 } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 600, color: '#94a3b8' } as React.CSSProperties,
  input: { background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 14, outline: 'none' } as React.CSSProperties,
  confirmBtn: { background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer', marginTop: 8 } as React.CSSProperties,
}
