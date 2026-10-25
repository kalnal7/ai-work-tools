import shutil
import pytest

OCR_INTEGRATION_TESTS = {
    "test_actual_local_korean_ocr_on_generated_invoice_image",
    "test_sample_image_pdfs_end_to_end",
    "test_mixed_pdf_reads_the_scanned_sixth_page_instead_of_stopping_at_five",
    "test_real_pdf_partial_failure_keeps_valid_work_and_reports_bad_file",
}


def pytest_collection_modifyitems(items):
    if not all(shutil.which(name) for name in ("tesseract", "pdftotext", "pdftoppm")):
        skip = pytest.mark.skip(reason="requires Tesseract OCR and Poppler command-line tools")
        for item in items:
            if item.name in OCR_INTEGRATION_TESTS:
                item.add_marker(skip)
