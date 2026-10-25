"""Real upload, local recognition, field edits and both download buttons."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from playwright.sync_api import sync_playwright, expect
from document_reader import model_directory

ROOT = Path(__file__).resolve().parent


def workbook_cells(path):
    with zipfile.ZipFile(path) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    return {cell.attrib["r"]: (cell.findtext("{*}is/{*}t") or cell.findtext("{*}v") or "")
            for cell in sheet.findall(".//{*}sheetData/{*}row/{*}c")}


def expect_code_value(page, value):
    exact = page.get_by_role("code").filter(has_text=re.compile(r"^" + re.escape(value) + r"$"))
    expect(exact).to_have_count(1, timeout=15000)


def test_real_browser_upload_edit_and_reexport(tmp_path):
    out_name = "e2e" if os.environ.get("CI") else "product_revision_20261025"
    out = ROOT / "output" / out_name
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    log = (tmp_path / "server.log").open("wb")
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
        "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError((tmp_path / "server.log").read_text(errors="replace"))
            try:
                with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            time.sleep(.2)
        else:
            raise AssertionError("Local server did not start")
        with sync_playwright() as playwright:
            executable = Path(os.environ.get("DOCULENS_CHROMIUM_EXECUTABLE", ""))
            launch_options = {"headless": True}
            if executable.is_file():
                launch_options["executable_path"] = str(executable)
            browser = playwright.chromium.launch(**launch_options)
            try:
                context = browser.new_context(viewport={"width":1600, "height":1000}, locale="ko-KR",
                    accept_downloads=True, record_video_dir=str(out / "recording"))
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded")
                paths = sorted((ROOT / "assets").glob("demo_invoice_*.pdf"))
                page.locator('input[type="file"]').set_input_files([str(path) for path in paths])
                with page.expect_download(timeout=120000) as pending:
                    page.get_by_role("button", name="한 번에 정리하고 엑셀 받기", exact=True).click()
                pending.value.save_as(str(tmp_path / "initial.xlsx"))
                cells = workbook_cells(tmp_path / "initial.xlsx")
                original_item = cells["E2"]
                assert original_item in {"복사용지 A4", "복사용지 Ad"}
                assert [cells[f"E{row}"] for row in (3, 4)] == ["택배 상자 3호", "업무용 식자재"]
                assert sum(int(cells[f"H{row}"]) for row in (2, 3, 4)) == 456500
                page.get_by_label("수정값", exact=True).wait_for(timeout=60000)
                page.locator('[data-testid="stImage"] img, [data-testid="stImageContainer"] img, img[src*="/media/"]').first.wait_for(timeout=15000)
                assert page.get_by_test_id("stException").count() == 0
                # A different value must reach the top download, not the cached initial XLSX.
                changed = f"{original_item} (검수)"
                page.get_by_label("수정값", exact=True).fill(changed)
                page.get_by_role("button", name="값 적용", exact=True).click()
                expect_code_value(page, changed)
                with page.expect_download(timeout=20000) as pending:
                    page.get_by_role("button", name="정리한 엑셀 다운로드", exact=True).click()
                pending.value.save_as(str(tmp_path / "edited.xlsx"))
                assert workbook_cells(tmp_path / "edited.xlsx")["E2"] == changed
                # Restore the original description; keep only the final, matching workbook.
                page.get_by_label("수정값", exact=True).fill(original_item)
                page.get_by_role("button", name="값 적용", exact=True).click()
                expect_code_value(page, original_item)
                with page.expect_download(timeout=20000) as pending:
                    page.get_by_role("button", name="수정한 엑셀 파일 다운로드", exact=True).click()
                target = out / "doculens_최종확인.xlsx"
                pending.value.save_as(str(target))
                final = workbook_cells(target)
                assert final["E2"] == original_item
                assert [final[f"I{row}"] for row in (2, 3, 4)] == ["합계 확인"] * 3
                assert sum(int(final[f"G{row}"]) for row in (2, 3, 4)) == 41500
                assert page.get_by_test_id("stException").count() == 0
                expect(page.get_by_text("수정 1건 반영됨")).to_have_count(0)
                # One-click revert restores the OCR value and the next download carries it.
                page.get_by_label("수정값", exact=True).fill(changed)
                page.get_by_role("button", name="값 적용", exact=True).click()
                expect_code_value(page, changed)
                expect(page.get_by_text("수정 1건 반영됨")).to_have_count(2, timeout=15000)
                page.get_by_role("button", name="원래 값으로 되돌리기", exact=True).click()
                expect_code_value(page, original_item)
                expect(page.get_by_text("수정 1건 반영됨")).to_have_count(0, timeout=15000)
                with page.expect_download(timeout=20000) as pending:
                    page.get_by_role("button", name="정리한 엑셀 다운로드", exact=True).click()
                pending.value.save_as(str(tmp_path / "reverted.xlsx"))
                reverted = workbook_cells(tmp_path / "reverted.xlsx")
                assert reverted["E2"] == original_item and reverted["I2"] == "합계 확인"
                assert page.get_by_test_id("stException").count() == 0
                page.get_by_text("결과 미리보기", exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(out / "program_verified.png"), full_page=True)
                (out / "execution.json").write_text(json.dumps({
                    "input_kind":"fictional_scan_pdfs", "input_files":[path.name for path in paths],
                    "ocr_model":model_directory().name if model_directory() else None,
                    "item_fields":[final[f"E{row}"] for row in (2, 3, 4)],
                    "total":456500, "vat":41500, "original_preview_visible":True,
                    "top_download_reflects_edit":True, "final_download_matches_original":True,
                    "workbook":str(target)}, ensure_ascii=False, indent=2), encoding="utf-8")
                context.close()
            finally:
                browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)
        log.close()
