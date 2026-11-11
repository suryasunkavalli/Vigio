"""PDF parsing service — extracts text from uploaded case report PDFs."""

import fitz  # PyMuPDF
import re
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text from a PDF file.
    Handles both digital PDFs and attempts basic OCR fallback notice for scanned ones.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    text_parts = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            text_parts.append(f"[Page {page_num}]\n{text.strip()}")
        else:
            # Page appears to be scanned/image-based
            logger.warning(f"Page {page_num} appears to have no extractable text (may be scanned)")
            text_parts.append(f"[Page {page_num}]\n[Image-based page — OCR not available in prototype]")

    doc.close()

    full_text = "\n\n".join(text_parts)

    if not full_text.strip():
        raise ValueError("No text could be extracted from the PDF. The file may be a scanned image without OCR.")

    logger.info(f"Extracted {len(full_text)} characters from {path.name} ({len(text_parts)} pages)")
    return full_text


def clean_extracted_text(raw_text: str) -> str:
    """Clean up common PDF extraction artifacts."""
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', raw_text)
    # Remove common PDF header/footer artifacts
    text = re.sub(r'Page \d+ of \d+', '', text)
    # Normalize whitespace within lines
    lines = [' '.join(line.split()) for line in text.split('\n')]
    text = '\n'.join(lines)
    return text.strip()


def extract_and_clean(pdf_path: str) -> str:
    """Full pipeline: extract + clean."""
    raw = extract_text_from_pdf(pdf_path)
    return clean_extracted_text(raw)
