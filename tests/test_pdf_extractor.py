import unittest

import pymupdf

from pocketcfo.pdf_extractor import PDFExtractionError, extract_pdf_text


def create_pdf(text: str | None = None) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if text is not None:
        page.insert_text((72, 72), text)
    contents = document.tobytes()
    document.close()
    return contents


class ExtractPdfTextTests(unittest.TestCase):
    def test_extracts_selectable_text(self) -> None:
        pdf_bytes = create_pdf("Sample invoice total: $125.00")

        extracted_text = extract_pdf_text("sample.pdf", pdf_bytes)

        self.assertIn("Sample invoice total: $125.00", extracted_text)

    def test_rejects_non_pdf_filename(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "extension"):
            extract_pdf_text("invoice.txt", create_pdf("Sample invoice"))

    def test_rejects_empty_upload(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "empty"):
            extract_pdf_text("invoice.pdf", b"")

    def test_rejects_file_over_size_limit(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "permitted upload size"):
            extract_pdf_text("invoice.pdf", create_pdf("Invoice"), max_bytes=1)

    def test_rejects_invalid_pdf(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "valid PDF"):
            extract_pdf_text("invoice.pdf", b"not a PDF")

    def test_flags_pdf_without_selectable_text(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "No selectable text"):
            extract_pdf_text("blank.pdf", create_pdf())


if __name__ == "__main__":
    unittest.main()
