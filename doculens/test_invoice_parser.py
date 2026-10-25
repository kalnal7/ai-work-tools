import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

import app


@pytest.mark.parametrize("text,items", [
    ("상 호 명: 오름상사\n품 목: 재생 복사용지 A4\n공 급 가 액: 120,000원\n부 가 세: 12,000원\n합 계 금 액: 132,000원", "재생 복사용지 A4"),
    ("거래처\n오름상사\n품명\n재생 복사용지 A4\n공급가액\n120000\n세액\n12000\n총액\n132000", "재생 복사용지 A4"),
    ("상호명: 오름상사\n품목  수량  단가  금액\n재생 복사용지 A4  2  60000  120000\n공급가액: 120000  부가세: 12000  합계: 132000", "재생 복사용지 A4"),
])
def test_different_label_layouts_keep_actual_item_and_amount(text, items):
    row = app.parse_invoice(text)
    assert row["상호명"] == "오름상사"
    assert row["품목"] == items
    assert (row["공급가액"], row["부가세"], row["합계"]) == (120000, 12000, 132000)
    assert row["확인"] == "합계 확인"


@pytest.mark.parametrize("amount", ["1.2", "12,0002", "120,00", "-120000", "120000abc"])
def test_malformed_ocr_amount_is_not_silently_exported_as_a_partial_number(amount):
    row = app.parse_invoice(f"상호명: 오름\n품목: 종이\n공급가액: {amount}\n부가세: 12000\n합계: 132000")
    assert row["공급가액"] is None
    assert "공급가액 형식 확인" in row["확인"]
    with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes([row]))) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    assert sheet.find(".//{*}c[@r='F2']/{*}v") is None


def test_conflicting_totals_require_review_and_supplier_signature_is_not_a_name():
    row = app.parse_invoice("공급자 서명 ______\n품목: 종이\n공급가액: 100\n부가세: 10\n합계: 110\n합계: 220")
    assert row["상호명"] == ""
    assert row["합계"] is None
    assert "합계 형식 확인" in row["확인"]


def test_ocr_control_characters_do_not_break_export_xml():
    row = app.parse_invoice("상호명: 오름\x00상사\n품목: 종이\n공급가액: 100\n부가세: 10\n합계: 110")
    with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes([row]))) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    assert sheet.find(".//{*}c[@r='B2']/{*}is/{*}t").text == "오름상사"
