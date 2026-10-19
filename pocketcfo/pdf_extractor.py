"""Validate invoice PDFs and extract selectable text without saving the file."""

import pymupdf


MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024


class PDFExtractionError(ValueError):
    """An uploaded PDF is invalid or does not contain extractable text."""


def extract_pdf_text(
    filename: str,
    pdf_bytes: bytes,
    *,
    max_bytes: int = MAX_PDF_SIZE_BYTES,
) -> str:
    """Return selectable text from a PDF after checking its basic input."""
    if not filename.lower().endswith(".pdf"):
        raise PDFExtractionError("Please upload a file with a .pdf extension.")
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise PDFExtractionError("The uploaded PDF is empty or could not be read.")
    if len(pdf_bytes) > max_bytes:
        raise PDFExtractionError("The PDF exceeds the permitted upload size.")
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise PDFExtractionError("This file does not appear to be a valid PDF.")

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.needs_pass:
                raise PDFExtractionError(
                    "This PDF is password-protected. Please upload an unlocked copy."
                )

            page_text = [page.get_text("text").strip() for page in document]
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise PDFExtractionError(
            "The PDF could not be opened. Please check that it is not damaged."
        ) from error

    extracted_text = "\n\n".join(text for text in page_text if text)
    if not extracted_text:
        raise PDFExtractionError(
            "No selectable text was found. This may be a scanned PDF; "
            "OCR is not available in this milestone."
        )

    return extracted_text
