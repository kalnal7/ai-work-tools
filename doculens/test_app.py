import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

import app


class Upload:
    def __init__(self, name="x.pdf", size=1):
        self.name = name
        self.size = size
    def getvalue(self):
        return b"0" * self.size


def test_file_count_limit_below_at_and_above():
    app.validate_files([Upload() for _ in range(49)])
    app.validate_files([Upload() for _ in range(50)])
    with pytest.raises(ValueError, match="최대 50개"):
        app.validate_files([Upload() for _ in range(51)])


def test_size_limit_at_and_over():
    app.validate_files([Upload(size=app.MAX_FILE_BYTES - 1)])
    app.validate_files([Upload(size=app.MAX_FILE_BYTES)])
    with pytest.raises(ValueError, match="15MB"):
        app.validate_files([Upload(size=app.MAX_FILE_BYTES + 1)])
    with pytest.raises(ValueError, match="빈 파일"):
        app.validate_files([Upload(size=0)])


def test_rejects_unhandled_extension():
    with pytest.raises(ValueError, match="PDF 또는 이미지"):
        app.validate_files([Upload(name="invoice.docx")])


def test_parse_invoice_and_arithmetic_check():
    text = "상호명: 다온문구\n사업자번호: 123-45-67890\n작성일자: 2026-10-01\n품목: 복사용지 A4\n공급가액: 120,000원\n부가세: 12,000원\n합계금액: 132,000원"
    row = app.parse_invoice(text, "invoice.pdf")
    assert row["상호명"] == "다온문구"
    assert row["사업자번호"] == "123-45-67890"
    assert row["공급가액"] == 120000
    assert row["부가세"] == 12000
    assert row["합계"] == 132000
    assert row["확인"] == "합계 확인"


def test_invalid_money_is_a_field_issue_and_corrected_xlsx_contains_new_value():
    row = app.parse_invoice("상호명: 다온문구\n품목: 복사용지\n공급가액: 1.2\n부가세: 10\n합계: 10", "invoice.pdf")
    assert "공급가액" in row["_invalid_money_fields"]
    with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes([{"파일명":"invoice.pdf", "상호명":"다온문구", "공급가액":1200, "부가세":10, "합계":1210}]))) as zf:
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "1200" in sheet and "1210" in sheet


def test_render_results_repair_widget_updates_download_rows():
    from streamlit.testing.v1 import AppTest

    row = {"파일명":"same.pdf", "상호명":"다온문구", "사업자번호":"123-45-67890", "작성일":"2026-10-01",
           "품목":"복사용지", "공급가액":100, "부가세":10, "합계":111, "확인":"금액 재확인", "원문":"합계금액: 110원"}
    def render():
        import streamlit as st
        import app
        row = {"파일명":"same.pdf", "상호명":"다온문구", "사업자번호":"123-45-67890", "작성일":"2026-10-01",
               "품목":"복사용지", "공급가액":100, "부가세":10, "합계":111, "확인":"금액 재확인", "원문":"합계금액: 110원"}
        original_export = app.xlsx_bytes
        def capture_export(rows):
            st.session_state["exported_review_rows"] = [dict(item) for item in rows]
            return original_export(rows)
        app.xlsx_bytes = capture_export
        try:
            app._render_results(st, [row], 0.1, "apptest_invoice_review")
        finally:
            app.xlsx_bytes = original_export
    at = AppTest.from_function(render).run()
    assert not at.exception
    assert any(button.label == "수정한 엑셀 파일 다운로드" for button in at.get("download_button"))
    next(widget for widget in at.text_input if widget.label == "수정값").set_value("110")
    next(button for button in at.button if button.label == "값 적용").click().run()
    assert not at.exception
    exported = at.session_state["exported_review_rows"]
    assert exported[0]["합계"] == 110
    assert any(button.label == "수정한 엑셀 파일 다운로드" for button in at.get("download_button"))
    with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes(exported))) as zf:
        assert "110" in zf.read("xl/worksheets/sheet1.xml").decode("utf-8")


def test_xlsx_is_valid_zip_with_workbook_and_rows():
    data = app.xlsx_bytes([app.parse_invoice("상호명: 다온문구\n공급가액: 120,000\n부가세: 12,000\n합계금액: 132,000")])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert zf.testzip() is None
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "다온문구" in sheet
        assert "132000" in sheet
        assert 'state="frozen"' in sheet
        assert '<autoFilter ref="A1:I2"' in sheet
        assert "xl/styles.xml" in zf.namelist()
        assert "확인" in sheet


