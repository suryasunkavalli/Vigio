import axios from 'axios'
import { CaseIntelligenceBrief, AnalysisStatus } from '../types/brief'

const api = axios.create({ baseURL: '/api' })

export async function uploadPDF(file: File): Promise<{ case_id: string; filename: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/upload', form)
  return res.data
}

export async function startAnalysis(caseId: string): Promise<void> {
  await api.post(`/analyze?case_id=${caseId}`)
}

export async function pollStatus(caseId: string): Promise<AnalysisStatus> {
  const res = await api.get(`/status/${caseId}`)
  return res.data
}

export async function getBrief(caseId: string): Promise<CaseIntelligenceBrief> {
  const res = await api.get(`/brief/${caseId}`)
  return res.data
}

export async function confirmBrief(
  caseId: string,
  reviewerName: string,
  reviewerDecision: string,
  reviewerCausality?: string,
  reviewerNotes?: string
): Promise<void> {
  await api.post(`/confirm/${caseId}`, null, {
    params: {
      reviewer_name: reviewerName,
      reviewer_decision: reviewerDecision,
      reviewer_causality: reviewerCausality,
      reviewer_notes: reviewerNotes,
    }
  })
}

export function exportUrl(caseId: string, format: 'json' | 'e2b'): string {
  return `/api/export/${caseId}?format=${format}`
}
