"""
Cases Router — API endpoints for case processing.

POST /api/upload       — upload a PDF, get a case_id
POST /api/analyze      — run all three intelligence layers
GET  /api/brief/{id}   — retrieve the Case Intelligence Brief
POST /api/confirm/{id} — submit human reviewer confirmation
GET  /api/export/{id}  — export brief as JSON or E2B stub
"""

import os
import time
import json
import logging
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from anthropic import Anthropic

from backend.models.case import (
    CaseIntelligenceBrief, AnalysisStatus, HumanConfirmation
)
from backend.services.pdf_parser import extract_and_clean
from backend.services.entity_extractor import extract_entities
from backend.services.regulatory_intelligence import assess_regulatory_intelligence
from backend.services.clinical_intelligence import assess_clinical_intelligence
from backend.services.population_intelligence import assess_population_intelligence
from backend.services.brief_synthesizer import synthesize_brief

router = APIRouter()
logger = logging.getLogger("verix.cases")

# In-memory store for MVP (replace with DB in production)
_briefs: dict[str, CaseIntelligenceBrief] = {}
_status: dict[str, AnalysisStatus] = {}

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def get_anthropic_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return Anthropic(api_key=api_key)


# ─── Upload ─────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_case_pdf(file: UploadFile = File(...)):
    """Accept a PDF and return a case_id to track analysis."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    case_id = str(uuid4())
    dest = UPLOAD_DIR / f"{case_id}.pdf"

    contents = await file.read()
    with open(dest, "wb") as f:
        f.write(contents)

    _status[case_id] = AnalysisStatus(
        case_id=case_id,
        status="uploaded",
        progress=0,
        current_step="PDF received — ready for analysis"
    )

    logger.info(f"Uploaded {file.filename} → case {case_id}")

    return {
        "case_id": case_id,
        "filename": file.filename,
        "message": "PDF uploaded. Call POST /api/analyze to begin intelligence extraction."
    }


# ─── Analyze ────────────────────────────────────────────────────────────────

def _run_analysis(case_id: str, filename: str):
    """Background task: run all three layers and synthesize brief."""
    start = time.time()
    pdf_path = str(UPLOAD_DIR / f"{case_id}.pdf")
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def update(step: str, pct: int):
        _status[case_id] = AnalysisStatus(
            case_id=case_id, status="processing", progress=pct, current_step=step
        )
        logger.info(f"[{case_id}] {pct}% — {step}")

    try:
        # Step 1: PDF extraction
        update("Extracting text from PDF", 10)
        narrative = extract_and_clean(pdf_path)

        # Step 2: Entity extraction
        update("Extracting ICH E2A entities", 25)
        entities = extract_entities(narrative, case_id, client)

        # Step 3: Regulatory intelligence (Layer 1)
        update("Running Regulatory Intelligence (Layer 1)", 45)
        regulatory = assess_regulatory_intelligence(entities, narrative, client)

        # Step 4: Clinical intelligence (Layer 2)
        update("Running Clinical Intelligence — PubMed search (Layer 2)", 65)
        clinical = assess_clinical_intelligence(entities, client)

        # Step 5: Population intelligence (Layer 3)
        update("Running Population Intelligence — FAERS query (Layer 3)", 80)
        population = assess_population_intelligence(entities, client)

        # Step 6: Synthesize brief
        update("Synthesizing Case Intelligence Brief", 92)
        duration = time.time() - start
        brief = synthesize_brief(
            entities, regulatory, clinical, population, client,
            source_filename=filename,
            processing_duration=duration
        )

        _briefs[case_id] = brief
        _status[case_id] = AnalysisStatus(
            case_id=case_id,
            status="complete",
            progress=100,
            current_step="Case Intelligence Brief ready"
        )
        logger.info(f"[{case_id}] Complete in {duration:.1f}s — trigger: {regulatory.reporting_trigger}")

    except Exception as e:
        logger.error(f"[{case_id}] Analysis failed: {e}", exc_info=True)
        _status[case_id] = AnalysisStatus(
            case_id=case_id,
            status="error",
            progress=0,
            current_step="Analysis failed",
            error=str(e)
        )


@router.post("/analyze")
async def analyze_case(case_id: str, background_tasks: BackgroundTasks):
    """Start the three-layer intelligence analysis pipeline."""
    pdf_path = UPLOAD_DIR / f"{case_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"No PDF found for case_id {case_id}")

    if case_id in _status and _status[case_id].status == "processing":
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    # Get original filename from status if available
    filename = _status.get(case_id, AnalysisStatus(case_id=case_id, status="", current_step="")).current_step
    filename = pdf_path.name  # use stored name as fallback

    background_tasks.add_task(_run_analysis, case_id, pdf_path.name)

    return {
        "case_id": case_id,
        "status": "processing",
        "message": "Analysis started. Poll GET /api/status/{case_id} for progress."
    }


# ─── Status ─────────────────────────────────────────────────────────────────

@router.get("/status/{case_id}")
def get_status(case_id: str):
    """Poll analysis progress."""
    if case_id not in _status:
        raise HTTPException(status_code=404, detail="Case not found")
    return _status[case_id]


# ─── Brief ──────────────────────────────────────────────────────────────────

@router.get("/brief/{case_id}")
def get_brief(case_id: str):
    """Retrieve the completed Case Intelligence Brief."""
    if case_id not in _briefs:
        status = _status.get(case_id)
        if status and status.status == "processing":
            raise HTTPException(status_code=202, detail="Analysis still in progress")
        raise HTTPException(status_code=404, detail="Brief not found")
    return _briefs[case_id]


# ─── Human Confirmation ─────────────────────────────────────────────────────

@router.post("/confirm/{case_id}")
def confirm_brief(
    case_id: str,
    reviewer_name: str,
    reviewer_decision: str,
    reviewer_notes: Optional[str] = None,
    override_reason: Optional[str] = None
):
    """
    Submit human reviewer confirmation — the regulatory determination step.
    AI builds the brief; human makes the determination.
    """
    if case_id not in _briefs:
        raise HTTPException(status_code=404, detail="Brief not found")

    brief = _briefs[case_id]
    brief.human_confirmation = HumanConfirmation(
        reviewer_name=reviewer_name,
        reviewer_decision=reviewer_decision,
        reviewer_notes=reviewer_notes,
        confirmed_at=datetime.utcnow(),
        override_reason=override_reason
    )

    # Append to audit trail
    brief.audit_trail.append({
        "event": "human_confirmation",
        "timestamp": datetime.utcnow().isoformat(),
        "reviewer": reviewer_name,
        "decision": reviewer_decision,
        "notes": reviewer_notes,
        "override": override_reason is not None
    })

    _briefs[case_id] = brief
    logger.info(f"[{case_id}] Confirmed by {reviewer_name}: {reviewer_decision}")

    return {
        "case_id": case_id,
        "status": "confirmed",
        "reviewer": reviewer_name,
        "decision": reviewer_decision
    }


# ─── Export ─────────────────────────────────────────────────────────────────

@router.get("/export/{case_id}")
def export_brief(case_id: str, format: str = "json"):
    """Export the Case Intelligence Brief in JSON or E2B stub format."""
    if case_id not in _briefs:
        raise HTTPException(status_code=404, detail="Brief not found")

    brief = _briefs[case_id]

    if format == "json":
        return JSONResponse(
            content=brief.model_dump(mode="json"),
            headers={"Content-Disposition": f"attachment; filename=verix_brief_{case_id}.json"}
        )

    elif format == "e2b":
        # ICH E2B(R3) XML stub — minimal structure for integration teams
        e = brief.entities
        r = brief.regulatory
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Verix MVP — ICH E2B(R3) Export Stub -->
<!-- Case ID: {case_id} | Generated: {brief.generated_at.isoformat()} -->
<ichicsr lang="en">
  <ichicsrmessageheader>
    <messagetype>ichicsr</messagetype>
    <messageformatversion>2.1</messageformatversion>
    <messagedatecreated>{brief.generated_at.strftime("%Y%m%d%H%M%S")}</messagedatecreated>
  </ichicsrmessageheader>
  <safetyreport>
    <safetyreportid>{case_id}</safetyreportid>
    <primarysourcecountry/>
    <receivedate>{r.day_zero or ""}</receivedate>
    <serious>{1 if r.seriousness.value != "Non-Serious" else 2}</serious>
    <seriousnessdeath>{1 if r.seriousness.value == "Fatal" else 2}</seriousnessdeath>
    <seriousnesslifethreatening>{1 if r.seriousness.value == "Life-Threatening" else 2}</seriousnesslifethreatening>
    <seriousnesshospitalization>{1 if "Hospitalization" in r.seriousness.value else 2}</seriousnesshospitalization>
    <seriousnessdisabling>{1 if "Disability" in r.seriousness.value else 2}</seriousnessdisabling>
    <seriousnesscongenitalanomali>{1 if "Congenital" in r.seriousness.value else 2}</seriousnesscongenitalanomali>
    <seriousnessother>{1 if r.seriousness.value == "Medically Significant" else 2}</seriousnessother>
    <patient>
      <patientsex>{1 if (e.patient_sex or "").lower() == "male" else 2 if (e.patient_sex or "").lower() == "female" else 0}</patientsex>
      <patientonsetage>{e.patient_age or ""}</patientonsetage>
      <reaction>
        <primarysourcereaction>{e.adverse_event or ""}</primarysourcereaction>
        <reactionoutcome/>
      </reaction>
      <drug>
        <drugcharacterization>1</drugcharacterization>
        <medicinalproduct>{e.suspect_product or ""}</medicinalproduct>
        <drugdosagetext>{e.suspect_product_dose or ""}</drugdosagetext>
        <drugindication>{e.suspect_product_indication or ""}</drugindication>
      </drug>
    </patient>
    <!-- Verix AI recommended action: {brief.recommended_action.value} -->
    <!-- Human reviewer: {brief.human_confirmation.reviewer_name or "PENDING"} -->
    <!-- Human decision: {brief.human_confirmation.reviewer_decision or "PENDING"} -->
  </safetyreport>
</ichicsr>"""

        return JSONResponse(
            content={"xml": xml, "note": "ICH E2B(R3) stub — review before submission to regulatory systems"},
            headers={"Content-Disposition": f"attachment; filename=verix_e2b_{case_id}.json"}
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}. Use 'json' or 'e2b'")
