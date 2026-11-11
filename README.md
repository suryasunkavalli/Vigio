# Vigio MVP — Case Intelligence Platform

Upload an Individual Case Safety Report (ICSR) PDF and get a Case Intelligence Brief that reads
the case through three analytical lenses. The lenses are not sequential steps; each asks a
different question of the same case.

| Lens | Question | MVP capabilities |
|------|----------|------------------|
| 1. Regulatory Safety | Is the case valid, serious, listed/expected and reportable? | ICH E2A validity, seriousness, listedness against a loaded reference label, reasonable-possibility assessment, IND (21 CFR 312.32) vs postmarketing (21 CFR 314.80 / 600.80) trigger, Day 0 |
| 2. Clinical Safety | What happened to the patient, and how plausible is a link to the product? | Case-level clinical summary, time to onset, dose/exposure, dechallenge/rechallenge, risk factors, alternative causes, proposed WHO-UMC causality, follow-up questions, PubMed literature |
| 3. Population Safety & Evidence Generation | Combined with other data, is there a risk worth investigating? | FAERS disproportionality (ROR with 95% CI from real openFDA counts), subgroup counts by sex and age group, evidence gaps and the data that would close them |

> **Intelligence ≠ Determination.** Vigio builds the evidence. A qualified reviewer makes the
> regulatory determination and confirms or changes the proposed causality; both are recorded
> in the audit trail.

---

## Quick start

```bash
cp .env.example .env        # add ANTHROPIC_API_KEY and ANTHROPIC_MODEL
pip install -r requirements.txt
python -m backend.main      # http://localhost:8000
open http://localhost:8000/ui
```

`frontend/standalone.html` is a single self-contained page (React via CDN, no build step). It
also contains three fictional demo cases that work without the backend. **Demo FAERS figures
are placeholders**; uploaded cases use live openFDA queries.

---

## Architecture

```
vigio-mvp/
├── backend/
│   ├── main.py                          # FastAPI app
│   ├── config.py                        # platform version and SDR thresholds
│   ├── labels/                          # reference labels for listedness (see labels/README.md)
│   ├── models/case.py                   # Pydantic models: entities, three lenses, brief
│   ├── routers/cases.py                 # /upload /analyze /status /brief /confirm /export
│   └── services/
│       ├── anthropic_service.py         # model config, API calls and validated JSON parsing
│       ├── pdf_parser.py                # PyMuPDF text extraction
│       ├── entity_extractor.py          # ICH E2A elements + clinical detail (Claude)
│       ├── regulatory_intelligence.py   # Lens 1: Regulatory Safety (Claude + label store)
│       ├── clinical_intelligence.py     # Lens 2: Clinical Safety (Claude + PubMed)
│       ├── population_intelligence.py   # Lens 3: Population Safety & Evidence (FAERS snapshot/openFDA + Claude)
│       ├── faers_local.py               # local FAERS lookup and term matching
│       ├── faers_normalize.py           # shared drug/event name normalization
│       └── brief_synthesizer.py         # Combines the lenses into the brief
├── frontend/standalone.html             # Upload UI + demo cases
├── data/faers.db                        # local FAERS snapshot (2026Q3)
├── tools/build_faers_db.py              # builds the snapshot from FDA quarterly files
└── tools/export_search_extract.py       # embeds a search extract in standalone.html for the demo
```

Pipeline: PDF → entity extraction → Regulatory and Clinical lenses (run concurrently) →
Population lens (uses the clinical findings to frame evidence gaps) → brief synthesis →
human confirmation.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload PDF, returns `case_id` |
| `POST` | `/api/analyze?case_id=` | Start the pipeline |
| `GET`  | `/api/status/{case_id}` | Poll progress (0–100%) |
| `GET`  | `/api/brief/{case_id}` | Retrieve the brief |
| `POST` | `/api/confirm/{case_id}?reviewer_name=&reviewer_decision=&reviewer_causality=&reviewer_notes=` | Record the reviewer's determination and causality |
| `GET`  | `/api/export/{case_id}?format=json\|e2b` | Export |
| `POST` | `/api/anthropic/check` | Verify the configured Anthropic key and model |
| `GET`  | `/api/faers/status` | Local FAERS snapshot status |
| `GET`  | `/api/faers/drugs?q=` | Drug autocomplete |
| `GET`  | `/api/faers/drug?drug=` | Drug safety profile and ROR results |
| `GET`  | `/api/faers/pair?drug=&event=` | Drug-event details and breakdowns |
| `GET`  | `/health` | Health check |

