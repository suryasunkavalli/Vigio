# Vigio MVP — Case Intelligence Platform

Three-layer pharmacovigilance AI. Upload a case report PDF, get a structured Case Intelligence Brief.

---

## What it does

1. **PDF extraction** — pull narrative text from any digital case report PDF
2. **ICH E2A entity extraction** — patient, reporter, suspect product, adverse event
3. **Layer 1: Regulatory Intelligence** — validity, seriousness (21 CFR 312.32), 7/15-day trigger, expectedness
4. **Layer 2: Clinical Intelligence** — PubMed mechanistic literature with PMID citations
5. **Layer 3: Population Intelligence** — OpenFDA FAERS signal, ROR disproportionality
6. **Case Intelligence Brief** — synthesized reviewer-facing output with recommended action and human confirmation workflow

> **Intelligence ≠ Determination.** Vigio builds the evidentiary brief. A qualified human reviewer makes the regulatory determination.

---

## Quick start

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set both required values in `.env`:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5-5
```

Then start the backend:

```powershell
.\.venv\Scripts\python.exe -m backend.main
```

Open `http://localhost:8000/ui` in a browser.

The frontend is a single self-contained HTML file served directly by the backend.
No Node, no npm, no Vite. Just open the URL once the backend is running.

> **Alternative:** You can also open `frontend/standalone.html` directly in a browser
> while the backend is running on port 8000 — same file, same result.

---

## Architecture

```
vigio-mvp/
├── backend/
│   ├── main.py                          # FastAPI app
│   ├── models/
│   │   └── case.py                      # Pydantic models (all layers + Brief)
│   ├── routers/
│   │   └── cases.py                     # /upload /analyze /brief /confirm /export
│   └── services/
│       ├── anthropic_service.py         # Shared model config + API/JSON validation
│       ├── pdf_parser.py                # PyMuPDF text extraction
│       ├── entity_extractor.py          # ICH E2A extraction (Claude)
│       ├── regulatory_intelligence.py   # Layer 1 (Claude)
│       ├── clinical_intelligence.py     # Layer 2 — PubMed + Claude
│       ├── population_intelligence.py   # Layer 3 — OpenFDA FAERS + Claude
│       └── brief_synthesizer.py         # Combines all layers → Case Intelligence Brief
└── frontend/
    └── src/
        ├── App.tsx                      # Two-panel layout + polling
        ├── components/
        │   ├── UploadPanel.tsx          # PDF upload + pipeline preview
        │   ├── ProgressTracker.tsx      # Live progress display
        │   └── BriefViewer.tsx          # Brief rendering + human confirmation
        ├── services/api.ts              # API calls
        └── types/brief.ts               # TypeScript types
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload PDF → returns `case_id` |
| `POST` | `/api/analyze?case_id=` | Start intelligence pipeline |
| `POST` | `/api/anthropic/check` | Verify API key and model access with a minimal paid request |
| `GET`  | `/api/status/{case_id}` | Poll progress (0–100%) |
| `GET`  | `/api/brief/{case_id}` | Retrieve completed brief |
| `POST` | `/api/confirm/{case_id}` | Submit human reviewer determination |
| `GET`  | `/api/export/{case_id}?format=json\|e2b` | Export brief |
| `GET`  | `/health` | Health check |

---

## Data sources

| Source | What we use | Cost |
|--------|-------------|------|
| Anthropic Claude | Entity extraction, all three intelligence layers | API usage |
| NCBI PubMed E-utilities | esearch + esummary for mechanistic literature | Free |
| OpenFDA FAERS | Drug-event report counts, ROR calculation | Free |

## Validation

Run local response-validation tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the paid end-to-end smoke test with fictional case data:

```powershell
.\.venv\Scripts\python.exe -m scripts.live_smoke_test
```

The smoke test calls Anthropic four times and also queries PubMed and OpenFDA.

---

## Export formats

- **JSON** — full `CaseIntelligenceBrief` model (for Oracle Argus / Veeva Vault integration)
- **E2B stub** — ICH E2B(R3) XML skeleton with mapped fields (for regulatory system handoff)

---

## Traceability by design

Every claim in the brief carries a source:
- Regulatory assessments cite ICH E2A (1994) and 21 CFR 312.32
- Clinical findings cite PMID URLs
- Population signals cite OpenFDA with report counts and ROR
- Human reviewer decision + timestamp recorded in audit trail

---

## Limitations (MVP)

- In-memory storage only — cases lost on restart (use a database in production)
- PDF must have a text layer (scanned PDFs require OCR pre-processing)
- Expectedness defaults to "Unknown" without a product label/IB loaded
- E2B export is a stub — not submission-ready without review

---

## License

Proprietary — Vigio AI. Not for distribution.
