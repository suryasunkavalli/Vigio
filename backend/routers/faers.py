"""
FAERS search API, backed by the local deduplicated snapshot (data/faers.db).

GET /api/faers/status                 which snapshot is loaded
GET /api/faers/drugs?q=               drug autocomplete (ingredients and product names)
GET /api/faers/events?q=&drug=        MedDRA PT autocomplete, optionally for one drug
GET /api/faers/drug?drug=             safety profile of a drug (events with ROR, 95% CI, signal flags)
GET /api/faers/pair?drug=&event=      one drug-event combination with breakdowns
GET /api/faers/top-events?drug=       most reported events for a drug
"""

from fastapi import APIRouter, HTTPException, Query
from backend.services import faers_local

router = APIRouter(prefix="/faers", tags=["faers"])


def _require_db():
    if not faers_local.available():
        raise HTTPException(503, f"No local FAERS snapshot at {faers_local.db_path()}. Build it with tools/build_faers_db.py.")


@router.get("/status")
def status():
    if not faers_local.available():
        return {"local_snapshot": False, "fallback": "openFDA (live)", "expected_path": str(faers_local.db_path())}
    return {"local_snapshot": True, **faers_local.meta()}


@router.get("/drugs")
def drugs(q: str = Query(..., min_length=2), limit: int = Query(10, le=50)):
    _require_db()
    return {"query": q, "results": faers_local.search_drugs(q, limit)}


@router.get("/events")
def events(q: str = Query(..., min_length=2), drug: str | None = None, limit: int = Query(10, le=50)):
    _require_db()
    ingredient = faers_local.match_drug(drug)[0] if drug else None
    return {"query": q, "drug": ingredient, "results": faers_local.search_events(q, ingredient, limit)}


@router.get("/drug")
def drug(drug: str, sort: str = Query("reports", pattern="^(reports|ror)$"), signals_only: bool = False,
         min_reports: int = Query(1, ge=1), limit: int = Query(50, le=500)):
    _require_db()
    return faers_local.drug_profile(drug, sort, signals_only, min_reports, limit)


@router.get("/pair")
def pair(drug: str, event: str):
    _require_db()
    return faers_local.pair_detail(drug, event)


@router.get("/top-events")
def top_events(drug: str, limit: int = Query(10, le=100)):
    _require_db()
    return {"drug": drug, "events": faers_local.top_events_for(drug, limit)}
