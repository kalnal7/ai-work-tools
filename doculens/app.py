"""DOCULENS local invoice OCR workbench.

Run with: streamlit run app.py --server.address 127.0.0.1 --server.port 8876
OCR runs locally through Tesseract. No uploaded document is sent to a remote API.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from visual_identity import app_css, load_identity
from product_workflow import DownloadJob, input_key, process_invoices, invoice_summary, review_worklist, review_invoice
from document_reader import (find_tool as _tool, extract_pdf, ocr_image, extract_text,
                             document_pages, source_preview, MAX_DOCUMENT_PAGES)
from invoice_parser import parse_invoice

MAX_FILES = 50
MAX_FILE_BYTES = 15 * 1024 * 1024
FIELDS = ["파일명", "상호명", "사업자번호", "작성일", "품목", "공급가액", "부가세", "합계", "확인"]
EDITABLE_FIELDS = [name for name in FIELDS if name not in {"파일명", "확인"}]
OK_CHECK = "합계 확인"


def check_label(value):
    """Screen-only wording for the 확인 column; the XLSX keeps the workflow value."""
    value = str(value or "").strip()
    if value == OK_CHECK:
        return "✓ 정상"
    return "확인 필요 · " + (value or "원본 대조")


def _plain(value):
    return "" if value is None else str(value).strip()


def count_edits(original_rows, current_rows):
    """Number of (document, field) values that differ from what OCR first read."""
    count = 0
    for original, current in zip(original_rows, current_rows):
        before, after = review_invoice(original), review_invoice(current)
        count += sum(_plain(before.get(field)) != _plain(after.get(field)) for field in EDITABLE_FIELDS)
    return count


def edited_documents(original_rows, current_rows):
    return {current.get("_document_id") for original, current in zip(original_rows, current_rows)
            if count_edits([original], [current])}


def default_selection(rows, issues):
    """The first issue's document and field, otherwise the first document's 품목."""
    if issues:
        return issues[0]["document_id"], (issues[0]["field"] if issues[0]["field"] in EDITABLE_FIELDS else "품목")
    return (rows[0].get("_document_id") if rows else None), "품목"


def file_status_lines(names, files_state):
    """[(name, 대기/읽는 중/완료 · n페이지/실패)] from DownloadJob file states."""
    lines = []
    for index, name in enumerate(names):
        entry = files_state.get(index, {})
        status = entry.get("status")
        if status == "reading":
            label = "읽는 중"
        elif status == "done":
            label = "완료" + (f' · {entry["pages"]}페이지' if entry.get("pages") else "")
        elif status == "failed":
            label = "실패"
        else:
            label = "대기"
        lines.append((name, label))
    return lines


def tracked_steps(job, extract, progress):
    """Wrap extract/progress so each file's status reaches the page while it runs."""
    calls = {"n":0, "current":0}
    def step(done, total, label):
        index, before = divmod(calls["n"], 2)
        calls["n"] += 1
        if before == 0:
            calls["current"] = index
            job.mark_file(index, "reading")
        else:
            job.mark_file(index, "done")
        progress(done, total, label)
    def read(name, data):
        index = calls["current"]
        try:
            text = extract(name, data)
        except Exception:
            job.mark_file(index, "failed")
            raise
        if not str(text).strip():
            job.mark_file(index, "failed")
        else:
            job.mark_file(index, "reading", getattr(text, "recognition", {}).get("pages"))
        return text
    return read, step


