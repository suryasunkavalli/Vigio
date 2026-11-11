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
  adverse_event_pt: string | null;
  adverse_event_onset: string | null;
  adverse_event_outcome: string | null;
  therapy_start_date: string | null;
  therapy_stop_date: string | null;
  time_to_onset: string | null;
  dose_exposure: string | null;
  dechallenge: string | null;
  rechallenge: string | null;
  medical_history: string[];
  concomitant_medications: string[];
  relevant_tests: string[];
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
  label_source: string;
  reportability_causality: string;
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
  case_clinical_summary: string;
  time_to_onset_assessment: string;
  dose_exposure_assessment: string;
  dechallenge_rechallenge_assessment: string;
  risk_factors: string[];
  alternative_causes: string[];
  causality: {
    method: string;
    category: string;
    rationale: string;
    criteria: Record<string, string>;
    reviewer_must_confirm: boolean;
  };
  follow_up_questions: string[];
  mechanistic_summary: string;
  pubmed_references: PubMedReference[];
  label_cross_reference: string;
  clinical_plausibility: string;
  clinical_notes: string;
}

export interface FAERSSignal {
  drug_name: string;
  event_term: string;
  report_count: number;
  total_drug_reports: number;
  event_total_reports: number;
  database_total_reports: number;
  reporting_odds_ratio: number | null;
  ror_ci_lower: number | null;
  ror_ci_upper: number | null;
  is_sdr: boolean;
  signal_strength: string;
  data_confidence: string;
  data_source: string;
  data_period: string;
  match_notes: string;
}

export interface PopulationIntelligence {
  faers_signal: FAERSSignal | null;
  subgroups: {
    by_sex: Record<string, number>;
    by_age_group: Record<string, number>;
    outcomes: Record<string, number>;
    note: string;
  } | null;
  background_context: string;
  population_notes: string;
  signal_summary: string;
  evidence_gaps: Array<{
    question: string;
    why_it_matters: string;
    data_that_would_answer: string;
  }>;
}

export interface HumanConfirmation {
  reviewer_name: string | null;
  reviewer_decision: string | null;
  reviewer_causality: string | null;
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
