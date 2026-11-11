"""Pydantic models for case entities, intelligence layers, and the Case Intelligence Brief."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


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
    adverse_event_onset: Optional[str] = None
    adverse_event_outcome: Optional[str] = None

    # Validity
    four_element_valid: bool = False
    missing_elements: List[str] = []

    # Raw narrative extracted from PDF
    source_narrative: str = ""


# --- Layer 1: Regulatory Intelligence ---

class RegulatoryIntelligence(BaseModel):
    validity_status: ValidityStatus
    four_element_check: dict  # element -> present/absent/uncertain
    seriousness: Seriousness
    seriousness_criteria_met: List[str] = []
    expectedness: Expectedness
    expectedness_basis: str = ""
    reporting_trigger: ReportingTrigger
    reporting_trigger_rationale: str = ""
    day_zero: Optional[str] = None  # date string
    regulatory_notes: str = ""
    citations: List[str] = []  # ICH E2A, 21 CFR 312.32, etc.


# --- Layer 2: Clinical Intelligence ---

class PubMedReference(BaseModel):
    pmid: str
    title: str
    authors: str
    journal: str
    year: str
    relevance_summary: str
    url: str


class ClinicalIntelligence(BaseModel):
    mechanistic_summary: str = ""
    pubmed_references: List[PubMedReference] = []
    label_cross_reference: str = ""
    clinical_plausibility: str = ""  # High / Moderate / Low / Unknown
    clinical_notes: str = ""


# --- Layer 3: Population Intelligence ---

class FAERSSignal(BaseModel):
    drug_name: str
    event_term: str
    report_count: int
    total_drug_reports: int
    reporting_odds_ratio: Optional[float] = None
    signal_strength: str = ""  # Strong / Moderate / Weak / Insufficient data
    data_source: str = "FDA FAERS / OpenFDA"
    query_timestamp: datetime = Field(default_factory=datetime.utcnow)


class PopulationIntelligence(BaseModel):
    faers_signal: Optional[FAERSSignal] = None
    background_context: str = ""
    population_notes: str = ""
    signal_summary: str = ""


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
    reviewer_notes: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    override_reason: Optional[str] = None


class CaseIntelligenceBrief(BaseModel):
    brief_id: str
    case_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    platform_version: str = "Verix MVP 0.1"

    # Extracted entities
    entities: CaseEntities

    # Three layers
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