def validate_files(files):
    if len(files) > MAX_FILES:
        raise ValueError(f"한 번에 최대 {MAX_FILES}개 파일까지 처리할 수 있습니다.")
    for f in files:
        data = f.getvalue()
        if not data:
            raise ValueError(f"{f.name}: 빈 파일입니다. 원본을 다시 선택해 주세요.")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"{f.name}: 파일 크기는 15MB 이하로 올려 주세요.")
        if Path(f.name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            raise ValueError(f"{f.name}: PDF 또는 이미지 파일만 지원합니다.")


def xlsx_bytes(rows: list[dict]) -> bytes:
    rows = invoice_summary(rows)["rows"]
    headers = FIELDS
    def cell(ref, value):
        if value is None or value == "":
            return f'<c r="{ref}"/>'
        if isinstance(value, (int, float)):
            return f'<c r="{ref}" s="2"><v>{value}</v></c>'
        safe_text = "".join(char for char in str(value) if char in "\t\n\r" or
                            0x20 <= ord(char) <= 0xD7FF or 0xE000 <= ord(char) <= 0xFFFD or
                            0x10000 <= ord(char) <= 0x10FFFF)
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(safe_text)}</t></is></c>'
    xml_rows = []
    for r_index, values in enumerate([headers] + [[row.get(h, "") for h in headers] for row in rows], 1):
        contents = "".join(cell(f'{chr(65+c)}{r_index}', v) for c, v in enumerate(values))
        if r_index == 1:
            contents = contents.replace(' t="inlineStr"', ' s="1" t="inlineStr"')
        xml_rows.append(f'<row r="{r_index}" ht="24" customHeight="1">' + contents + '</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
             '<cols><col min="1" max="1" width="30" customWidth="1"/><col min="2" max="5" width="22" customWidth="1"/><col min="6" max="8" width="18" customWidth="1"/><col min="9" max="9" width="48" customWidth="1"/></cols>'
             '<sheetData>' + "".join(xml_rows) + f'</sheetData><autoFilter ref="A1:I{max(1,len(rows)+1)}"/></worksheet>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="문서 정리" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    }
    files['[Content_Types].xml'] = files['[Content_Types].xml'].replace('</Types>', '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
    files['xl/_rels/workbook.xml.rels'] = files['xl/_rels/workbook.xml.rels'].replace('</Relationships>', '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    files['xl/styles.xml'] = ('<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="맑은 고딕"/></font><font><b/><sz val="11"/><name val="맑은 고딕"/><color rgb="FFFDFDFC"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF9C3D2E"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return stream.getvalue()


def demo_rows():
    assets = Path(__file__).resolve().parent / "assets"
    rows = []
    for path in sorted(assets.glob("demo_invoice_*.pdf")):
        rows.append(parse_invoice(extract_pdf(path.read_bytes()), path.name))
    if not rows:
        raise RuntimeError("예시 PDF를 찾지 못했습니다. make_demo_files.py를 먼저 실행해 주세요.")
    return rows


def _source_panel(st, row, source_files, editor_key):
    position = row.get("_row_index", 0)
    if not 0 <= position < len(source_files):
        st.caption("이 결과에는 원본 파일이 연결되지 않았습니다.")
        return
    name, data = source_files[position]
    try:
        cache_key = editor_key + "_preview"
        fingerprint = hashlib.sha256(data).hexdigest()
        cache = st.session_state.get(cache_key, {})
        if cache.get("fingerprint") != fingerprint:
            cache = {"fingerprint":fingerprint, "pages":document_pages(name, data)}
        pages = cache["pages"]
        page = int(st.number_input("원본 페이지", min_value=1, max_value=pages, value=1,
            key=editor_key+"_page_"+str(position))) if pages > 1 else 1
        if cache.get("page") != page:
            cache.update(page=page, image=source_preview(name, data, page))
        st.session_state[cache_key] = cache
        st.image(cache["image"], caption=f"{name} · {page}/{pages}페이지", width="stretch")
    except Exception as exc:
        st.error(f"원본 미리보기를 열지 못했습니다: {exc}")


def _render_results(st, rows, elapsed, editor_key, source_files=()):
    st.markdown('<div class="dl-section"><div class="left"><span class="index">02</span>'
        '<h2>결과 미리보기</h2></div><span class="detail">필요한 항목만 바로 수정하세요</span></div>', unsafe_allow_html=True)
    metrics = st.empty()
    st.caption(f"인식 시간 {elapsed:.2f}초 · 현재 문서 기준")
    rows_key = editor_key + "_canonical_rows"
    originals_key = editor_key + "_original_rows"
    revision_key = editor_key + "_editor_revision"
    if rows_key not in st.session_state:
        seeded = []
        for position, source in enumerate(rows):
            row = review_invoice(source)
            row.setdefault("_row_index", position)
            row.setdefault("_document_id", hashlib.sha256(f"{editor_key}:{position}:{row.get('파일명','문서')}".encode("utf-8")).hexdigest()[:24])
            row.setdefault("_input_fingerprint", editor_key)
            seeded.append(row)
        st.session_state[rows_key] = seeded
        st.session_state[originals_key] = [dict(row) for row in seeded]
        st.session_state[revision_key] = 0
    canonical = st.session_state[rows_key]
    originals = st.session_state.setdefault(originals_key, [dict(row) for row in canonical])
    widget_key = f"{editor_key}_table_{st.session_state[revision_key]}"
    edited = st.data_editor([{**{k: r.get(k, "") for k in FIELDS}, "확인":check_label(r.get("확인"))} for r in canonical],
        width="stretch", hide_index=True, key=widget_key, disabled=["파일명", "확인"],
        column_config={**{k:st.column_config.NumberColumn(k, min_value=0, step=1, format="localized")
                          for k in ("공급가액", "부가세", "합계")},
                       "확인":st.column_config.TextColumn("확인", width="medium")})
    if not isinstance(edited, list):
        edited = edited.to_dict(orient="records")
    table_changed = False
    for position, displayed in enumerate(edited):
        if position >= len(canonical):
            break
        previous = dict(canonical[position])
        for field in EDITABLE_FIELDS:
            canonical[position][field] = displayed.get(field, "")
            if displayed.get(field, "") != previous.get(field, ""):
                table_changed = True
                if field in {"공급가액", "부가세", "합계"}:
                    canonical[position]["_invalid_money_fields"] = [name for name in canonical[position].get("_invalid_money_fields", []) if name != field]
        canonical[position] = review_invoice(canonical[position])
    st.session_state[rows_key] = canonical
    if table_changed:
        st.session_state[revision_key] += 1
        st.rerun()
    summary = invoice_summary(canonical)
    metrics.markdown('<div class="dl-statusbar">'
        f'<div class="dl-stat-unit"><span class="dl-stat-label">처리한 문서</span><div class="dl-stat-value">{summary["count"]}건</div></div>'
        f'<div class="dl-stat-unit"><span class="dl-stat-label">합계 금액</span><div class="dl-stat-value">₩{summary["total"]:,}</div></div>'
        f'<div class="dl-stat-unit"><span class="dl-stat-label">부가세</span><div class="dl-stat-value">₩{summary["vat"]:,}</div></div></div>', unsafe_allow_html=True)
    issues = review_worklist(summary["rows"])
    if issues:
        st.warning(f'확인이 필요한 문서 {summary["needs_review"]}건이 있습니다. 원본과 대조해 주세요.')
        st.caption(" / ".join(f'{issue["filename"]} · {issue["field"]} · {issue["reason"]}' for issue in issues[:6]))
    else:
        st.success("검수할 항목이 없습니다.")
        st.caption("자동 확인 결과입니다. 읽힌 글자가 맞는지는 아래 원본과 비교해 주세요.")
    st.markdown("#### 확인하고 수정하기")
    default_id, default_field = default_selection(canonical, issues)
    doc_ids = [row["_document_id"] for row in canonical]
    names = {row["_document_id"]: row.get("파일명") or "문서" for row in canonical}
    selected_id = st.segmented_control("문서", options=doc_ids, default=default_id,
        format_func=lambda doc_id: names[doc_id], key=editor_key+"_selected_document") or default_id
    selected_row = next((row for row in canonical if row["_document_id"] == selected_id), None)
    if selected_row is not None:
        issue_fields = [issue["field"] for issue in issues if issue["document_id"] == selected_id and issue["field"] in EDITABLE_FIELDS]
        field_default = issue_fields[0] if issue_fields else (default_field if selected_id == default_id else "품목")
        field = st.segmented_control("수정할 항목", options=EDITABLE_FIELDS, default=field_default,
            key=editor_key+"_field_"+selected_id) or field_default
        left, right = st.columns([1.15, 1])
        with left:
            if source_files:
                st.markdown("**원본 문서**")
                _source_panel(st, selected_row, source_files, editor_key)
            with st.expander("OCR로 읽은 글", expanded=not bool(source_files)):
                st.text_area("OCR 원문", selected_row.get("원문", ""), height=200,
                    key=editor_key+"_source_"+selected_row["_document_id"], disabled=True, label_visibility="collapsed")
        with right:
            st.markdown(f'**현재값 · {field}**')
            field_value = selected_row.get(field)
            st.code("(비어 있음)" if field_value is None or field_value == "" else str(field_value))
            recognition = selected_row.get("_recognition", {})
            route = {"local_ocr":"로컬 OCR", "pdf_text":"PDF 텍스트 추출", "mixed_pdf":"PDF 텍스트 + 로컬 OCR"}.get(recognition.get("route"))
            if route:
                st.caption(f'{route} · {recognition.get("pages", 1)}페이지' + (" · 정밀 모델" if recognition.get("model") == "tessdata_best" else ""))
            if selected_row.get("_extraction_failed") and not selected_row.get("_manual_review_complete"):
                st.caption("원본과 표를 대조해 누락된 항목을 입력한 뒤 완료해 주세요.")
                if st.button("문서를 직접 확인 완료", key=editor_key+"_manual_"+selected_row["_document_id"]):
                    selected_row["_manual_review_complete"] = True
                    st.session_state[revision_key] += 1
                    st.rerun()
            elif field in EDITABLE_FIELDS:
                with st.form(editor_key+"_field_form_"+selected_row["_document_id"]+"_"+field):
                    corrected = st.text_input("수정값", value="" if field_value is None else str(field_value))
                    applied = st.form_submit_button("값 적용", type="primary")
                if applied:
                    selected_row[field] = corrected
                    if field in {"공급가액", "부가세", "합계"}:
                        selected_row["_invalid_money_fields"] = [name for name in selected_row.get("_invalid_money_fields", []) if name != field]
                    selected_row.update(review_invoice(selected_row))
                    st.session_state[rows_key] = canonical
                    st.session_state[revision_key] += 1
                    st.rerun()
            position = canonical.index(selected_row)
            if position < len(originals) and count_edits([originals[position]], [selected_row]):
                if st.button("원래 값으로 되돌리기", key=editor_key+"_revert_"+selected_id):
                    canonical[position] = dict(originals[position])
                    st.session_state[rows_key] = canonical
                    st.session_state[revision_key] += 1
                    st.rerun()
    edits = count_edits(originals, canonical)
    if edits:
        st.markdown(f'<div class="dl-edit-count">수정 {edits}건 반영됨</div>', unsafe_allow_html=True)
    st.download_button("수정한 엑셀 파일 다운로드", data=xlsx_bytes(summary["rows"]),
        file_name="doculens_문서정리_검수.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch", on_click="ignore")


def main():
    import streamlit as st
    st.set_page_config(page_title="DOCULENS | 문서 정리", page_icon="▥", layout="wide", initial_sidebar_state="collapsed")
    identity = load_identity()
    st.markdown(app_css(identity), unsafe_allow_html=True)
    st.markdown('<div class="dl-topbar"><div class="dl-brand">Doculens.</div>'
        '<span class="dl-live">내 컴퓨터에서 처리하는 문서 정리</span></div>'
        '<div class="dl-heading"><div><div class="kicker">파일을 넣고, 한 번만 누르세요</div>'
        '<h1>쌓인 전표를, 한 장의 표로.</h1>'
        '<p>문서 인식부터 금액 대조, 엑셀 생성과 다운로드까지 한 번에 이어집니다.</p></div></div>', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="dl-sidebar-title">문서 정리</div>'
            '<div class="dl-rail-label">이렇게 사용하세요</div>'
            '<div class="dl-rail-row"><i>01</i> 파일 올리기</div>'
            '<div class="dl-rail-row"><i>02</i> 한 번에 엑셀 받기</div>'
            '<div class="dl-rail-row"><i>03</i> 필요한 항목만 검수</div>'
            '<div class="dl-muted-note">문서는 외부 OCR API로 전송하지 않습니다. 흐린 글씨와 누락 항목은 원문과 대조해 주세요.</div>', unsafe_allow_html=True)
        if st.button("예시 전표로 화면 보기", type="secondary", width="stretch"):
            started = time.perf_counter()
            try:
                st.session_state["doculens_demo"] = {"rows":demo_rows(), "elapsed":time.perf_counter()-started}
            except Exception as exc:
                st.error(str(exc))
    st.markdown('<div class="dl-section"><div class="left"><span class="index">01</span>'
        '<h2>문서 입력</h2></div><span class="detail">최대 50개 · 파일당 15MB</span></div>', unsafe_allow_html=True)
    files = st.file_uploader("PDF 또는 영수증 이미지", type=["pdf","png","jpg","jpeg","tif","tiff"],
        accept_multiple_files=True, help="최대 50개, 파일당 15MB·50페이지. 전표 한 건을 파일 하나로 넣어 주세요.")
    error = None
    try:
        validate_files(files or [])
    except ValueError as exc:
        error = str(exc)
        st.error(error)
    inputs = tuple((f.name, f.getvalue()) for f in (files or [])) if not error else ()
    fingerprint = input_key(inputs)
    current = st.session_state.get("doculens_job")
    if current is None or current.key != fingerprint:
        if current is not None:
            stale_prefix = "doculens_editor_" + current.key
            for key in list(st.session_state):
                if key.startswith(stale_prefix):
                    del st.session_state[key]
        current = DownloadJob(fingerprint)
        st.session_state["doculens_job"] = current
    job = current
    state = job.snapshot()
    active = state["status"] in {"queued", "running"}

    def build_export():
        def work(progress):
            read, step = tracked_steps(job, extract_text, progress)
            return process_invoices(inputs, read, parse_invoice, xlsx_bytes, step)
        return job.run(work)

    if state["status"] == "ready":
        # The top button must not keep serving the first, unedited workbook.
        current_rows = st.session_state.get("doculens_editor_"+fingerprint+"_canonical_rows", state["report"]["rows"])
        top_edits = count_edits(st.session_state.get("doculens_editor_"+fingerprint+"_original_rows", current_rows), current_rows)
        st.download_button("정리한 엑셀 다운로드", data=xlsx_bytes(current_rows),
            file_name="doculens_문서정리.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary", width="stretch", key="ready_"+fingerprint[:16], on_click="ignore")
    else:
        st.download_button("한 번에 정리하고 엑셀 받기", data=build_export,
            file_name="doculens_문서정리.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary", width="stretch", disabled=not inputs or active,
            key="one_click_"+fingerprint[:16], on_click=job.request)
    if state["status"] == "ready" and top_edits:
        st.markdown(f'<div class="dl-edit-count">수정 {top_edits}건 반영됨</div>', unsafe_allow_html=True)
    if inputs:
        st.caption(f"선택한 문서 {len(inputs)}개 · 추가 설정 없이 진행합니다. 확인할 항목은 엑셀과 아래 결과에 함께 표시합니다.")
    else:
        st.caption("파일을 추가하면 정리 버튼이 활성화됩니다.")

    @st.fragment(run_every=.4 if active else None)
    def results_panel():
        latest = job.snapshot()
        if latest["status"] in {"queued", "running"}:
            done, total = latest["done"], latest["total"]
            st.progress(done / max(1,total), text=f'{done}/{total or len(inputs)}개 처리 중 · {latest["label"] or "문서를 준비하고 있습니다"}')
            st.markdown('<div class="dl-file-status">' + "".join(
                f'<div class="dl-file-row" data-state="{html.escape(label.split(" ")[0])}"><span>{html.escape(name)}</span><b>{html.escape(label)}</b></div>'
                for name, label in file_status_lines([name for name, _ in inputs], latest.get("files", {}))) + '</div>', unsafe_allow_html=True)
            return
        if active:
            st.rerun()
        if latest["status"] == "failed":
            st.error(latest["error"])
            st.caption("입력 파일을 고친 뒤 같은 버튼으로 다시 시도할 수 있습니다.")
        elif latest["status"] == "ready":
            st.markdown('<div class="dl-notice"><span>엑셀 파일을 만들었습니다. 확인할 항목은 아래에서 수정할 수 있어요.</span></div>', unsafe_allow_html=True)
            report = latest["report"]
            _render_results(st, report["rows"], latest["elapsed"], "doculens_editor_"+fingerprint, inputs)
        elif not inputs and not error and st.session_state.get("doculens_demo"):
            demo = st.session_state["doculens_demo"]
            st.caption("예시 전표는 가상 자료입니다.")
            _render_results(st, demo["rows"], demo["elapsed"], "doculens_demo_editor", tuple((path.name, path.read_bytes()) for path in sorted((Path(__file__).parent/"assets").glob("demo_invoice_*.pdf"))))
        else:
            st.markdown('<div class="dl-notice"><span>파일을 넣고 위 버튼을 누르면 엑셀 다운로드가 시작됩니다.</span></div>', unsafe_allow_html=True)
    results_panel()
    st.markdown('<div class="dl-muted-note">인식 결과와 원문은 저장 전에 대조해 주세요. 파일을 바꾸면 이전 결과와 섞이지 않도록 새 작업으로 시작합니다.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
