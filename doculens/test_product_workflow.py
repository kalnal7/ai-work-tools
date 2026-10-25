"""Real product failure boundaries, input isolation and single-flight downloads."""
import importlib.util
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
import zipfile

import app
from product_workflow import DownloadJob, input_key, invoice_summary, process_invoices, review_invoice, review_worklist

ROOT = Path(__file__).resolve().parent


def render_review_fixture():
    import streamlit as st
    import app
    row = {"파일명":"same.pdf", "상호명":"다온문구", "사업자번호":"123-45-67890",
           "작성일":"2026-10-01", "품목":"복사용지", "공급가액":100, "부가세":10,
           "합계":111, "확인":"금액 재확인", "원문":"합계금액: 110원"}
    original_export = app.xlsx_bytes
    def capture_export(rows):
        st.session_state["exported_review_rows"] = [dict(item) for item in rows]
        return original_export(rows)
    app.xlsx_bytes = capture_export
    try:
        app._render_results(st, [row], 0.1, "workflow_review")
    finally:
        app.xlsx_bytes = original_export


class ProductWorkflowTests(unittest.TestCase):
    def test_duplicate_clicks_do_one_job_and_keep_download_bytes(self):
        job = DownloadJob("selection-a")
        entered, release = threading.Event(), threading.Event()
        calls = []
        def work(progress):
            calls.append(1); progress(0,1,"receipt.pdf"); entered.set()
            self.assertTrue(release.wait(3))
            progress(1,1,"receipt.pdf")
            return b"real workbook bytes", {"count":1}
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(job.run,work)
            self.assertTrue(entered.wait(3))
            job.request()
            self.assertEqual(job.snapshot()["status"],"running")
            second = pool.submit(job.run,work)
            release.set()
            self.assertEqual(first.result(3),second.result(3))
        self.assertEqual(calls,[1])
        self.assertEqual(job.snapshot()["status"],"ready")
        self.assertEqual(job.snapshot()["done"],1)

    def test_failure_can_retry_and_changed_input_never_reuses_job(self):
        job = DownloadJob(input_key([("receipt.pdf",b"a")]))
        def fail(progress):
            raise ValueError("원본 확인")
        with self.assertRaises(ValueError): job.run(fail)
        self.assertEqual(job.snapshot()["status"],"failed")
        job.request()
        self.assertEqual(job.snapshot()["status"],"queued")
        self.assertEqual(job.run(lambda p:(b"fixed",{"count":1})),b"fixed")
        self.assertNotEqual(job.key,input_key([("receipt.pdf",b"b")]))
        self.assertNotEqual(job.key,input_key([("renamed.pdf",b"a")]))
        self.assertNotEqual(input_key([("ab",b"c")]),input_key([("a",b"bc")]))

    def test_progress_below_equal_above_and_no_empty_export(self):
        job=DownloadJob("progress")
        for done in (0,1,2): job.progress(done,2,"실제 입력")
        for done in (-1,3):
            with self.assertRaises(ValueError): job.progress(done,2,"실제 입력")
        with self.assertRaises(ValueError): job.run(lambda p:(b"",{}))
        self.assertEqual(job.snapshot()["status"],"failed")

    def test_edited_money_recomputes_summary_and_checks_without_float_loss(self):
        row={"상호명":"거래처","공급가액":100,"부가세":10,"합계":110}
        self.assertEqual(invoice_summary([row])["total"],110)
        edited={**row,"합계":"1,100"}
        summary=invoice_summary([edited])
        self.assertEqual(summary["total"],1100)
        self.assertEqual(summary["needs_review"],1)
        self.assertIn("금액 재확인",summary["rows"][0]["확인"])
        self.assertEqual(row["합계"],110)
        for number in (0,1,9007199254740993):
            self.assertEqual(review_invoice({**row,"합계":str(number)})["합계"],number)
        for number in (-1,"NaN","Infinity","1.1",True):
            self.assertIsNone(review_invoice({**row,"합계":number})["합계"])

    def test_invalid_money_reason_survives_rechecks_without_exporting_partial_amount(self):
        row = app.parse_invoice("상호명: 다온문구\n품목: 복사용지\n공급가액: 1.2\n부가세: 10\n합계: 10", "invoice.pdf")
        reviewed = review_invoice(row)
        self.assertIsNone(reviewed["공급가액"])
        self.assertIn("공급가액 형식 확인", reviewed["확인"])
        rechecked = invoice_summary([reviewed])
        self.assertIn("공급가액 형식 확인", rechecked["rows"][0]["확인"])
        self.assertNotIn("공급가액 누락", rechecked["rows"][0]["확인"])
        self.assertEqual(review_worklist(rechecked["rows"])[0]["field"], "공급가액")
        with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes(rechecked["rows"]))) as workbook:
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        ns = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        self.assertIsNone(sheet.find(".//s:c[@r='F2']/s:v", ns))

    def test_repair_form_keeps_invalid_reason_then_updates_same_row_and_xlsx(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_function(render_review_fixture).run()
        self.assertFalse(at.exception)
        document_id = at.session_state["exported_review_rows"][0]["_document_id"]
        next(widget for widget in at.text_input if widget.label == "수정값").set_value("1.2")
        next(button for button in at.button if button.label == "값 적용").click().run()
        self.assertFalse(at.exception)
        exported = at.session_state["exported_review_rows"]
        self.assertIsNone(exported[0]["합계"])
        self.assertEqual(exported[0]["확인"], "합계 형식 확인")
        self.assertEqual(next(w for w in at.button_group if w.label == "수정할 항목").value, "합계")
        self.assertIn("합계금액: 110원", at.text_area[0].value)
        next(widget for widget in at.text_input if widget.label == "수정값").set_value("110")
        next(button for button in at.button if button.label == "값 적용").click().run()
        self.assertFalse(at.exception)
        exported = at.session_state["exported_review_rows"]
        self.assertEqual(exported[0]["합계"], 110)
        self.assertEqual(exported[0]["_document_id"], document_id)
        self.assertEqual(exported[0]["확인"], "합계 확인")
        self.assertEqual(at.dataframe[0].value.iloc[0]["확인"], "✓ 정상")
        self.assertEqual(at.session_state["workflow_review_canonical_rows"][0]["_document_id"], exported[0]["_document_id"])
        with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes(exported))) as workbook:
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        ns = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        self.assertEqual(sheet.find(".//s:c[@r='H2']/s:v", ns).text, "110")

    def test_table_edit_refreshes_review_column_summary_and_download(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_function(render_review_fixture).run()
        self.assertFalse(at.exception)
        at.session_state["workflow_review_table_0"] = {
            "edited_rows":{0:{"합계":110}}, "added_rows":[], "deleted_rows":[]}
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["exported_review_rows"][0]["합계"], 110)
        self.assertEqual(at.dataframe[0].value.iloc[0]["확인"], "✓ 정상")
        self.assertTrue(any("₩110" in item.value for item in at.markdown))
        self.assertTrue(any(item.value == "검수할 항목이 없습니다." for item in at.success))

    def test_worklist_uses_document_identity_and_names_field_issues(self):
        rows=[
            {"파일명":"같은.pdf","_row_index":0,"_document_id":"doc-a","상호명":"상점","품목":"","공급가액":100,"부가세":10,"합계":111,"원문":"품목: ?"},
            {"파일명":"같은.pdf","_row_index":1,"_document_id":"doc-b","상호명":"","품목":"책","공급가액":100,"부가세":10,"합계":110,"원문":"상호명: "},
        ]
        issues=review_worklist(rows)
        self.assertEqual([(i["document_id"],i["row_index"],i["field"],i["reason"]) for i in issues],
                         [("doc-a",0,"품목","품목 누락"),("doc-a",0,"합계","금액 불일치"),("doc-b",1,"상호명","상호명 누락")])
        self.assertEqual(rows[0]["품목"],"")

    def test_extraction_failure_only_clears_after_explicit_manual_review(self):
        row={"파일명":"broken.pdf","_row_index":0,"_document_id":"broken-id","_extraction_failed":True,
             "_extraction_reason":"인식 실패 · 이미지 읽기 실패","원문":""}
        self.assertEqual(review_worklist([row])[0]["field"],"문서")
        edited=review_invoice({**row,"합계":120})
        self.assertIn("인식 실패",edited["확인"])
        self.assertEqual(review_worklist([edited])[0]["field"],"문서")
        completed=review_invoice({**edited,"_manual_review_complete":True})
        self.assertNotIn("인식 실패",completed["확인"])
        self.assertNotEqual(completed["확인"],"합계 확인")

    def test_real_pdf_partial_failure_keeps_valid_work_and_reports_bad_file(self):
        valid=ROOT/"assets/demo_invoice_1.pdf"
        data,report=process_invoices([(valid.name,valid.read_bytes()),("broken.pdf",b"not a PDF")],
            app.extract_text,app.parse_invoice,app.xlsx_bytes)
        self.assertTrue(data.startswith(b"PK"))
        self.assertEqual(report["count"],2)
        self.assertEqual(report["rows"][0]["합계"],132000)
        self.assertEqual(report["errors"][0]["file"],"broken.pdf")
        self.assertTrue(report["rows"][1]["확인"].startswith("인식 실패"))
        self.assertNotEqual(report["rows"][0]["_document_id"],report["rows"][1]["_document_id"])
        with self.assertRaisesRegex(ValueError,"읽을 수 있는 문서"):
            process_invoices([("bad.pdf",b"bad")],app.extract_text,app.parse_invoice,app.xlsx_bytes)


if __name__=="__main__":
    unittest.main()