---

## Disproportionality method (Lens 3)

From openFDA: `a` = reports with the drug and the event, drug total, event total and the
database total. Then `b = drug total − a`, `c = event total − a`, `d = N − a − b − c`,
`ROR = (a/b)/(c/d)`, 95% CI = `exp(ln ROR ± 1.96·√(1/a+1/b+1/c+1/d))`.

A signal of disproportionate reporting (SDR) is flagged when `a ≥ 3` and the CI lower bound
is above 1. Strength: Strong at ROR ≥ 5, Moderate 2–5, Weak below 2. Data confidence by
report count: High ≥ 100, Moderate 20–99, Low < 20. All thresholds live in `backend/config.py`
and are heuristics to be validated.

FAERS is voluntary and has no exposure denominator; disproportionality is not incidence or
causality.

---

## Local FAERS snapshot (Population lens)

The Population lens reads FAERS counts from a local SQLite database first and falls back to live
openFDA only if the database is missing or the drug isn't in it.

- `data/faers.db`: built from the FDA quarterly ASCII extract **2026Q3** (421,401 deduplicated reports).
  See `data/FAERS_SNAPSHOT_REPORT.md` for contents and checks.
- `tools/build_faers_db.py`: rebuilds it. Add more quarters for more stable counts:

```bash
python tools/build_faers_db.py --out data/faers.db faers_ascii_2026q3.zip faers_ascii_2026q2.zip ...
```

Processing: latest case version per case ID, FDA-deleted cases removed, drugs matched on active
ingredient with salts stripped and combinations split, suspect drugs only (PS/SS), events as
MedDRA preferred terms. Free-text drug and event names from uploaded cases are matched to the
snapshot (product names such as "Keytruda" map to their ingredient; US spellings map to MedDRA
spellings; compound descriptions match on the primary event). The match is shown in the brief.

Set `FAERS_DB_PATH` to use a database elsewhere. Endpoints are listed in `backend/routers/faers.py`.


### Drug Safety Search

The UI has a **Drug Safety Search** view: type a drug or brand name and see every event reported
with it as a suspect drug, with report counts, ROR (95% CI), signal classification and data
confidence; sort by most reported or strongest signal, filter to signals only, and open any
drug–event pair for sex, age and outcome breakdowns.

- **With the backend running** it queries the full database through `/api/faers/drugs`,
  `/api/faers/events`, `/api/faers/drug` and `/api/faers/pair` (every drug, all breakdowns).
- **Without a backend** (the published demo page) it uses a compact extract embedded in
  `standalone.html`: the top 1,000 suspect ingredients, each with its 25 most reported events and
  up to 25 strongest signals. Regenerate it after rebuilding the database:

```bash
python tools/export_search_extract.py      # options: --drugs 1000 --top 25 --signals 25
```

---

## Changes in 0.2

- Restructured around the three lenses; new fields for clinical review, causality,
  follow-up questions, evidence gaps and subgroups
- Listedness is only assessed against a loaded label, never from model memory
- Correct IND vs postmarketing reporting logic
- **Fixed ROR**: previously used hardcoded event and database totals; now uses real
  openFDA counts and reports a 95% CI
- Regulatory and Clinical lenses run concurrently
- Model name set once (`ANTHROPIC_MODEL`); robust, validated JSON parsing of model output
- Demo cases rewritten: fictional cases, real literature references (linked by PubMed
  search), FAERS figures clearly marked as placeholders

## Limitations

- In-memory storage only (cases lost on restart)
- PDF must have a text layer (no OCR yet)
- Event terms are free text from extraction; MedDRA coding is not enforced, which affects
  FAERS matching
- Single-case analysis only: aggregate analysis of a customer's ICSRs, signal evaluation,
  observed-vs-expected and real-world evidence are on the roadmap
- E2B export is a stub, not submission-ready
- Not validated for GxP use

Proprietary — Vigio AI. Not for distribution.
