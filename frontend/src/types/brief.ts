export interface CaseEntities {
  case_id: string;
  patient: string | null;
  patient_age: string | null;
  patient_sex: string | null;
  reporter: string | null;
  reporter_type: string | null;
  suspect_product: string | null;
  suspect_product_dose: string | null;
  suspect_product_indication: string | null;
  adverse_event: string | null;
  adverse_event_onset: string | null;
  adverse_event_outcome: string | null;
  four_element_valid: boolean;
  missing_elements: string[];
}

export interface RegulatoryIntelligence {
  validity_status: string;
  four_element_check: Record<string, string>;
  seriousness: string;
  seriousness_criteria_met: string[];
  expectedness: string;
  expectedness_basis: string;
  reporting_trigger: string;
  reporting_trigger_rationale: string;
  day_zero: string | null;
  regulatory_notes: string;
  citations: string[];
}

export interface PubMedReference {
  pmid: string;
  title: string;
  authors: string;
  journal: string;
  year: string;
  relevance_summary: string;
  url: string;
}

export interface ClinicalIntelligence {
  mechanistic_summary: string;
  pubmed_references: PubMedReference[];
  label_cross_reference: string;
  clinical_plausibility: string;
  clinical_notes: string;
}

export interface FAERSSignal {
  drug_name: string;
  event_term: string;
  report_count: number | null;
  total_drug_reports: number | null;
  reporting_odds_ratio: number | null;
  signal_strength: string;
  query_status: 'success' | 'no_results' | 'partial' | 'unavailable';
  query_note: string;
  data_source: string;
}

export interface PopulationIntelligence {
  faers_signal: FAERSSignal | null;
  background_context: string;
  population_notes: string;
  signal_summary: string;
}

export interface HumanConfirmation {
  reviewer_name: string | null;
  reviewer_decision: string | null;
  reviewer_notes: string | null;
  confirmed_at: string | null;
  override_reason: string | null;
}

export interface CaseIntelligenceBrief {
  brief_id: string;
  case_id: string;
  generated_at: string;
  platform_version: string;
  entities: CaseEntities;
  regulatory: RegulatoryIntelligence;
  clinical: ClinicalIntelligence;
  population: PopulationIntelligence;
  executive_summary: string;
  recommended_action: string;
  recommended_action_rationale: string;
  key_uncertainties: string[];
  human_confirmation: HumanConfirmation;
  audit_trail: Record<string, unknown>[];
  source_pdf_filename: string;
  processing_duration_seconds: number | null;
}

export interface AnalysisStatus {
  case_id: string;
  status: 'uploaded' | 'processing' | 'complete' | 'error';
  progress: number;
  current_step: string;
  error?: string;
}
