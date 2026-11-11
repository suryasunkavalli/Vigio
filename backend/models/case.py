"""
Pydantic models for case entities, the three safety lenses, and the Case Intelligence Brief.

Vigio reads every ICSR through three analytical lenses (not sequential steps):
  1. Regulatory Safety  - is the case valid, serious, listed/expected and reportable?
  2. Clinical Safety    - what happened to the patient, and how plausible is a link to the product?
  3. Population Safety & Evidence Generation - combined with other data, is there a risk worth investigating?

The JSON keys `regulatory`, `clinical` and `population` are kept for API compatibility.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

from backend.config import PLATFORM_VERSION


class Seriousness(str, Enum):
    FATAL = "Fatal"
    LIFE_THREATENING = "Life-Threatening"
    HOSPITALIZATION = "Hospitalization / Prolonged Hospitalization"
    DISABILITY = "Disability / Incapacity"
    CONGENITAL_ANOMALY = "Congenital Anomaly"
    MEDICALLY_SIGNIFICANT = "Medically Significant"
    NON_SERIOUS = "Non-Serious"


class ReportingTrigger(str, Enum):
    SEVEN_DAY = "7-Day (Fatal/Life-Threatening Unexpected)"
    FIFTEEN_DAY = "15-Day (Serious Unexpected)"
    PERIODIC = "Periodic (Expected or Non-Serious)"
    NOT_APPLICABLE = "Not Applicable"


class ValidityStatus(str, Enum):
    VALID = "Valid"
    INCOMPLETE = "Incomplete"
    INVALID = "Invalid"


class Expectedness(str, Enum):
    EXPECTED = "Expected (Listed)"
    UNEXPECTED = "Unexpected (Unlisted)"
    UNKNOWN = "Unknown / Label Not Available"


class CausalityCategory(str, Enum):
    """WHO-UMC causality categories."""
    CERTAIN = "Certain"
    PROBABLE = "Probable / Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    CONDITIONAL = "Conditional / Unclassified"
    UNASSESSABLE = "Unassessable / Unclassifiable"


# --- Extracted Case Entities ---

class CaseEntities(BaseModel):
    case_id: str
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ICH E2A four elements
    patient: Optional[str] = None
    patient_age: Optional[str] = None
    patient_sex: Optional[str] = None
    reporter: Optional[str] = None
    reporter_type: Optional[str] = None  # HCP, consumer, literature, etc.
    suspect_product: Optional[str] = None
    suspect_product_dose: Optional[str] = None
    suspect_product_indication: Optional[str] = None
    adverse_event: Optional[str] = None
    adverse_event_pt: Optional[str] = None       # MedDRA preferred term for the primary event, if identifiable
    adverse_event_onset: Optional[str] = None
    adverse_event_outcome: Optional[str] = None

    # Clinical detail used by the Clinical Safety lens
    therapy_start_date: Optional[str] = None
    therapy_stop_date: Optional[str] = None
    time_to_onset: Optional[str] = None          # e.g. "21 days after first dose"
    dose_exposure: Optional[str] = None          # dose, frequency, route, duration, recent changes
    dechallenge: Optional[str] = None            # Positive / Negative / Not done / Unknown, plus detail
    rechallenge: Optional[str] = None            # Positive / Negative / Not done / Unknown, plus detail
    medical_history: List[str] = []
    concomitant_medications: List[str] = []
    relevant_tests: List[str] = []               # labs, imaging, biopsies with values where stated

    # Validity
    four_element_valid: bool = False
    missing_elements: List[str] = []

    # Raw narrative extracted from PDF
    source_narrative: str = ""


# --- Lens 1: Regulatory Safety ---

class RegulatoryIntelligence(BaseModel):
    validity_status: ValidityStatus
    four_element_check: dict  # element -> present/absent/uncertain
    seriousness: Seriousness
    seriousness_criteria_met: List[str] = []
    expectedness: Expectedness
    expectedness_basis: str = ""
    label_source: str = ""          # which reference label was used, or why none
    reportability_causality: str = ""  # "reasonable possibility" assessment used for expedited reporting
    reporting_trigger: ReportingTrigger
    reporting_trigger_rationale: str = ""
    day_zero: Optional[str] = None  # date string
    regulatory_notes: str = ""
    citations: List[str] = []  # ICH E2A, 21 CFR 312.32, etc.


# --- Lens 2: Clinical Safety ---

class PubMedReference(BaseModel):
    pmid: str
    title: str
    authors: str
    journal: str
    year: str
    relevance_summary: str
    url: str


class CausalityAssessment(BaseModel):
    method: str = "WHO-UMC"
    category: CausalityCategory = CausalityCategory.UNASSESSABLE
    rationale: str = ""
    criteria: Dict[str, str] = {}   # e.g. temporal relationship, dechallenge, alternative causes
    reviewer_must_confirm: bool = True


class ClinicalIntelligence(BaseModel):
    case_clinical_summary: str = ""
    time_to_onset_assessment: str = ""
    dose_exposure_assessment: str = ""
    dechallenge_rechallenge_assessment: str = ""
    risk_factors: List[str] = []
    alternative_causes: List[str] = []
    causality: CausalityAssessment = Field(default_factory=CausalityAssessment)
    follow_up_questions: List[str] = []

    # Literature and mechanism
    mechanistic_summary: str = ""
    pubmed_references: List[PubMedReference] = []
    label_cross_reference: str = ""
    clinical_plausibility: str = ""  # High / Moderate / Low / Unknown
    clinical_notes: str = ""


# --- Lens 3: Population Safety & Evidence Generation ---

class FAERSSignal(BaseModel):
    drug_name: str
    event_term: str
    report_count: int                       # a: reports with this drug and this event
    total_drug_reports: int                 # a + b: all reports for this drug
    event_total_reports: int = 0            # a + c: all reports for this event, any drug
    database_total_reports: int = 0         # N: all reports in FAERS
    reporting_odds_ratio: Optional[float] = None
    ror_ci_lower: Optional[float] = None
    ror_ci_upper: Optional[float] = None
    is_sdr: bool = False                    # signal of disproportionate reporting
    signal_strength: str = ""
    data_confidence: str = ""               # High / Moderate / Low, by report volume
    data_source: str = "FDA FAERS via openFDA"
    data_period: str = ""                   # e.g. "2026Q3" for the local snapshot
    match_notes: str = ""                   # how the drug and event were matched to FAERS terms
    query_timestamp: datetime = Field(default_factory=datetime.utcnow)


class SubgroupBreakdown(BaseModel):
    by_sex: Dict[str, int] = {}
    by_age_group: Dict[str, int] = {}
    outcomes: Dict[str, int] = {}
    note: str = "Counts of FAERS reports for this drug-event pair. Descriptive only; not adjusted rates."


class EvidenceGap(BaseModel):
    question: str
    why_it_matters: str = ""
    data_that_would_answer: str = ""   # e.g. claims, EHR, registry, targeted study


class PopulationIntelligence(BaseModel):
    faers_signal: Optional[FAERSSignal] = None
    subgroups: Optional[SubgroupBreakdown] = None
    background_context: str = ""
    population_notes: str = ""
    signal_summary: str = ""
    evidence_gaps: List[EvidenceGap] = []


# --- Case Intelligence Brief (the output) ---

class RecommendedAction(str, Enum):
    EXPEDITED_7DAY = "Submit 7-Day Expedited Report"
    EXPEDITED_15DAY = "Submit 15-Day Expedited Report"
    PERIODIC = "Include in Periodic Safety Report"
    FOLLOW_UP = "Obtain Follow-Up Information"
    NO_ACTION = "No Regulatory Action Required"
    REVIEW_NEEDED = "Senior Medical Review Required"


class HumanConfirmation(BaseModel):
    reviewer_name: Optional[str] = None
    reviewer_decision: Optional[str] = None
    reviewer_causality: Optional[str] = None   # reviewer's own WHO-UMC category
    reviewer_notes: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    override_reason: Optional[str] = None


class CaseIntelligenceBrief(BaseModel):
    brief_id: str
    case_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    platform_version: str = PLATFORM_VERSION

    # Extracted entities
    entities: CaseEntities

    # Three lenses
    regulatory: RegulatoryIntelligence
    clinical: ClinicalIntelligence
    population: PopulationIntelligence

    # Synthesis
    executive_summary: str = ""
    recommended_action: RecommendedAction = RecommendedAction.REVIEW_NEEDED
    recommended_action_rationale: str = ""
    key_uncertainties: List[str] = []

    # Traceability
    human_confirmation: HumanConfirmation = Field(default_factory=HumanConfirmation)
    audit_trail: List[dict] = []

    # Export
    source_pdf_filename: str = ""
    processing_duration_seconds: Optional[float] = None


# --- API request/response models ---

class AnalysisRequest(BaseModel):
    case_id: str
    filename: str


class AnalysisStatus(BaseModel):
    case_id: str
    status: str  # pending, processing, complete, error
    progress: int = 0  # 0-100
    current_step: str = ""
    error: Optional[str] = None


class ExportFormat(str, Enum):
    JSON = "json"
    PDF = "pdf"
    E2B = "e2b"  # ICH E2B(R3) XML schema stub