def test_actual_local_korean_ocr_on_generated_invoice_image(tmp_path):
    if not app._tool("tesseract"):
        pytest.skip("Tesseract OCR is not installed")
    image = Image.new("RGB", (1800, 1400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(Path(__file__).parent / "static" / "fonts" / "SUIT-SemiBold.ttf"), 72)
    for i, line in enumerate(["상호명: 다온문구", "사업자번호: 123-45-67890", "작성일자: 2026-10-01",
                              "품목: 복사용지 A4", "공급가액: 120,000", "부가세: 12,000",
                              "합계금액: 132,000"]):
        draw.text((100, 100 + i * 170), line, fill="black", font=font)
    path = tmp_path / "invoice.png"
    image.save(path)
    text = app.ocr_image(path.read_bytes())
    row = app.parse_invoice(text, "invoice.png")
    assert row["공급가액"] == 120000, text
    assert row["부가세"] == 12000, text
    assert row["합계"] == 132000, text


def test_sample_image_pdfs_end_to_end():
    if not app._tool("tesseract") or not app._tool("pdftoppm"):
        pytest.skip("Tesseract and Poppler are required for PDF OCR")
    root = Path(__file__).resolve().parent / "assets"
    paths = sorted(root.glob("demo_invoice_*.pdf"))
    assert len(paths) == 3
    rows = [app.parse_invoice(app.extract_pdf(path.read_bytes()), path.name) for path in paths]
    assert [row["공급가액"] for row in rows] == [120000, 85000, 210000]
    assert [row["부가세"] for row in rows] == [12000, 8500, 21000]
    assert [row["합계"] for row in rows] == [132000, 93500, 231000]
    assert rows[0]["품목"] in {"복사용지 A4", "복사용지 Ad"}
    assert [row["품목"] for row in rows[1:]] == ["택배 상자 3호", "업무용 식자재"]
    assert all(row["확인"] == "합계 확인" for row in rows), rows
    assert all(row["_recognition"]["route"] == "local_ocr" for row in rows)


def test_check_label_is_display_only():
    assert app.check_label("합계 확인") == "✓ 정상"
    assert app.check_label("금액 재확인") == "확인 필요 · 금액 재확인"
    assert app.check_label("") == "확인 필요 · 원본 대조"
    row = app.parse_invoice("상호명: 다온문구\n품목: 복사용지\n공급가액: 100\n부가세: 10\n합계: 110", "a.pdf")
    with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes([row]))) as zf:
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "합계 확인" in sheet and "정상" not in sheet


def test_count_edits_zero_one_two_and_normalized_money():
    base = {"파일명":"a.pdf", "상호명":"다온", "품목":"복사용지", "공급가액":100, "부가세":10, "합계":110}
    assert app.count_edits([base], [dict(base)]) == 0
    assert app.count_edits([base], [dict(base, 공급가액="100")]) == 0
    assert app.count_edits([base], [dict(base, 품목="복사용지 (검수)")]) == 1
    assert app.count_edits([base], [dict(base, 품목="x", 상호명="y")]) == 2
    assert app.edited_documents([dict(base, _document_id="d")], [dict(base, _document_id="d", 품목="x")]) == {"d"}


def test_default_selection_prefers_issue_document_and_field():
    rows = [{"_document_id":"a"}, {"_document_id":"b"}]
    assert app.default_selection(rows, []) == ("a", "품목")
    assert app.default_selection(rows, [{"document_id":"b", "field":"합계"}]) == ("b", "합계")
    assert app.default_selection(rows, [{"document_id":"b", "field":"문서"}]) == ("b", "품목")
    assert app.default_selection([], []) == (None, "품목")


def test_file_status_lines_follow_real_tracked_progress():
    from product_workflow import DownloadJob, process_invoices
    from document_reader import DocumentText
    job, seen = DownloadJob("k"), []
    def extract(name, data):
        seen.append(app.file_status_lines(["a.pdf", "b.pdf", "c.pdf"], job.snapshot()["files"]))
        if name == "b.pdf":
            raise ValueError("broken")
        return DocumentText("상호명: 다온\n품목: 용지\n공급가액: 100\n부가세: 10\n합계: 110", {"pages":2})
    read, step = app.tracked_steps(job, extract, lambda *a: None)
    process_invoices([("a.pdf", b"1"), ("b.pdf", b"2"), ("c.pdf", b"3")], read, app.parse_invoice, app.xlsx_bytes, step)
    assert seen[0] == [("a.pdf", "읽는 중"), ("b.pdf", "대기"), ("c.pdf", "대기")]
    assert seen[2][0] == ("a.pdf", "완료 · 2페이지") and seen[2][1] == ("b.pdf", "실패")
    assert app.file_status_lines(["a.pdf", "b.pdf", "c.pdf"], job.snapshot()["files"]) == [
        ("a.pdf", "완료 · 2페이지"), ("b.pdf", "실패"), ("c.pdf", "완료 · 2페이지")]


def test_review_panel_segmented_selection_edit_count_and_revert():
    from streamlit.testing.v1 import AppTest

    def render():
        import streamlit as st
        import app
        rows = [{"파일명":f"d{i}.pdf", "상호명":"다온", "품목":f"용지{i}", "공급가액":100, "부가세":10,
                 "합계":110 if i != 2 else 111, "원문":""} for i in (1, 2)]
        original_export = app.xlsx_bytes
        def capture_export(items):
            st.session_state["exported"] = [dict(item) for item in items]
            return original_export(items)
        app.xlsx_bytes = capture_export
        try:
            app._render_results(st, rows, 0.1, "seg")
        finally:
            app.xlsx_bytes = original_export
    at = AppTest.from_function(render).run()
    assert not at.exception
    doc = next(w for w in at.button_group if w.label == "문서")
    field = next(w for w in at.button_group if w.label == "수정할 항목")
    assert at.session_state["seg_canonical_rows"][1]["_document_id"] == doc.value  # issue document first
    assert field.value == "합계"
    assert not any(m.value.startswith('<div class="dl-edit-count">') for m in at.markdown)
    next(w for w in at.text_input if w.label == "수정값").set_value("110")
    next(b for b in at.button if b.label == "값 적용").click().run()
    assert at.session_state["exported"][1]["합계"] == 110
    assert any("수정 1건 반영됨" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "원래 값으로 되돌리기").click().run()
    assert not at.exception
    assert at.session_state["exported"][1]["합계"] == 111
    assert not any("반영됨" in m.value for m in at.markdown)
    assert not any(b.label == "원래 값으로 되돌리기" for b in at.button)
