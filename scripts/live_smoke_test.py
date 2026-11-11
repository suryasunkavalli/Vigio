"""Paid end-to-end smoke test using a fictional pharmacovigilance case."""

import io

import pymupdf
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from backend.main import app


SYNTHETIC_NARRATIVE = """FICTIONAL TEST CASE - NOT A REAL PATIENT

On November 10, 2026, Dr. Maya Patel reported a 45-year-old female patient
who received amoxicillin 500 mg orally three times daily for acute sinusitis.
Treatment began on November 8, 2026. On November 9, 2026, the patient developed
generalized urticaria. There was no breathing difficulty, hospitalization,
disability, or other medically significant complication. Amoxicillin was
discontinued and an oral antihistamine was given. The patient fully recovered
on November 10, 2026. Dr. Patel considered the reaction related to amoxicillin.
No product label or investigator brochure was supplied with the report.
"""


def build_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 545, 792),
        SYNTHETIC_NARRATIVE,
        fontsize=11,
    )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def main() -> None:
    with TestClient(app) as client:
        upload = client.post(
            "/api/upload",
            files={
                "file": (
                    "synthetic_amoxicillin_case.pdf",
                    io.BytesIO(build_pdf()),
                    "application/pdf",
                )
            },
        )
        upload.raise_for_status()
        case_id = upload.json()["case_id"]

        analysis = client.post("/api/analyze", params={"case_id": case_id})
        analysis.raise_for_status()

        status = client.get(f"/api/status/{case_id}")
        status.raise_for_status()
        status_data = status.json()
        if status_data["status"] != "complete":
            raise RuntimeError(f"Analysis did not complete: {status_data}")

        brief_response = client.get(f"/api/brief/{case_id}")
        brief_response.raise_for_status()
        brief = brief_response.json()

        confirmation = client.post(
            f"/api/confirm/{case_id}",
            params={
                "reviewer_name": "MVP Smoke Test",
                "reviewer_decision": "Manual review completed",
                "reviewer_notes": "Automated fictional-case smoke test",
            },
        )
        confirmation.raise_for_status()

        export = client.get(f"/api/export/{case_id}", params={"format": "json"})
        export.raise_for_status()

        print("workflow: complete")
        print(f"case_id: {case_id}")
        print(f"source_filename: {brief['source_pdf_filename']}")
        print(f"validity: {brief['regulatory']['validity_status']}")
        print(f"faers_source: {brief['population']['faers_signal']['data_source']}")
        print(f"faers_ror: {brief['population']['faers_signal']['reporting_odds_ratio']}")
        print(f"faers_ci: {brief['population']['faers_signal']['ror_ci_lower']}-{brief['population']['faers_signal']['ror_ci_upper']}")
        print(f"recommended_action: {brief['recommended_action']}")
        print(f"export_bytes: {len(export.content)}")


if __name__ == "__main__":
    main()
